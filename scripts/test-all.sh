#!/usr/bin/env bash
#
# test-all.sh — every test surface in the Azmoth monorepo, one command, one verdict.
#
# The repository has five test surfaces and no single place that runs them. CI runs them as five
# GitHub jobs (.github/workflows/ci.yml), which is the right shape for CI and the wrong shape for
# "am I safe to commit?" — you cannot run a GitHub matrix on a laptop. This script is that second
# shape: the same checks, in dependency order, with one exit code.
#
#     ./scripts/test-all.sh              # everything that can run here
#     ./scripts/test-all.sh --fast       # checks + engine tests, no builds  (~2 min)
#     ./scripts/test-all.sh --help
#
# It is deliberately NOT a second definition of what the checks are. Every phase shells out to the
# command that already owns it — `pnpm turbo typecheck`, `pytest`, `scripts/e2e_partner_api.py` —
# so a check cannot pass here and fail in CI because this file drifted. What lives here is the
# order, the parallelism, the logs and the verdict.
#
# Nothing here requires Docker. Phase 4 needs a stack answering on two ports and says so plainly
# when there isn't one; the other three phases run against the checkout.

set -uo pipefail

# Bash 4 for `${x,,}` in slug() and `local -a` in phase 1. macOS ships 3.2 as /bin/bash, so the
# `env bash` shebang finds a Homebrew 5.x first if there is one — and this says which problem it
# is if there is not, rather than dying on a syntax error twenty lines in.
if (( BASH_VERSINFO[0] < 4 )); then
  echo "test-all.sh needs bash 4+; this is ${BASH_VERSION}." >&2
  echo "On macOS: brew install bash  (the shebang picks up the new one automatically)." >&2
  exit 2
fi

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# ── Configuration ────────────────────────────────────────────────────────────────────────────
# The two base URLs are the same variables scripts/e2e_partner_api.py reads, so pointing the E2E
# run at a non-default stack is one export that both halves honour.
E2E_ENGINE_BASE_URL="${E2E_ENGINE_BASE_URL:-http://localhost:8000}"
E2E_WEB_BASE_URL="${E2E_WEB_BASE_URL:-http://localhost:3000}"
PROBE_TIMEOUT="${PROBE_TIMEOUT:-5}"

# The engine's own interpreter, which is where pytest and the pinned dependencies are. Falling back
# to python3 lets the script report "pytest is not installed" instead of "no such file".
ENGINE_PY="$ROOT/apps/engine/.venv/bin/python"
[[ -x "$ENGINE_PY" ]] || ENGINE_PY="$(command -v python3 || true)"

TS="$(date +%Y%m%d-%H%M%S)"
LOG_DIR="$ROOT/logs"
MASTER_LOG="$LOG_DIR/test-all-$TS.log"
CHECK_LOG_DIR="$LOG_DIR/test-all-$TS"

# ── Colour ───────────────────────────────────────────────────────────────────────────────────
use_color=1
[[ -t 1 ]] || use_color=0
[[ -n "${NO_COLOR:-}" ]] && use_color=0
if (( use_color )); then
  C_RESET=$'\033[0m'; C_BOLD=$'\033[1m'; C_DIM=$'\033[2m'
  C_GREEN=$'\033[32m'; C_RED=$'\033[31m'; C_YELLOW=$'\033[33m'; C_CYAN=$'\033[36m'
else
  C_RESET=''; C_BOLD=''; C_DIM=''; C_GREEN=''; C_RED=''; C_YELLOW=''; C_CYAN=''
fi

# ── Output ───────────────────────────────────────────────────────────────────────────────────
# say() writes to the terminal with colour and to the master log without it. A `tee` over the whole
# script would have been shorter and would have put escape codes in a file people grep, and would
# have raced the process-substitution flush at exit.
# A literal ESC rather than \x1b, which is a GNU sed extension: BSD sed on macOS would leave
# every escape code in the log file.
ESC=$'\033'
say() {
  printf '%s\n' "$*"
  printf '%s\n' "$*" | sed -e "s/${ESC}\[[0-9;]*m//g" >>"$MASTER_LOG"
}
phase_header() {
  say ""
  say "${C_BOLD}${C_CYAN}═══ PHASE $1: $2 ═══${C_RESET}"
  say ""
}

