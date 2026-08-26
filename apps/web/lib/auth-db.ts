/**
 * The connection Better Auth keeps its users, sessions and credentials in. **Server-only.**
 *
 * ## One database, two tiers
 *
 * The accounts live in the *same* database as the proposals and the audit log, rather than in one
 * of their own. That is the whole point of the design: `audit_events.actor` and
 * `proposals.created_by` hold a Better Auth `user.id`, and "who approved this invoice" has to be
 * answerable by a join rather than by correlating two systems that can disagree. A second database
 * would make every attribution question a distributed one.
 *
 * The two tiers reach it with different drivers, and neither manages the other's tables: Alembic
 * owns `proposals`, `audit_events`, `batch_jobs`, `batch_files` and `rule_reviews`
 * (`apps/engine/alembic/`), Better Auth owns `user`, `session`, `account` and `verification`.
 * `apps/engine/alembic/env.py` names the second set explicitly so that an `--autogenerate` run can
 * never propose dropping them.
 *
 * ## Why the URL is parsed rather than passed through
 *
 * The engine's `DATABASE_URL` is a *SQLAlchemy* URL — the Python driver is part of the value:
 *
 *     postgresql+asyncpg://user:pw@host:5432/govatax
 *     sqlite+aiosqlite:///./test.db
 *
 * Neither form means anything to `pg` or to `better-sqlite3`. Accepting them anyway is deliberate:
 * a deployment should be able to set one connection string for both tiers and have them land in
 * the same place, and requiring two spellings of one fact is how they end up pointing at two
 * different databases. `normaliseDatabaseUrl` strips the `+driver` suffix; a plain
 * `postgres://…` or `postgresql://…` passes through untouched.
 */

import path from "node:path"

import type { BetterAuthOptions } from "better-auth"
import BetterSqlite3 from "better-sqlite3"
import { Pool } from "pg"

/**
 * What Better Auth accepts as its `database`: a driver instance, a Kysely dialect, or an adapter.
 *
 * `authDatabase` is annotated with this rather than with `Pool | BetterSqlite3.Database`, and the
 * reason is a TypeScript emit rule rather than taste. `@types/better-sqlite3` puts the instance
 * type inside a namespace (`BetterSqlite3.Database`) that another module's generated declaration
 * cannot name — and `lib/auth.ts` exports `auth`, whose inferred type would have to mention it.
 * Widening to the option type the library already publishes keeps the declaration writable, and is
 * in any case the more honest signature: what this function returns is "something Better Auth can
 * be configured with".
 */
type AuthDatabase = NonNullable<BetterAuthOptions["database"]>

/** What `AUTH_DATABASE_URL` (or `DATABASE_URL`) resolved to, once the Python driver is stripped. */
type Resolved =
  | { kind: "postgres"; url: string }
  | { kind: "sqlite"; file: string }

/**
 * Where the accounts go when nothing is configured.
 *
 * The engine's own default is `sqlite+aiosqlite:///./test.db`, relative to the directory `uvicorn`
 * is started in — which is `apps/engine`. So the development default here is that same file,
 * reached from the web app's working directory, and a developer who runs both with no configuration
 * gets one database rather than two.
 *
 * It is a development convenience and nothing more: `resolveDatabase` refuses to fall back to it
 * when `NODE_ENV` is `production`, for the same reason the engine refuses `DATABASE_AUTO_CREATE`
 * there. A production stack that quietly wrote its user accounts to a SQLite file beside the
 * container's working directory would lose every one of them on the next deploy.
 */
const DEVELOPMENT_SQLITE_FILE = path.join(process.cwd(), "..", "engine", "test.db")

/** `postgresql+asyncpg://…` → `postgresql://…`; `sqlite+aiosqlite:///x` → `sqlite:///x`. */
export function normaliseDatabaseUrl(raw: string): string {
  return raw.replace(/^([a-z0-9]+)\+[a-z0-9_]+:/i, "$1:")
}

/** Read one connection string into something a Node driver can be built from. */
export function parseDatabaseUrl(raw: string): Resolved {
  const url = normaliseDatabaseUrl(raw.trim())

  if (url.startsWith("postgres://") || url.startsWith("postgresql://")) {
    return { kind: "postgres", url }
  }

  if (url.startsWith("sqlite:")) {
    // SQLAlchemy writes the path after three slashes — `sqlite:///./test.db` is relative,
    // `sqlite:////var/lib/x.db` is absolute — and `:memory:` is its own thing. A URL object would
    // mangle all three, so the prefix is taken off by hand.
    const file = url.replace(/^sqlite:\/{2,3}/, "")
    if (file === ":memory:") {
      throw new Error(
        "AUTH_DATABASE_URL is an in-memory SQLite database. Sessions written to it vanish when " +
          "the process restarts, so every user would be signed out by a deploy. Name a file.",
      )
    }
    return { kind: "sqlite", file: path.resolve(file) }
  }

  // The scheme, never the whole value: this string can carry a password, and an error that
  // reaches a log or a stack trace is the last place one belongs.
  const scheme = url.split(":")[0] ?? "(empty)"
  throw new Error(
    `AUTH_DATABASE_URL names the scheme "${scheme}". Better Auth speaks Postgres or SQLite here; ` +
      "the value must start with postgres://, postgresql:// or sqlite:/// (a SQLAlchemy +driver " +
      "suffix, as the engine's DATABASE_URL carries, is stripped for you).",
  )
}

/**
 * The database Better Auth is configured with, built once per process.
 *
 * A `Pool`, not a connection: Next runs many requests concurrently in one process, and a single
 * connection would serialise every session lookup behind whichever request holds it. `better-sqlite3`
 * is synchronous by design and has no pool to size — which is one more reason it is a development
 * default rather than a deployment target.
 */
export function authDatabase(): AuthDatabase {
  const configured = process.env.AUTH_DATABASE_URL ?? process.env.DATABASE_URL

  if (!configured) {
    if (process.env.NODE_ENV === "production") {
      throw new Error(
        "AUTH_DATABASE_URL is not set. In production the user accounts and sessions must live in " +
          "the same Postgres the engine writes proposals to — set it to the engine's DATABASE_URL " +
          "(the +asyncpg suffix is stripped for you). There is deliberately no SQLite fallback here.",
      )
    }
    return new BetterSqlite3(DEVELOPMENT_SQLITE_FILE)
  }

  const resolved = parseDatabaseUrl(configured)
  if (resolved.kind === "sqlite") {
    if (process.env.NODE_ENV === "production") {
      throw new Error(
        "AUTH_DATABASE_URL names a SQLite file and NODE_ENV is production. One writer, one file, " +
          "no replication and no encryption at rest is not where password hashes belong — the " +
          "engine refuses the same configuration for proposals. Point both at Postgres.",
      )
    }
    return new BetterSqlite3(resolved.file)
  }

  return new Pool({ connectionString: resolved.url })
}
