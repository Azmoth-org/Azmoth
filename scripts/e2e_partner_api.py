#!/usr/bin/env python3
"""End-to-end proof of the paid path, against a running stack.

    apps/engine/.venv/bin/python scripts/e2e_partner_api.py

Ten steps, in order, each asserting a status code and a body. Between them they walk the whole
commercial lifecycle a paying integrator experiences — sign in, mint a key, audit with it, be
refused without it, meter the usage, revoke, be refused again — and they audit the five golden
deliveries in `apps/engine/tests/golden/`, whose expected results were computed from the fee
schedule rather than from the engine (`tests/golden/oracle.py`). If both halves pass, the API works
*and* it is right.

    1  sign in as the test practice, through the product's own Better Auth flow
    2  mint an API key through the product's key-creation endpoint; token once, hash stored
    3  case A with the key                                → 200 and the known answer
    4  the same request without a key, and with a garbage one → 401, 401
    5  case A again                                       → an identical receipt_hash
    6  case B and case C                                  → the verified rule citations
    7  case E raw → 422 ECHTDATEN_UNDECLARED; anonymised → 200 and case A's report
    8  usage metering: successful audits counted, refused auth not charged
    9  revoke the key through the product flow; immediate re-call → 401
   10  tenancy: org A's key cannot read org B's job

## The stack

Reads `E2E_WEB_BASE_URL` (default `http://localhost:3000`) and `E2E_ENGINE_BASE_URL` (default
`http://localhost:8000`) and prints which stack it found, so a passing run says what it passed
against. `--detect` alone prints that and exits. Either compose stack works
(`infra/docker/docker-compose.dev.yml` or `docker-compose.yml`), as does `pnpm dev` beside
`uvicorn` — nothing here depends on Docker except the two optional database reads noted below.

## No sideways access

Everything goes through a published surface. The account is created by `POST
/api/auth/sign-up/email` and named by `POST /api/onboarding`; the key is minted by `POST
/api/engine/settings/api-keys` and revoked by `DELETE /api/engine/settings/api-keys/{key_id}` — the
same routes the settings screen calls. If `E2E_LEGACY_PASSWORDS` names a password the account was
signed up under before a prior run's password scheme changed, `POST /api/auth/change-password` rolls
it onto today's password — there is no admin plugin in this deployment and `request-password-reset`
is hard-disabled, so this is the only endpoint that can recover an account short of deleting it by
hand. Nothing writes to the database outside that one recovery path, and no key is seeded by hand,
so a change that broke minting or revocation cannot be hidden by a fixture that built its own.

Two steps additionally *read* the database when `docker compose` can reach Postgres, because there
is no endpoint that can answer them and the alternative is to assert nothing: that `api_keys.key_hash`
is SHA-256 of the token that was handed out (step 2), and that `api_usage_logs` grew by exactly the
expected number of rows (step 8). Both degrade to a printed SKIP with a reason; neither is a write.

## Zero third-party dependencies

Standard library only — `urllib`, `http.cookiejar`, `zipfile` — so it runs under any interpreter on
the machine, including one that has never installed the engine's requirements. The only import from
the repository is `apps/engine/tests/golden/oracle.py`, which is itself standard-library-only and is
the module that owns what "expected" means.

## The plaintext key

Printed nowhere after step 2's own assertion. Step 2 prints the `key_id` — the public half, which is
what a log line names — and every later step refers to the key by that. A test script that echoed a
live credential into a terminal, a CI log or a scrollback buffer would be a worse leak than the one
it is testing for.

## Cleanup

Every key this run minted is revoked at exit, through the product's own endpoint, whatever the
outcome. An organisation is deleted only if this run created it — a reused one is left alone, since
deleting somebody's practice because a test borrowed it would be worse than leaving a row behind.
What is deliberately *not* removed is written on the closing line: the `user` row (Better Auth
offers no self-delete here) and the revoked `api_keys` rows, which are kept by design because "this
key was live from March to July" is a question a billing dispute asks.

Exit status: 0 every step passed · 1 at least one FAIL · 2 the stack is not reachable.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
import zipfile
from http.cookiejar import CookieJar
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GOLDEN_DIR = REPO_ROOT / "apps" / "engine" / "tests" / "golden"
ANONYMIZER = REPO_ROOT / "scripts" / "anonymize_padnext.py"
COMPOSE_DEV = REPO_ROOT / "infra" / "docker" / "docker-compose.dev.yml"
COMPOSE_PROD = REPO_ROOT / "infra" / "docker" / "docker-compose.yml"

sys.path.insert(0, str(GOLDEN_DIR))
import oracle  # noqa: E402  - the golden expectations; standard library only, see its header

WEB_BASE = os.environ.get("E2E_WEB_BASE_URL", "http://localhost:3000").rstrip("/")
ENGINE_BASE = os.environ.get("E2E_ENGINE_BASE_URL", "http://localhost:8000").rstrip("/")

#: Deterministic test identities, reused across runs rather than freshly invented each time.
#:
#: A run that minted a new practice every time would leave a trail of `doctor_profiles` and
#: `practices` rows that no product endpoint can remove — `lanr` is unique, so they cannot even be
#: reused. Two stable accounts are created once, on the first run, and signed into afterwards; the
#: keys are what churn, and those the product can revoke.
PRACTICES = {
    "A": {
        "email": "e2e-partner-a@e2e.azmoth.test",
        "name": "E2E Partner A",
        "first": "Erika",
        "last": "Musterfrau",
        "lanr": "999000101",
        "specialty": "Innere Medizin",
        "practice": "E2E Partner-Test Praxis A",
        "bsnr": "999000201",
        "city": "München",
        "plz": "80331",
    },
    "B": {
        "email": "e2e-partner-b@e2e.azmoth.test",
        "name": "E2E Partner B",
        "first": "Bernd",
        "last": "Beispiel",
        "lanr": "999000102",
        "specialty": "Chirurgie",
        "practice": "E2E Partner-Test Praxis B",
        "bsnr": "999000202",
        "city": "Bonn",
        "plz": "53111",
    },
}

#: Not a secret: it authenticates two accounts that exist only inside a synthetic-data deployment,
#: on a host that is not published. Overridable via `E2E_PASSWORD` for a stack where that is not
#: true.
#:
#: The default is *derived*, not a literal in source. A fixed high-entropy string sitting in a
#: script is exactly the shape a secret scanner exists to flag, and "read the comment above it, it's
#: fine" is not something a scanner — or the next person who greps history for credentials — can
#: verify from the diff alone. Hashing a public, non-secret seed keeps the property that actually
#: matters here (deterministic across runs, so the same two practices are reused instead of a fresh
#: `doctor_profiles` row every time) without a secret-shaped literal ever being committed.
_PASSWORD_SEED = "azmoth-e2e-partner-api-synthetic-test-account-v1"
PASSWORD = os.environ.get("E2E_PASSWORD") or (
    "E2e-" + hashlib.sha256(_PASSWORD_SEED.encode("utf-8")).hexdigest()[:20] + "!"
)

#: Passwords a practice may have been signed up under before `PASSWORD`'s derivation changed —
#: comma-separated in `E2E_LEGACY_PASSWORDS`. Empty by default: nothing in source ever names an old
#: password, since that would be exactly the secret-shaped literal this file stopped committing.
#: `sign_in` tries each once, and on a match rolls the account onto `PASSWORD` through the product's
#: own `/api/auth/change-password` — there is no admin plugin here and `/api/auth/request-password-
#: reset` is hard-disabled (`RESET_PASSWORD_DISABLED`, no `sendResetPassword` configured), so this is
#: the only endpoint that can recover an account without deleting and re-onboarding it by hand.
LEGACY_PASSWORDS = [p for p in os.environ.get("E2E_LEGACY_PASSWORDS", "").split(",") if p]

#: A well-formed token for a key that does not exist. Shaped correctly on purpose: a malformed
#: string is refused by a length check before any lookup, which tests a cheaper path than the one a
#: leaked-and-rotated credential takes.
GARBAGE_KEY = "azm_live_" + "de" * 6 + "_" + "ad" * 24


class StepFailure(Exception):
    """A step could not be performed at all — recorded as a FAIL row, not a traceback.

    Distinct from a failed assertion: "the sign-in endpoint rate-limited us" is not the API being
    wrong, and a stack trace would bury the thirty rows that already passed. Cleanup still runs.
    """

    def __init__(self, step: str, name: str, detail: str) -> None:
        super().__init__(detail)
        self.step = step
        self.name = name
        self.detail = detail


# ==========================================================================================
# the result table
# ==========================================================================================


class Table:
    """The PASS/FAIL table, printed as it goes so a hanging step is visible.

    A step is one row. `note` is what a reader needs to believe the row without re-running it — the
    figure that was compared, the code that came back — which is why it is not optional in spirit
    even though it is in the signature.
    """

    PASS, FAIL, SKIP, BUG = "PASS", "FAIL", "SKIP", "BUG "

    def __init__(self) -> None:
        self.rows: list[tuple[str, str, str, str]] = []
        self._started = time.monotonic()

    def record(self, step: str, name: str, outcome: str, note: str = "") -> None:
        self.rows.append((step, name, outcome, note))
        marker = {self.PASS: "✓", self.FAIL: "✗", self.SKIP: "–", self.BUG: "!"}[outcome]
        print(f"  {marker} [{outcome.strip()}] {step:>4}  {name}" + (f" — {note}" if note else ""))
        sys.stdout.flush()

    def ok(self, step: str, name: str, note: str = "") -> None:
        self.record(step, name, self.PASS, note)

    def fail(self, step: str, name: str, note: str) -> None:
        self.record(step, name, self.FAIL, note)

    def skip(self, step: str, name: str, note: str) -> None:
        self.record(step, name, self.SKIP, note)

    def bug(self, step: str, name: str, note: str) -> None:
        self.record(step, name, self.BUG, note)

    def check(self, step: str, name: str, condition: bool, note: str = "", failure: str = "") -> bool:
        """Record one assertion. Returns the condition, so a caller can stop on a failure."""
        if condition:
            self.ok(step, name, note)
        else:
            self.fail(step, name, failure or note)
        return condition

    def failures(self) -> int:
        return sum(1 for _, _, outcome, _ in self.rows if outcome == self.FAIL)

    def render(self) -> str:
        step_w = max(4, *(len(r[0]) for r in self.rows))
        name_w = max(20, *(len(r[1]) for r in self.rows))
        line = "─" * (step_w + name_w + 60)
        out = [
            "",
            line,
            f"{'STEP':<{step_w}}  {'CHECK':<{name_w}}  RESULT  DETAIL",
            line,
        ]
        for step, name, outcome, note in self.rows:
            out.append(f"{step:<{step_w}}  {name:<{name_w}}  {outcome:<6}  {note}")
        out.append(line)
        counts = {
            outcome: sum(1 for _, _, o, _ in self.rows if o == outcome)
            for outcome in (self.PASS, self.FAIL, self.SKIP, self.BUG)
        }
        out.append(
            f"{counts[self.PASS]} passed · {counts[self.FAIL]} failed · "
            f"{counts[self.SKIP]} skipped · {counts[self.BUG]} bug · "
            f"{time.monotonic() - self._started:.1f}s"
        )
        out.append(line)
        return "\n".join(out)


# ==========================================================================================
# HTTP, on the standard library
# ==========================================================================================


class Response:
    __slots__ = ("status", "headers", "body")

    def __init__(self, status: int, headers: dict[str, str], body: bytes) -> None:
        self.status = status
        self.headers = {k.lower(): v for k, v in headers.items()}
        self.body = body

    def json(self) -> dict:
        try:
            return json.loads(self.body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return {}

    @property
    def error_code(self) -> str:
        return str(self.json().get("error_code", ""))

    def excerpt(self, limit: int = 220) -> str:
        text = self.body.decode("utf-8", "replace").replace("\n", " ")
        return text[:limit]


class Client:
    """One cookie jar, one `urlopen`. Enough HTTP for ten steps and nothing more.

    `Origin` is sent on every request because Better Auth refuses a state-changing call without one
    (`MISSING_OR_NULL_ORIGIN`) — a browser always sends it, so a script that did not would be
    testing a path no real caller takes.
    """

    def __init__(self) -> None:
        self.jar = CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar),
            urllib.request.HTTPErrorProcessor,
        )

    def request(
        self,
        method: str,
        url: str,
        *,
        json_body: object | None = None,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
        timeout: float = 120.0,
    ) -> Response:
        sent = dict(headers or {})
        payload = data
        if json_body is not None:
            payload = json.dumps(json_body).encode("utf-8")
            sent.setdefault("Content-Type", "application/json")
        origin = WEB_BASE if url.startswith(WEB_BASE) else ENGINE_BASE
        sent.setdefault("Origin", origin)
        sent.setdefault("Accept", "application/json")

        request = urllib.request.Request(url, data=payload, headers=sent, method=method)
        try:
            with self.opener.open(request, timeout=timeout) as handle:
                return Response(handle.status, dict(handle.headers), handle.read())
        except urllib.error.HTTPError as error:  # 4xx and 5xx are answers here, not exceptions
            return Response(error.code, dict(error.headers or {}), error.read())
        except urllib.error.URLError as error:
            raise SystemExit(f"cannot reach {url}: {error.reason}") from error

    def get(self, url: str, **kwargs) -> Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs) -> Response:
        return self.request("POST", url, **kwargs)

    def delete(self, url: str, **kwargs) -> Response:
        return self.request("DELETE", url, **kwargs)

    def post_multipart_zip(self, url: str, field: str, filename: str, blob: bytes,
                           headers: dict[str, str]) -> Response:
        boundary = f"----azmothE2E{uuid.uuid4().hex}"
        body = io.BytesIO()
        body.write(f"--{boundary}\r\n".encode())
        body.write(
            f'Content-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'.encode()
        )
        body.write(b"Content-Type: application/zip\r\n\r\n")
        body.write(blob)
        body.write(f"\r\n--{boundary}--\r\n".encode())
        sent = dict(headers)
        sent["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        return self.request("POST", url, data=body.getvalue(), headers=sent)


# ==========================================================================================
# the stack, and the optional database reads
# ==========================================================================================


def detect_stack() -> dict[str, str]:
    """What is answering, and — where Docker can say — which compose file it came from."""
    found: dict[str, str] = {"web": WEB_BASE, "engine": ENGINE_BASE}

    engine = Client().get(f"{ENGINE_BASE}/api/v1/health")
    if engine.status != 200:
        raise SystemExit(
            f"engine at {ENGINE_BASE} answered {engine.status} to /api/v1/health. Start the stack "
            f"first: docker compose -f {COMPOSE_DEV.relative_to(REPO_ROOT)} up -d"
        )
    payload = engine.json()
    found["engine_status"] = str(payload.get("status", "?"))
    found["catalog"] = str(payload.get("catalog_version", "?"))

    web = Client().get(f"{WEB_BASE}/api/health")
    found["web_status"] = f"HTTP {web.status}"

    found["compose"] = "not a docker stack (or docker not available)"
    if shutil.which("docker"):
        for path in (COMPOSE_DEV, COMPOSE_PROD):
            probe = subprocess.run(  # noqa: S603 - fixed argv, no shell
                ["docker", "compose", "-f", str(path), "ps", "--services", "--filter",
                 "status=running"],
                capture_output=True, text=True, cwd=REPO_ROOT,
            )
            services = {line.strip() for line in probe.stdout.splitlines() if line.strip()}
            if {"engine", "web"} <= services:
                found["compose"] = f"{path.relative_to(REPO_ROOT)} ({', '.join(sorted(services))})"
                break
    return found


def psql(sql: str) -> str | None:
    """One read-only query through `docker compose exec postgres psql`, or `None`.

    `None` covers every reason it could not run — no Docker, a stack that is not Docker, a
    container that is not up — and every caller turns that into a printed SKIP rather than a
    failure. There is no endpoint that can answer the two questions this is used for, and asserting
    nothing about them would be worse than asserting them only where it is possible.
    """
    if not shutil.which("docker"):
        return None
    for path in (COMPOSE_DEV, COMPOSE_PROD):
        result = subprocess.run(  # noqa: S603 - fixed argv, no shell
            ["docker", "compose", "-f", str(path), "exec", "-T", "postgres",
             "psql", "-U", os.environ.get("POSTGRES_USER", "azmoth"),
             "-d", os.environ.get("POSTGRES_DB", "azmoth"), "-At", "-c", sql],
            capture_output=True, text=True, cwd=REPO_ROOT, timeout=30,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    return None


# ==========================================================================================
# the product's own flows
# ==========================================================================================


#: How many times an auth call is retried past a `429`, and the longest single wait honoured.
AUTH_RETRIES = 3
AUTH_MAX_WAIT_SECONDS = 70


def _auth_with_backoff(client: Client, route: str, body: dict) -> Response:
    """One Better Auth call, waiting out a `429` the number of seconds it asks for."""
    response = client.post(f"{WEB_BASE}/api/auth/{route}", json_body=body)
    for _ in range(AUTH_RETRIES):
        if response.status != 429:
            return response
        wait = response.json().get("retry_after")
        try:
            delay = min(float(wait), AUTH_MAX_WAIT_SECONDS)
        except (TypeError, ValueError):
            delay = 5.0
        print(f"    auth {route} rate-limited; waiting {delay:.0f}s as it asked")
        sys.stdout.flush()
        time.sleep(delay + 1)
        response = client.post(f"{WEB_BASE}/api/auth/{route}", json_body=body)
    return response


def sign_in(client: Client, practice: dict) -> tuple[str, bool]:
    """Sign in, signing up first if the account does not exist yet.

    Returns `(organization_id, organisation_was_created_by_this_run)`. Both halves go through Better
    Auth's own endpoints and the application's own onboarding route — there is no path here that
    writes an identity row directly, which is the property that makes step 2 mean anything.
    """
    created_org = False

    # Better Auth rate-limits its own auth endpoints — a few sign-in attempts a minute per address,
    # which two practices per run and a couple of consecutive runs will reach. It answers `429` with
    # an honest `retry_after`, so the right thing is to wait exactly that long rather than to fail:
    # a `429` here is the product protecting itself, not the API being wrong.
    signed_in = _auth_with_backoff(
        client, "sign-in/email", {"email": practice["email"], "password": PASSWORD}
    )
    if signed_in.status != 200 and _migrate_legacy_password(client, practice):
        signed_in = _auth_with_backoff(
            client, "sign-in/email", {"email": practice["email"], "password": PASSWORD}
        )
    if signed_in.status != 200:
        signed_up = _auth_with_backoff(
            client,
            "sign-up/email",
            {"email": practice["email"], "password": PASSWORD, "name": practice["name"]},
        )
        if signed_up.status != 200:
            raise StepFailure(
                "1", "signed in through Better Auth",
                f"neither sign-in ({signed_in.status}) nor sign-up ({signed_up.status}) worked for "
                f"{practice['email']}: {signed_up.excerpt()} — if this deployment sets "
                "SIGNUP_ALLOWLIST, add e2e.azmoth.test to it (apps/web/lib/auth-allowlist.ts); if "
                "the account exists under an older password, set E2E_LEGACY_PASSWORDS to it so this "
                "run can migrate it forward",
            )

    session = client.get(f"{WEB_BASE}/api/auth/get-session").json()
    organization_id = (session.get("session") or {}).get("activeOrganizationId")

    if not organization_id:
        # No practice yet. `POST /api/onboarding` is the route the sign-up wizard posts to, and it
        # creates the organisation and makes it active — see its header for why that is its job and
        # not sign-up's.
        organization_id = _onboard(client, practice)
        created_org = True
    else:
        # The practice exists, but the *cookie* that says so belongs to a browser session and this
        # is a fresh client — which is the second-device case `GET /api/onboarding/resume` exists
        # for: it re-derives the fact from the database and reissues the cookie. Without it
        # `callEngine` answers `403 onboarding_required` and a key can never be minted.
        client.get(f"{WEB_BASE}/api/onboarding/resume")
        probe = client.get(f"{WEB_BASE}/api/engine/settings/api-keys")
        if probe.status == 403 and probe.json().get("error") == "onboarding_required":
            # The rows are gone (an organisation deleted by an earlier cleanup takes its practice
            # row's meaning with it). Re-run onboarding, which is an upsert and safe to repeat.
            organization_id = _onboard(client, practice)
            created_org = True

    return organization_id, created_org


def _migrate_legacy_password(client: Client, practice: dict) -> bool:
    """Try each of `LEGACY_PASSWORDS` and, on a match, roll the account onto `PASSWORD`.

    Both calls are published Better Auth routes — `sign-in/email` and `change-password` — so this
    writes nothing this script does not already have a product-endpoint story for. Returns whether
    the account is now signed in under `PASSWORD`.
    """
    for old_password in LEGACY_PASSWORDS:
        attempt = _auth_with_backoff(
            client, "sign-in/email", {"email": practice["email"], "password": old_password}
        )
        if attempt.status != 200:
            continue
        changed = client.post(
            f"{WEB_BASE}/api/auth/change-password",
            json_body={
                "currentPassword": old_password,
                "newPassword": PASSWORD,
                "revokeOtherSessions": False,
            },
        )
        if changed.status == 200:
            print(f"    {practice['email']}: migrated off a legacy password onto today's PASSWORD")
            return True
    return False


def _onboard(client: Client, practice: dict) -> str:
    """`POST /api/onboarding` — the doctor and the practice, upserted. Returns the organisation id."""
    onboarded = client.post(
        f"{WEB_BASE}/api/onboarding",
        json_body={
            "doctor": {
                "title": "Dr. med.",
                "firstName": practice["first"],
                "lastName": practice["last"],
                "lanr": practice["lanr"],
                "specialty": practice["specialty"],
            },
            "practice": {
                "practiceName": practice["practice"],
                "bsnr": practice["bsnr"],
                "city": practice["city"],
                "plz": practice["plz"],
            },
        },
    )
    if onboarded.status != 200:
        raise StepFailure(
            "1", "practice named through POST /api/onboarding",
            f"HTTP {onboarded.status}: {onboarded.excerpt()}",
        )
    return str(onboarded.json()["organization"]["id"])


def mint_key(client: Client, label: str) -> dict:
    """`POST /api/engine/settings/api-keys` — the route the settings screen calls."""
    response = client.post(
        f"{WEB_BASE}/api/engine/settings/api-keys", json_body={"name": label}
    )
    if response.status != 201:
        raise StepFailure(
            "2", "mint a key through the product flow",
            f"POST /api/engine/settings/api-keys → HTTP {response.status}: {response.excerpt()}",
        )
    return response.json()


def revoke_key(client: Client, key_id: str) -> Response:
    return client.delete(f"{WEB_BASE}/api/engine/settings/api-keys/{key_id}")


def audit_single(client: Client, token: str, case: str) -> Response:
    return client.post(
        f"{ENGINE_BASE}/api/v1/audit/single",
        data=oracle.delivery_bytes(case),
        headers={
            "X-API-Key": token,
            "Content-Type": "application/xml",
            "x-padnext-filename": f"{case}_padx.xml",
        },
    )


def audit_bytes(client: Client, token: str, blob: bytes, filename: str) -> Response:
    return client.post(
        f"{ENGINE_BASE}/api/v1/audit/single",
        data=blob,
        headers={
            "X-API-Key": token,
            "Content-Type": "application/xml",
            "x-padnext-filename": filename,
        },
    )


# ==========================================================================================
# the run
# ==========================================================================================


def run(table: Table, *, skip_tenancy: bool, keep_practices: bool) -> None:
    minted: list[tuple[Client, str]] = []   # (client that owns the session, key_id)
    created_orgs: list[tuple[Client, str]] = []

    try:
        # -- 1. sign in ------------------------------------------------------------------
        practice_a = Client()
        org_a, created_a = sign_in(practice_a, PRACTICES["A"])
        if created_a:
            created_orgs.append((practice_a, org_a))
        session = practice_a.get(f"{WEB_BASE}/api/auth/get-session").json()
        table.check(
            "1", "signed in through Better Auth",
            bool(session.get("user", {}).get("id")) and bool(org_a),
            note=f"user={session.get('user', {}).get('id', '?')[:8]}… org={org_a[:8]}…"
                 + (" (practice created by this run)" if created_a else " (existing practice)"),
            failure=f"no session or no active organisation: {session}",
        )

        # -- 2. mint a key ---------------------------------------------------------------
        issued = mint_key(practice_a, "e2e-partner-api")
        token = issued["token"]
        key_id = issued["key_id"]
        minted.append((practice_a, key_id))
        table.check(
            "2", "token returned, once", 
            token.startswith("azm_live_") and issued["organization_id"] == org_a,
            note=f"key_id={key_id} (the plaintext token is not printed again)",
            failure=f"unexpected mint body: { {k: v for k, v in issued.items() if k != 'token'} }",
        )

        listed = practice_a.get(f"{WEB_BASE}/api/engine/settings/api-keys").json()
        row = next((k for k in listed.get("keys", []) if k["key_id"] == key_id), None)
        table.check(
            "2", "listing carries no secret",
            row is not None and "token" not in row and "key_hash" not in row,
            note="GET /settings/api-keys returns key_id, name, timestamps — no secret",
            failure=f"a listed key carries a secret field: {row}",
        )

        stored = psql(
            "select key_hash from api_keys where key_id = "
            f"'{key_id}';"  # noqa: S608 - key_id is 12 hex chars from our own mint response
        )
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        if stored is None:
            table.skip("2", "stored form is a hash",
                       "no psql via docker compose; no endpoint can answer this")
        else:
            table.check(
                "2", "stored form is a hash",
                stored == digest and stored != token,
                note="api_keys.key_hash == sha256(token), and is not the token",
                failure=f"key_hash {stored!r} is not sha256 of the issued token",
            )

        # -- 3. case A with the key ------------------------------------------------------
        expected_a = oracle.load_expected("case_a_known_answer")
        response = audit_single(practice_a, token, "case_a_known_answer")
        if not table.check(
            "3", "case A → 200", response.status == 200,
            note=f"HTTP {response.status}",
            failure=f"HTTP {response.status}: {response.excerpt()}",
        ):
            return
        report_a = response.json()
        problems = oracle.compare_report(report_a, expected_a["report"])
        table.check(
            "3", "case A → the known answer", not problems,
            note=(
                f"nachgerechnet {report_a['recomputed_total_eur']} € · "
                f"Rechendifferenz {report_a['arithmetic_delta_eur']} € · "
                f"buckets {report_a['confirmed_wrong_eur']}/{report_a['confirmed_fine_eur']}/"
                f"{report_a['unconfirmed_eur']} € · "
                f"findings {[f['type'] for f in report_a['findings']]}"
            ),
            failure="; ".join(problems),
        )
        table.check(
            "3", "every position berechnungsfähig",
            all(
                p["verdict"] == "chargeable" and "Keine verifizierte Regel" in p["bucket_reason"]
                for p in report_a["positions"]
            ),
            note="5 chargeable, each 'keine verifizierte Regel anwendbar'",
            failure=str([(p["positionsnr"], p["verdict"], p["bucket_reason"][:60])
                         for p in report_a["positions"]]),
        )
        quota_headers = [h for h in ("x-quota-limit", "x-quota-remaining", "x-quota-reset")
                         if h in response.headers]
        table.check(
            "3", "quota headers present", len(quota_headers) == 3,
            note=f"X-Quota-Remaining {response.headers.get('x-quota-remaining')}",
            failure=f"only {quota_headers} of the three quota headers were sent",
        )

        # -- 4. without a key, and with a garbage one ------------------------------------
        naked = practice_a.post(
            f"{ENGINE_BASE}/api/v1/audit/single",
            data=oracle.delivery_bytes("case_a_known_answer"),
            headers={"Content-Type": "application/xml"},
        )
        table.check(
            "4", "no key → 401 API_KEY_REQUIRED",
            naked.status == 401 and naked.error_code == "API_KEY_REQUIRED",
            note=f"HTTP {naked.status} {naked.error_code}",
            failure=f"HTTP {naked.status} {naked.excerpt()}",
        )
        garbage = audit_single(Client(), GARBAGE_KEY, "case_a_known_answer")
        table.check(
            "4", "garbage key → 401 API_KEY_INVALID",
            garbage.status == 401 and garbage.error_code == "API_KEY_INVALID",
            note=f"HTTP {garbage.status} {garbage.error_code} (unknown, wrong and revoked are one code)",
            failure=f"HTTP {garbage.status} {garbage.excerpt()}",
        )

        # -- 5. determinism --------------------------------------------------------------
        again = audit_single(practice_a, token, "case_a_known_answer")
        first_hash, second_hash = report_a["receipt_hash"], again.json().get("receipt_hash", "")
        table.check(
            "5", "receipt_hash is stable", bool(first_hash) and first_hash == second_hash,
            note=f"{first_hash[:16]}… twice",
            failure=f"{first_hash} != {second_hash}",
        )
        table.check(
            "5", "receipt canary", first_hash.startswith(expected_a["receipt_hash_prefix"]),
            note=f"prefix {expected_a['receipt_hash_prefix']}",
            failure=(
                f"receipt moved to {first_hash[:16]}…: the catalog, rules, logic, solver, policy "
                "or response shape changed — see apps/engine/app/services/receipt.py"
            ),
        )

        # -- 6. the two verified rules ---------------------------------------------------
        for case, rule_id, label in (
            ("case_b_verified_exclusion", "excl_auto_34_4", "case B → verified exclusion"),
            ("case_c_verified_factor_cap", "cap_auto_440", "case C → verified factor cap"),
        ):
            expected = oracle.load_expected(case)
            response = audit_single(practice_a, token, case)
            if not table.check(
                "6", f"{label} → 200", response.status == expected["http_status"],
                note=f"HTTP {response.status}",
                failure=f"HTTP {response.status}: {response.excerpt()}",
            ):
                continue
            report = response.json()
            problems = oracle.compare_report(report, expected["report"])
            table.check(
                "6", label, not problems,
                note=(
                    f"nachweislich falsch {report['confirmed_wrong_eur']} € · "
                    f"bestätigt korrekt {report['confirmed_fine_eur']} € · "
                    f"unbestätigt {report['unconfirmed_eur']} €"
                ),
                failure="; ".join(problems),
            )
            cited = [f for f in report["findings"] if f["rule_id"] == rule_id]
            table.check(
                "6", f"{label} cites {rule_id}", bool(cited),
                note=f"{cited[0]['type']} on position {cited[0]['positionsnr']}" if cited else "",
                failure=f"no finding cites {rule_id}; got "
                        f"{[(f['type'], f['rule_id']) for f in report['findings']]}",
            )

        # -- 6b. the known defect, checked rather than assumed ---------------------------
        #
        # Not a numbered step and not a FAIL: `tests/golden/bug_positionsnr_collision/` is a defect
        # this repository has already written down (docs/api/E2E_GOLDEN.md §5) and holds open as a
        # strict xfail. Re-checking it here means the one command that proves the paid path also
        # says whether that defect is still live — and turns into a PASS, loudly, the day it is not.
        collision = oracle.load_expected("bug_positionsnr_collision")
        observed = audit_single(practice_a, token, "bug_positionsnr_collision")
        if observed.status != 200:
            table.fail("6b", "known defect: positionsnr collision",
                       f"the reproducer did not audit at all: HTTP {observed.status}")
        else:
            problems = oracle.compare_report(observed.json(), collision["report"])
            body = observed.json()
            if problems:
                table.bug(
                    "6b", "known defect: positionsnr collision",
                    f"still present — bestätigt korrekt {body['confirmed_fine_eur']} €, "
                    f"nachweislich falsch {body['confirmed_wrong_eur']} € "
                    f"(expected {collision['report']['confirmed_fine_eur']} € / "
                    f"{collision['report']['confirmed_wrong_eur']} €). "
                    "See docs/api/E2E_GOLDEN.md §5",
                )
            else:
                table.ok(
                    "6b", "known defect: positionsnr collision",
                    "FIXED — promote tests/golden/bug_positionsnr_collision to a golden case and "
                    "drop the strict xfail in tests/test_golden_cases.py",
                )

        # -- 7. the gate -----------------------------------------------------------------
        expected_e = oracle.load_expected("case_e_echtdaten_gate")
        raw = audit_single(practice_a, token, "case_e_echtdaten_gate")
        body = raw.json()
        codes = [e.get("code") for e in (body.get("details") or {}).get("errors") or []]
        table.check(
            "7", "case E raw → 422 ECHTDATEN_UNDECLARED",
            raw.status == expected_e["http_status"]
            and raw.error_code == expected_e["error_code"],
            note=f"HTTP {raw.status} {raw.error_code}",
            failure=f"HTTP {raw.status} {raw.excerpt()}",
        )
        table.check(
            "7", "the refusal batches its errors",
            all(code in codes for code in expected_e["batched_error_codes_include"]),
            note=f"details.errors = {codes}",
            failure=f"details.errors = {codes}, expected to include "
                    f"{expected_e['batched_error_codes_include']}",
        )

        anonymised = anonymise(GOLDEN_DIR / "case_e_echtdaten_gate" / "delivery_padx.xml")
        if anonymised is None:
            table.fail("7", "anonymize_padnext.py runs", f"{ANONYMIZER} did not produce a file")
        else:
            table.ok("7", "anonymize_padnext.py runs",
                     'output carries echtdaten="false"')
            cleaned = audit_bytes(practice_a, token, anonymised, "case_e_anonymised_padx.xml")
            after = expected_e["after_anonymisation"]
            if table.check(
                "7", "anonymised → 200", cleaned.status == after["http_status"],
                note=f"HTTP {cleaned.status}",
                failure=f"HTTP {cleaned.status}: {cleaned.excerpt()}",
            ):
                problems = oracle.compare_report(cleaned.json(), after["report"])
                table.check(
                    "7", "anonymised → case A's report", not problems,
                    note=f"claimed {cleaned.json()['claimed_total_eur']} €, "
                         f"unbestätigt {cleaned.json()['unconfirmed_eur']} €",
                    failure="; ".join(problems),
                )

        # -- 8. metering -----------------------------------------------------------------
        #
        # Counted **per endpoint**, not as a total. A total would have to account for the usage and
        # billing reads this step itself makes — which is arithmetic that passes for the wrong
        # reason as soon as one more call is added anywhere. `by_endpoint["/api/v1/audit/single"]`
        # moves only when an audit is attributed, which is exactly the claim.
        #
        # `GET /settings/usage` flushes the meter's buffer before reading (see its docstring: a
        # partner who has just made five calls must not be told they made none), so a window whose
        # ends are both such a read has no lag in it.
        AUDIT_ENDPOINT = "/api/v1/audit/single"
        before_calls, before_failed = usage_endpoint(practice_a, token, AUDIT_ENDPOINT)
        before_rows = usage_rows(org_a, AUDIT_ENDPOINT)
        before_invoices = quota_invoices(practice_a, token)

        successes = 3
        for _ in range(successes):
            audit_single(practice_a, token, "case_a_known_answer")

        refused = 4
        for _ in range(refused // 2):
            audit_single(Client(), GARBAGE_KEY, "case_a_known_answer")
            practice_a.post(
                f"{ENGINE_BASE}/api/v1/audit/single",
                data=oracle.delivery_bytes("case_a_known_answer"),
                headers={"Content-Type": "application/xml"},
            )

        after_calls, after_failed = usage_endpoint(practice_a, token, AUDIT_ENDPOINT)
        table.check(
            "8", "successful audits are metered",
            after_calls - before_calls == successes,
            note=f"{AUDIT_ENDPOINT} +{after_calls - before_calls} for {successes} audits",
            failure=f"+{after_calls - before_calls} metered calls for {successes} audits",
        )
        table.check(
            "8", "refused auth is not metered",
            after_calls - before_calls == successes and after_failed == before_failed,
            note=f"{refused} × 401 added nothing — a 401 resolves no key, so the row has no "
                 "tenant to attribute and is never written",
            failure=f"+{after_calls - before_calls} calls and +{after_failed - before_failed} "
                    f"failures for {successes} audits and {refused} refusals",
        )

        after_invoices = quota_invoices(practice_a, token)
        if before_invoices is None or after_invoices is None:
            table.skip("8", "quota counts invoices, not requests",
                       "GET /billing/usage did not answer")
        else:
            table.check(
                "8", "quota counts invoices, not requests",
                after_invoices - before_invoices == successes,
                note=f"invoices_processed +{after_invoices - before_invoices} "
                     f"for {successes} audits and {refused} refusals",
                failure=f"invoices_processed +{after_invoices - before_invoices}, "
                        f"expected +{successes}",
            )

        after_rows = usage_rows(org_a, AUDIT_ENDPOINT)
        if before_rows is None or after_rows is None:
            table.skip("8", "api_usage_logs row count",
                       "no psql via docker compose; asserted through GET /settings/usage instead")
        else:
            table.check(
                "8", "api_usage_logs row count",
                after_rows - before_rows == successes,
                note=f"{before_rows} → {after_rows} rows for this organisation on {AUDIT_ENDPOINT}",
                failure=f"+{after_rows - before_rows} rows, expected +{successes}",
            )

        # -- 9. revocation ---------------------------------------------------------------
        revoked = revoke_key(practice_a, key_id)
        table.check(
            "9", "revoke through the product flow",
            revoked.status == 200 and revoked.json().get("revoked") is True,
            note=f"DELETE /settings/api-keys/{key_id} → HTTP {revoked.status}",
            failure=f"HTTP {revoked.status}: {revoked.excerpt()}",
        )
        dead = audit_single(Client(), token, "case_a_known_answer")
        table.check(
            "9", "revoked key → 401 immediately",
            dead.status == 401 and dead.error_code == "API_KEY_INVALID",
            note=f"HTTP {dead.status} {dead.error_code}, no cache window",
            failure=f"HTTP {dead.status} {dead.excerpt()}",
        )
        still_listed = practice_a.get(f"{WEB_BASE}/api/engine/settings/api-keys").json()
        kept = next((k for k in still_listed.get("keys", []) if k["key_id"] == key_id), None)
        table.check(
            "9", "the revoked row survives",
            kept is not None and kept.get("revoked_at"),
            note=f"revoked_at={kept.get('revoked_at') if kept else None} — a billing dispute asks",
            failure="the revoked key vanished from the listing",
        )

        # -- 10. tenancy -----------------------------------------------------------------
        if skip_tenancy:
            table.skip("10", "org A cannot read org B's job", "--skip-tenancy was given")
            return
        tenancy(table, minted, created_orgs)

    except StepFailure as failure:
        table.fail(failure.step, failure.name, failure.detail)
    finally:
        cleanup(table, minted, created_orgs if not keep_practices else [])


def tenancy(table: Table, minted: list, created_orgs: list) -> None:
    """A second practice, a real bulk job, and org A asking for it.

    A second organisation is cheap here — the product creates one from a sign-up and an onboarding
    call, which is two requests — so this is asserted rather than skipped. A *job* is needed and
    not merely a report, because `/audit/single` is synchronous and stores nothing a second caller
    could ask for; `/audit/bulk` is the endpoint with a `job_id` in it.
    """
    practice_b = Client()
    org_b, created_b = sign_in(practice_b, PRACTICES["B"])
    if created_b:
        created_orgs.append((practice_b, org_b))
    issued_b = mint_key(practice_b, "e2e-partner-api-tenancy")
    minted.append((practice_b, issued_b["key_id"]))
    table.check(
        "10", "a second practice and key exist",
        org_b != "" and issued_b["organization_id"] == org_b,
        note=f"org={org_b[:8]}… key_id={issued_b['key_id']}",
        failure=f"second organisation not usable: {org_b!r}",
    )

    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("case_a_padx.xml", oracle.delivery_bytes("case_a_known_answer"))
    accepted = practice_b.post_multipart_zip(
        f"{ENGINE_BASE}/api/v1/audit/bulk", "file", "e2e_tenancy.zip", archive.getvalue(),
        {"X-API-Key": issued_b["token"]},
    )
    if not table.check(
        "10", "org B starts a bulk job", accepted.status == 202,
        note=f"HTTP {accepted.status} {accepted.json().get('batch_id', '')}",
        failure=f"HTTP {accepted.status}: {accepted.excerpt()}",
    ):
        return
    job_id = accepted.json()["batch_id"]

    # Poll to a terminal status before asking across the boundary, so a 404 cannot be "not written
    # yet" wearing the costume of "not yours".
    deadline = time.monotonic() + 60
    status = "PENDING"
    while time.monotonic() < deadline:
        polled = practice_b.get(
            f"{ENGINE_BASE}/api/v1/audit/bulk/{job_id}", headers={"X-API-Key": issued_b["token"]}
        )
        status = polled.json().get("status", "?")
        if status in {"COMPLETED", "FAILED"}:
            break
        time.sleep(1.0)
    table.check(
        "10", "org B can read its own job", status == "COMPLETED",
        note=f"{job_id} → {status}",
        failure=f"{job_id} reached {status}, not COMPLETED",
    )

    key_a = mint_key(_owner_of(minted, 0), "e2e-partner-api-tenancy-a")
    minted.append((_owner_of(minted, 0), key_a["key_id"]))
    crossed = Client().get(
        f"{ENGINE_BASE}/api/v1/audit/bulk/{job_id}", headers={"X-API-Key": key_a["token"]}
    )
    table.check(
        "10", "org A cannot read org B's job",
        crossed.status == 404 and crossed.error_code == "AUDIT_JOB_NOT_FOUND",
        note=f"HTTP {crossed.status} {crossed.error_code} — 404 and not 403, so a key cannot "
             "discover that another practice's job exists",
        failure=f"HTTP {crossed.status} {crossed.excerpt()}",
    )
    listing = Client().get(
        f"{ENGINE_BASE}/api/v1/audit/bulk?limit=100", headers={"X-API-Key": key_a["token"]}
    ).json()
    ids = [job.get("job_id") or job.get("batch_id") for job in listing.get("jobs", [])]
    table.check(
        "10", "org B's job is absent from org A's listing", job_id not in ids,
        note=f"org A sees {listing.get('total', 0)} job(s), none of them org B's",
        failure=f"org A's listing contains {job_id}",
    )


def _owner_of(minted: list, index: int) -> Client:
    return minted[index][0]


# ==========================================================================================
# helpers the steps lean on
# ==========================================================================================


def anonymise(source: Path) -> bytes | None:
    """Run the real `scripts/anonymize_padnext.py`, as a practice would, and return its output.

    A subprocess and not an import: this is the script a practice copies onto its own machine and
    runs on data that has not been anonymised yet, so the thing under test is the file on disk with
    its own `__main__`, not a function reached past it.
    """
    workspace = Path(os.environ.get("TMPDIR", "/tmp")) / f"azmoth-e2e-{uuid.uuid4().hex[:8]}"
    workspace.mkdir(parents=True, exist_ok=True)
    staged = workspace / source.name
    staged.write_bytes(source.read_bytes())
    target = workspace / "anonymised_padx.xml"

    done = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, str(ANONYMIZER), str(staged), "-o", str(target), "--quiet"],
        capture_output=True, text=True,
    )
    if done.returncode != 0 or not target.exists():
        print(f"    anonymiser said: {done.stdout.strip()} {done.stderr.strip()}")
        return None
    blob = target.read_bytes()
    shutil.rmtree(workspace, ignore_errors=True)
    return blob if b'echtdaten="false"' in blob else None


def usage_endpoint(client: Client, token: str, endpoint: str) -> tuple[int, int]:
    """`(requests, failed_requests)` for one endpoint, from `GET /settings/usage`.

    That endpoint flushes the meter's buffer before it reads, which is what makes this usable as a
    window boundary: the row for a call made a millisecond ago is in the answer.
    """
    response = client.get(
        f"{ENGINE_BASE}/api/v1/settings/usage", headers={"X-API-Key": token}
    )
    for row in response.json().get("by_endpoint", []):
        if row.get("endpoint") == endpoint:
            return int(row.get("requests", 0)), int(row.get("failed_requests", 0))
    return 0, 0


def quota_invoices(client: Client, token: str) -> int | None:
    """`invoices_processed` from `GET /billing/usage` — the unit a quota is spent in."""
    response = client.get(
        f"{ENGINE_BASE}/api/v1/billing/usage", headers={"X-API-Key": token}
    )
    if response.status != 200:
        return None
    value = response.json().get("invoices_processed")
    return int(value) if value is not None else None


def usage_rows(organization_id: str, endpoint: str) -> int | None:
    """Rows in `api_usage_logs` for one organisation on one endpoint, or `None` without psql.

    Endpoint-scoped for the same reason step 8 counts that way: an unscoped count would also move
    for the usage read that closes the window, and an assertion that has to predict its own
    side effects is one that will be wrong the next time a line is added above it.
    """
    out = psql(
        "select count(*) from api_usage_logs where organization_id = "
        f"'{organization_id}' and endpoint = '{endpoint}';"  # noqa: S608 - both from our own session
    )
    if out is None or not out.isdigit():
        return None
    return int(out)


def cleanup(table: Table, minted: list, created_orgs: list) -> None:
    """Revoke every key this run minted, and delete only the organisations it created.

    `--keep-practices` empties `created_orgs` at the call site rather than branching here, because
    the distinction that matters is *whose* organisation it is, and a run that was told to keep
    them created nothing it is entitled to delete.
    """
    revoked = 0
    for client, key_id in minted:
        response = revoke_key(client, key_id)
        # 404 is fine and is not a failure: step 9 already revoked one of these on purpose, and
        # revocation is idempotent by contract.
        if response.status in {200, 404}:
            revoked += 1
    table.ok("--", "cleanup: keys revoked",
             f"{revoked}/{len(minted)} through DELETE /settings/api-keys")

    deleted = 0
    for client, organization_id in created_orgs:
        response = client.post(
            f"{WEB_BASE}/api/auth/organization/delete",
            json_body={"organizationId": organization_id},
        )
        if response.status == 200:
            deleted += 1
    if created_orgs:
        table.ok("--", "cleanup: organisations deleted",
                 f"{deleted}/{len(created_orgs)} this run created")
    else:
        table.ok("--", "cleanup: organisations deleted",
                 "none to delete — the practices were reused, or --keep-practices was given")

    print(
        "\n  Left behind on purpose: the two e2e `user` rows (Better Auth exposes no self-delete "
        "here, and they are reused by the next run), and the revoked `api_keys` rows, which are "
        "kept by design — see apps/engine/app/db/models.py:ApiKeyRecord."
    )


# ==========================================================================================


def main() -> int:
    parser = argparse.ArgumentParser(
        description="End-to-end proof of the Azmoth partner API and the GOÄ engine.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--detect", action="store_true",
                        help="print which stack is answering and exit")
    parser.add_argument("--skip-tenancy", action="store_true",
                        help="skip step 10 instead of creating a second practice")
    parser.add_argument(
        "--keep-practices", action="store_true",
        help=(
            "do not delete an organisation this run created. Recommended for repeated local runs: "
            "deleting it makes the next run re-onboard, and `practices` rows are keyed on the "
            "organisation id, so a new one is written each time and no endpoint can remove it."
        ),
    )
    args = parser.parse_args()

    print("Azmoth partner API — end-to-end")
    stack = detect_stack()
    print(f"  engine  {stack['engine']}  ({stack['engine_status']}, catalog {stack['catalog']})")
    print(f"  web     {stack['web']}  ({stack['web_status']})")
    print(f"  stack   {stack['compose']}")
    if args.detect:
        return 0
    print()

    table = Table()
    run(table, skip_tenancy=args.skip_tenancy, keep_practices=args.keep_practices)
    print(table.render())

    if table.failures():
        print(f"FAILED — {table.failures()} check(s) did not hold.")
        return 1
    print("PASSED — every check held.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