# ── Check results ────────────────────────────────────────────────────────────────────────────
# Parallel checks cannot append to a shared array — they are subshells — so each one writes its
# verdict to a file named after itself and the parent reads them back after `wait`.
STATUS_DIR=""

slug() { local s="${1,,}"; s="${s//[^a-z0-9]/-}"; printf '%s' "${s//--/-}"; }

# run_check <name> <log-slug> <command...>
# Runs one check with its output in its own log file, and records PASS/FAIL plus wall-clock.
run_check() {
  local name="$1" sl="$2"; shift 2
  local log="$CHECK_LOG_DIR/$sl.log"
  local start end rc
  start=$(date +%s)
  { printf '$ %s\n\n' "$*"; "$@"; } >"$log" 2>&1
  rc=$?
  end=$(date +%s)
  printf '%s|%s|%s|%s\n' "$name" "$( ((rc==0)) && echo PASS || echo FAIL )" "$((end-start))" "$log" \
    >"$STATUS_DIR/$sl.status"
  return $rc
}

# skip_check <name> <reason> [order-prefix] - a check that was not attempted, recorded so the log
# explains itself. report_checks reads the status files in glob order, so the numeric prefixes the
# callers pass are what keep "unit tests" above "golden suite" instead of alphabetical order.
skip_check() {
  local sl; sl="${3:-}$(slug "$1")"
  printf '%s|SKIP|0|%s\n' "$1" "$2" >"$STATUS_DIR/$sl.status"
}

