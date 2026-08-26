#!/usr/bin/env node
/**
 * Refuse to start when the container's `node_modules` is older than the mounted source.
 *
 * `docker-compose.dev.yml` bind-mounts the working tree over the image's copy of it and then masks
 * `node_modules` with an **anonymous volume**, so the container runs current code against whatever
 * `pnpm install` put there when that volume was first created. Add a dependency, and
 * `docker compose up` starts a container whose code imports a package it does not have.
 *
 * The engine has the same trap and `apps/engine/scripts/check_deps.py` is this file's counterpart —
 * but the *fix* differs, and that is the whole reason this exists separately rather than the README
 * saying "rebuild". The engine keeps its packages in an image layer, so `--build` refreshes them.
 * An anonymous volume is **preserved across container recreation**, so `--build` does nothing for
 * this app: the new image is built, the container is replaced, and the same stale volume is mounted
 * back over it. `--renew-anon-volumes` is what replaces it, and nothing about the failure hints at
 * that.
 *
 * The failure is also bad out of proportion to its cause. `next dev` catches the resolution error
 * per request, answers 404, and stays up — so `docker ps` reports `Up (unhealthy)` rather than a
 * crash, the healthcheck fails forever, and the missing package name is one line inside a repeating
 * error. This turns that into a refusal that names the packages and the command.
 *
 * ## What it checks, and what it deliberately does not
 *
 * Presence, and the major version. Every declared dependency has to resolve, and for a `^`, `~` or
 * exact range the installed major has to match (`~` also checks the minor). A drift *inside* a
 * caret range is not reported: catching it would mean implementing semver range satisfaction, and
 * this exists to catch the common case loudly rather than to reimplement a resolver — the same
 * bargain `check_deps.py` strikes by looking only at `==` pins.
 *
 * `workspace:*` dependencies are skipped: they are symlinks into the bind-mounted source, so they
 * are as current as the working tree by construction and have no installed version to compare.
 *
 * Exit 0 if everything resolves, 1 if anything is missing or a major behind. Set CHECK_DEPS=false
 * to start anyway.
 */

import { existsSync, readFileSync } from "node:fs"
import path from "node:path"
import process from "node:process"

const APP_DIR = path.resolve(import.meta.dirname, "..")
const MANIFEST = path.join(APP_DIR, "package.json")

/**
 * The installed version of one package, or `null` if it is not there.
 *
 * Walked on disk rather than asked of `require.resolve`, and that is not a stylistic preference: a
 * package with a strict `exports` map does not publish `./package.json`, so resolving it throws for
 * `better-auth`, `next-themes` and `@tailwindcss/postcss` — three packages that are installed and
 * working. Resolving the *entry point* instead has the mirror problem, since a package whose only
 * export is CSS has no entry point Node will load. The directory on disk is the fact both of those
 * are proxies for.
 *
 * pnpm puts a symlink at `node_modules/<name>` pointing into its store, and these calls follow it.
 * The walk continues up to the filesystem root because pnpm hoists some packages to the workspace's
 * own `node_modules` rather than the app's.
 */
function installedVersion(name) {
  for (let dir = APP_DIR; ; dir = path.dirname(dir)) {
    const manifest = path.join(dir, "node_modules", name, "package.json")
    if (existsSync(manifest)) {
      try {
        return JSON.parse(readFileSync(manifest, "utf8")).version ?? "unknown"
      } catch {
        return "unreadable"
      }
    }
    if (path.dirname(dir) === dir) return null
  }
}

/** `^1.7.1` → `{ operator: "^", major: 1, minor: 7 }`. `null` for anything not worth guessing at. */
function parseRange(range) {
  const match = /^([\^~]?)(\d+)\.(\d+)\.(\d+)/.exec(range.trim())
  if (!match) return null
  return { operator: match[1], major: Number(match[2]), minor: Number(match[3]) }
}

function main() {
  const manifest = JSON.parse(readFileSync(MANIFEST, "utf8"))
  const declared = { ...manifest.dependencies, ...manifest.devDependencies }

  const problems = []
  let checked = 0

  for (const [name, range] of Object.entries(declared)) {
    if (typeof range !== "string" || range.startsWith("workspace:")) continue
    checked += 1

    const installed = installedVersion(name)
    if (installed === null) {
      problems.push(`  ${name}@${range} is declared but NOT INSTALLED`)
      continue
    }

    const want = parseRange(range)
    const have = parseRange(installed)
    if (!want || !have) continue
    if (want.major !== have.major || (want.operator === "~" && want.minor !== have.minor)) {
      problems.push(`  ${name}: container has ${installed}, package.json wants ${range}`)
    }
  }

  if (problems.length === 0) return 0

  process.stderr.write(
    `\ncheck-deps: this container's node_modules is out of date with apps/web/package.json ` +
      `(${problems.length} of ${checked} dependencies do not match):\n` +
      problems.join("\n") +
      "\n\nThe source is bind-mounted but the packages are not, so the container is running the" +
      "\nworking tree's code against an older install." +
      "\n\n`--build` alone will NOT fix this. node_modules lives in an anonymous volume, which" +
      "\ncompose keeps when it recreates the container — so a fresh image gets the same stale" +
      "\nvolume mounted back over it. Renew the volume as well:" +
      "\n\n    docker compose -f infra/docker/docker-compose.dev.yml up --build --renew-anon-volumes" +
      "\n\nNamed volumes are untouched by that flag, so the Postgres data survives it." +
      "\n\n(Set CHECK_DEPS=false to start anyway.)\n",
  )
  return 1
}

process.exit(main())