# report_checks — prints one line per check written since the last reset, and returns 1 if any
# check failed. SKIP does not fail a phase; a skipped check is a check that could not apply.
report_checks() {
  local failed=0 f name status secs detail
  shopt -s nullglob
  for f in "$STATUS_DIR"/*.status; do
    IFS='|' read -r name status secs detail <"$f"
    case "$status" in
      PASS) say "  ${C_GREEN}✔ PASS${C_RESET}  ${name} ${C_DIM}(${secs}s)${C_RESET}" ;;
      FAIL) say "  ${C_RED}✘ FAIL${C_RESET}  ${name} ${C_DIM}(${secs}s)${C_RESET}"; failed=1 ;;
      SKIP) say "  ${C_YELLOW}⤼ SKIP${C_RESET}  ${name} ${C_DIM}— ${detail}${C_RESET}" ;;
    esac
  done
  shopt -u nullglob
  return $failed
}

# show_failures — the tail of every failing check's log, on the terminal and in the master log.
# Without this the script tells you a phase failed and makes you go find out why, which is the
# thing that makes people stop using a wrapper and run the underlying commands by hand.
show_failures() {
  local f name status secs log
  shopt -s nullglob
  for f in "$STATUS_DIR"/*.status; do
    IFS='|' read -r name status secs log <"$f"
    [[ "$status" == FAIL ]] || continue
    say ""
    say "${C_RED}${C_BOLD}── ${name} — last 40 lines of ${log#$ROOT/} ──${C_RESET}"
    tail -n 40 "$log" | while IFS= read -r line; do say "  $line"; done
  done
  shopt -u nullglob
}

reset_checks() { rm -f "$STATUS_DIR"/*.status 2>/dev/null || true; }

# ── The summary box ──────────────────────────────────────────────────────────────────────────
# BOX_INNER is the printable width between the two frame characters: the border rows are 38 wide
# inside, and box_row prints one space of its own on each side, so label+pad+status must come to 36.
#
# The display width of each status is passed in rather than measured, because ${#s} counts ✅ as
# one character and wc -L is not portable. ✅ and ❌ are East_Asian_Width=Wide, so they are two
# columns everywhere; ⏭️ is two by emoji presentation. "NOT RUN" is spelled with an ASCII dash
# instead of ➖ for exactly this reason - ➖ is one column by EAW and two by emoji presentation,
# so it lands differently in different terminals and there is no width that is right for both.
BOX_INNER=36
box_line() { say "${C_BOLD}$1${C_RESET}"; }

box_row() {
  local label="$1" status="$2" colour="$3" swidth="$4"
  local pad=$(( BOX_INNER - ${#label} - swidth ))
  (( pad < 1 )) && pad=1
  say "${C_BOLD}║${C_RESET} ${label}$(printf '%*s' "$pad" '')${colour}${status}${C_RESET} ${C_BOLD}║${C_RESET}"
}

# verdict_row <label> <PASS|FAIL|SKIPPED|NOT RUN>
verdict_row() {
  case "$2" in
    PASS)     box_row "$1" "✅ PASS"     "$C_GREEN"   7 ;;
    FAIL)     box_row "$1" "❌ FAIL"     "$C_RED"     7 ;;
    SKIPPED)  box_row "$1" "⏭️ SKIPPED"  "$C_YELLOW" 10 ;;
    *)        box_row "$1" "-- NOT RUN"  "$C_DIM"    10 ;;
  esac
}

# ── Phases ───────────────────────────────────────────────────────────────────────────────────
P1=NOT_RUN; P2=NOT_RUN; P3=NOT_RUN; P4=NOT_RUN

# Phase 1 — fast checks, in parallel.
#
# Three independent commands over the same checkout, none of which writes to it. `pnpm turbo`
# already fans out across the six workspace packages internally and caches by content hash, so the
# parallelism here is across the *kinds* of check, not across the apps — running one turbo process
# per app would fight over .turbo/ for no gain.
phase_1_fast_checks() {
  phase_header 1 "Fast Checks"
  reset_checks

  local -a pids=()

  if [[ -n "$PY_LINT_CMD" ]]; then
    say "  ${C_DIM}running: python lint (${PY_LINT_NAME}), turbo typecheck, turbo lint${C_RESET}"
    run_check "Python lint (${PY_LINT_NAME})" "1-python-lint" $PY_LINT_CMD & pids+=($!)
  else
    say "  ${C_DIM}running: turbo typecheck, turbo lint${C_RESET}"
    skip_check "Python lint" "no ruff/black config in the repo" "1-"
  fi

  run_check "TypeScript typecheck (all packages)" "2-typecheck" pnpm turbo typecheck & pids+=($!)
  run_check "ESLint (all packages)"               "3-eslint"  pnpm turbo lint      & pids+=($!)

  local p; for p in "${pids[@]}"; do wait "$p"; done

  say ""
  if report_checks; then P1=PASS; else P1=FAIL; show_failures; fi
}

# Phase 2 — the engine, sequentially.
#
# Sequential because both invocations drive the same Soufflé binary and the same catalog load, and
# because pytest-xdist is not installed: two concurrent pytest processes here would contend for
# apps/engine/test.db and interleave into an unreadable log for no wall-clock saving.
#
# The golden suite runs a second time on purpose. `pytest tests/` covers it, but the golden cases
# are the ones that assert the *billing numbers* against tests/golden/oracle.py — an independent
# fee-schedule calculation, not the engine — and when they are the thing that broke you want them
# named on their own line and in their own log rather than buried in 1,700 others. It costs
# about four seconds.
phase_2_engine_tests() {
  phase_header 2 "Engine Tests"
  reset_checks

  if [[ -z "$ENGINE_PY" ]]; then
    P2=FAIL
    say "  ${C_RED}✘ FAIL${C_RESET}  no Python interpreter found"
    say "        expected apps/engine/.venv/bin/python — see README 'Working on one tier at a time'"
    return
  fi
  say "  ${C_DIM}interpreter: ${ENGINE_PY#$ROOT/}${C_RESET}"
  say ""

  # `-rs` names the reason for every skip. The three benchmark skips are expected (pytest.ini
  # carries --benchmark-skip); a solver-dependent test skipping means souffle is missing, which is a
  # thing you want to read in the log rather than mistake for a pass.
  ( cd "$ROOT/apps/engine" && run_check "Unit tests (pytest tests/)" "1-pytest-unit" \
      "$ENGINE_PY" -m pytest tests/ -rs )
  local unit=$?

  if (( unit == 0 )); then
    ( cd "$ROOT/apps/engine" && run_check "Golden suite (tests/test_golden_cases.py)" "2-pytest-golden" \
        "$ENGINE_PY" -m pytest tests/test_golden_cases.py -v )
  else
    # Recorded as a skip rather than silently omitted: "the golden suite did not run" and "the
    # golden suite passed" have to look different in the log.
    skip_check "Golden suite (tests/test_golden_cases.py)" "not run - the unit suite failed first" "2-"
  fi

  if report_checks; then P2=PASS; else P2=FAIL; show_failures; fi
}

# Phase 3 — the three Next.js builds, in parallel.
#
# One turbo invocation rather than three, because turbo is the thing that knows web, marketing and
# docs are independent and that @workspace/ui has to be typechecked before any of them. It runs
# them concurrently on its own and caches the result by content hash, so an unchanged app is a
# cache hit rather than a second 90-second build. Three separate `pnpm --filter` processes would
# lose the cache and race each other for .turbo/.
#
# TURBO_CONCURRENCY is honoured if exported: `next build` wants roughly a gigabyte per app, so on a
# machine with less than about 4 GB free, TURBO_CONCURRENCY=1 is the difference between a slow pass
# and an OOM kill that reads like a build failure.
phase_3_builds() {
  phase_header 3 "Builds"
  reset_checks
  say "  ${C_DIM}running: turbo build (web, marketing, docs — turbo parallelises internally)${C_RESET}"
  say ""

  run_check "Builds (web, marketing, docs)" "1-builds" \
    pnpm turbo build --filter=web --filter=marketing --filter=docs

  # turbo names the tasks it could not finish on a `Failed:` line in its summary. Reading it back
  # turns one red line into "docs is the one that broke" without a second run.
  local log="$CHECK_LOG_DIR/1-builds.log" failed_tasks=''
  if [[ -f "$log" ]]; then
    failed_tasks="$(grep -E '^[[:space:]]*Failed:' "$log" \
      | sed -E 's/^[[:space:]]*Failed:[[:space:]]*//' | tr '\n' ' ')"
  fi

  if report_checks; then
    P3=PASS
  else
    P3=FAIL
    [[ -n "$failed_tasks" ]] && say "  ${C_RED}failed tasks:${C_RESET} $failed_tasks"
    show_failures
  fi
}

# Phase 4 — the end-to-end proof, against a stack somebody else started.
#
# Optional by construction, not by flag: the script probes the two ports and skips with a reason
# when nothing answers, because the common case is a developer with no stack up who still wants
# phases 1–3. A skip here never changes the exit code — see the summary block.
stack_is_up() {
  curl -fsS --max-time "$PROBE_TIMEOUT" -o /dev/null "$E2E_ENGINE_BASE_URL/health" 2>/dev/null \
    && curl -fsS --max-time "$PROBE_TIMEOUT" -o /dev/null "$E2E_WEB_BASE_URL" 2>/dev/null
}

phase_4_e2e() {
  phase_header 4 "E2E (Partner API)"
  reset_checks

  if [[ -z "$ENGINE_PY" ]]; then
    P4=SKIPPED
    say "  ${C_YELLOW}⤼ SKIP${C_RESET}  no Python interpreter found"
    return
  fi

  # --e2e-only takes the user at their word and runs without probing: the script itself exits 2
  # when the stack is unreachable, and a FAIL that says so is more useful than this wrapper
  # second-guessing an explicit flag.
  if (( ! E2E_ONLY )) && ! stack_is_up; then
    P4=SKIPPED
    say "  ${C_YELLOW}⤼ SKIP${C_RESET}  ${C_YELLOW}Skipped: stack not running${C_RESET}"
    say "        probed ${E2E_ENGINE_BASE_URL}/health and ${E2E_WEB_BASE_URL}"
    say "        ${C_DIM}start one with: make up   (or: pnpm dev, beside uvicorn)${C_RESET}"
    return
  fi

  say "  ${C_DIM}engine ${E2E_ENGINE_BASE_URL} · web ${E2E_WEB_BASE_URL}${C_RESET}"
  say ""
  # --keep-practices: without it the run deletes the organisation it created, the next run
  # re-onboards, and `practices` rows accumulate keyed on an organisation id no endpoint can
  # remove. See the script's own docstring under "## Cleanup".
  run_check "E2E partner API (10 steps)" "1-e2e" \
    "$ENGINE_PY" scripts/e2e_partner_api.py --keep-practices

  if report_checks; then P4=PASS; else P4=FAIL; show_failures; fi
}

# ── Usage ────────────────────────────────────────────────────────────────────────────────────
usage() {
  cat <<'EOF'
test-all.sh — run every test surface in the Azmoth monorepo and print one verdict.

USAGE
    ./scripts/test-all.sh [options]

PHASES                                                          typical wall-clock
    1  Fast checks    python lint (if configured), turbo typecheck, turbo lint     ~30s
    2  Engine tests   pytest tests/  then  pytest tests/test_golden_cases.py       ~2m
    3  Builds         next build for web, marketing and docs (turbo, parallel)   ~1-3m
    4  E2E            scripts/e2e_partner_api.py, only if a stack is answering     ~40s

    Phases run in order and the run stops at the first failing phase, because a type error
    makes a build failure uninformative and a broken engine makes an E2E failure a duplicate.

OPTIONS
    --skip-e2e     Do not run phase 4 even if a stack is answering.
    --fast         Phases 1 and 2 only. The pre-commit loop.
    --e2e-only     Phase 4 only, without probing first (assumes the stack is up).
    --no-color     Plain output. Also implied by NO_COLOR=1 or a non-tty stdout.
    -h, --help     This text.

EXIT STATUS
    0   every phase that ran passed
    1   a phase failed
    2   bad usage, or the environment cannot run the script at all

    A skipped phase 4 does not affect the exit code. A phase 4 that ran and failed does.

ENVIRONMENT
    E2E_ENGINE_BASE_URL   default http://localhost:8000   (also read by e2e_partner_api.py)
    E2E_WEB_BASE_URL      default http://localhost:3000   (likewise)
    TURBO_CONCURRENCY     passed through to turbo; set to 1 on a machine with <4 GB free
    PROBE_TIMEOUT         seconds to wait for the stack probe (default 5)

LOGS
    logs/test-all-<timestamp>.log        the transcript, without colour codes
    logs/test-all-<timestamp>/<check>.log   full output of each individual check
EOF
}

# ── Argument parsing ─────────────────────────────────────────────────────────────────────────
SKIP_E2E=0; FAST=0; E2E_ONLY=0
while (( $# )); do
  case "$1" in
    --skip-e2e) SKIP_E2E=1 ;;
    --fast)     FAST=1 ;;
    --e2e-only) E2E_ONLY=1 ;;
    --no-color) use_color=0
                C_RESET=''; C_BOLD=''; C_DIM=''; C_GREEN=''; C_RED=''; C_YELLOW=''; C_CYAN='' ;;
    -h|--help)  usage; exit 0 ;;
    *) printf 'test-all.sh: unknown option %q\n\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

if (( FAST && E2E_ONLY )); then
  echo "test-all.sh: --fast and --e2e-only ask for disjoint sets of phases." >&2
  exit 2
fi

# ── Preflight ────────────────────────────────────────────────────────────────────────────────
mkdir -p "$CHECK_LOG_DIR"
STATUS_DIR="$(mktemp -d "${TMPDIR:-/tmp}/test-all-status.XXXXXX")"
trap 'rm -rf "$STATUS_DIR"' EXIT

# Python lint runs only when the repo actually configures one. A globally-installed ruff pointed at
# a repo with no config would lint 40k lines to its own defaults and report failures nobody agreed
# to — a check the repo never opted into is noise, not a check. Adding a pyproject.toml or
# ruff.toml is all it takes to turn this on.
PY_LINT_CMD=''; PY_LINT_NAME=''
py_lint_configured() {
  local f
  for f in pyproject.toml ruff.toml .ruff.toml apps/engine/pyproject.toml \
           apps/engine/ruff.toml apps/engine/.ruff.toml; do
    [[ -f "$ROOT/$f" ]] && return 0
  done
  return 1
}
if py_lint_configured; then
  for tool in ruff black; do
    bin=""
    [[ -x "$ROOT/apps/engine/.venv/bin/$tool" ]] && bin="$ROOT/apps/engine/.venv/bin/$tool"
    [[ -z "$bin" ]] && bin="$(command -v "$tool" 2>/dev/null || true)"
    [[ -z "$bin" ]] && continue
    case "$tool" in
      ruff)  PY_LINT_CMD="$bin check apps/engine scripts";  PY_LINT_NAME=ruff ;;
      black) PY_LINT_CMD="$bin --check apps/engine scripts"; PY_LINT_NAME=black ;;
    esac
    break
  done
fi

START_TS=$(date +%s)
: >"$MASTER_LOG"
say "${C_BOLD}Azmoth — full test suite${C_RESET}"
say "  ${C_DIM}$(date '+%Y-%m-%d %H:%M:%S')  ·  $(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo 'no git')  ·  log: ${MASTER_LOG#$ROOT/}${C_RESET}"

# ── Run ──────────────────────────────────────────────────────────────────────────────────────
# Fail fast between phases. Within a phase every check still runs, so one command does show you
# all of the type errors and all of the lint errors — it is the *next* phase that is pointless
# once this one is red.
if (( E2E_ONLY )); then
  phase_4_e2e
else
  phase_1_fast_checks
  if [[ "$P1" == PASS ]]; then
    phase_2_engine_tests
    if [[ "$P2" == PASS ]]; then
      if (( FAST )); then
        P3=SKIPPED
      else
        phase_3_builds
      fi
      if [[ "$P3" == PASS || "$P3" == SKIPPED ]]; then
        if (( FAST )); then
          P4=SKIPPED
        elif (( SKIP_E2E )); then
          P4=SKIPPED
          phase_header 4 "E2E (Partner API)"
          say "  ${C_YELLOW}⤼ SKIP${C_RESET}  --skip-e2e was given"
        else
          phase_4_e2e
        fi
      fi
    fi
  fi
fi

# ── Summary ──────────────────────────────────────────────────────────────────────────────────
# Required phases are 1-3. Phase 4 fails the run only if it actually ran and failed; a stack that
# is not up is a fact about the machine, not a defect in the code.
overall=PASS
for p in "$P1" "$P2" "$P3" "$P4"; do
  [[ "$p" == FAIL ]] && overall=FAIL
done
if (( ! E2E_ONLY )); then
  for p in "$P1" "$P2"; do
    [[ "$p" == NOT_RUN ]] && overall=FAIL   # skipped by fail-fast, i.e. something upstream broke
  done
fi

ELAPSED=$(( $(date +%s) - START_TS ))
say ""
box_line "╔══════════════════════════════════════╗"
box_line "║      AZMOTH TEST SUITE SUMMARY       ║"
box_line "╠══════════════════════════════════════╣"
verdict_row "Fast Checks:"  "${P1/NOT_RUN/NOT RUN}"
verdict_row "Engine Tests:" "${P2/NOT_RUN/NOT RUN}"
verdict_row "Builds:"       "${P3/NOT_RUN/NOT RUN}"
verdict_row "E2E:"          "${P4/NOT_RUN/NOT RUN}"
box_line "╠══════════════════════════════════════╣"
if [[ "$overall" == PASS ]]; then
  box_row "OVERALL:" "✅ ALL PASSED" "$C_GREEN" 13
else
  box_row "OVERALL:" "❌ FAILED"     "$C_RED"   9
fi
box_line "╚══════════════════════════════════════╝"
say ""
say "  ${C_DIM}${ELAPSED}s  ·  logs in ${CHECK_LOG_DIR#$ROOT/}/${C_RESET}"

[[ "$overall" == PASS ]] && exit 0
exit 1
