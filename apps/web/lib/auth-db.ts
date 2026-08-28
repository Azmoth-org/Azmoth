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
 * owns `proposals`, `audit_events`, `batch_jobs`, `batch_files`, `rule_reviews`, `doctor_profiles`
 * and `practices` (`apps/engine/alembic/`), Better Auth owns `user`, `session`, `account`,
 * `verification` and the three the organization plugin brings. `apps/engine/alembic/env.py` names
 * the second set explicitly so that an `--autogenerate` run can never propose dropping them.
 *
 * The last two of Alembic's are the odd ones out, because the web tier *writes* them: they hold the
 * doctor and practice details `POST /api/onboarding` collects, and they are Alembic's because they
 * are business data and because a LANR is what a PADnext export will eventually have to carry. That
 * is why `databaseDriver` below is exported — `lib/db.ts` reaches those two tables through the very
 * handle Better Auth is holding, rather than opening a second one.
 *
 * ## Why the URL is parsed rather than passed through
 *
 * The engine's `DATABASE_URL` is a *SQLAlchemy* URL — the Python driver is part of the value:
 *
 *     postgresql+asyncpg://user:pw@host:5432/azmoth
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
const DEVELOPMENT_SQLITE_FILE = path.join(
  process.cwd(),
  "..",
  "engine",
  "test.db"
)

/**
 * One environment variable, or `undefined` when it is missing **or blank**.
 *
 * The blank half is the point. Compose writes an unconfigured variable through as an empty string
 * (`BETTER_AUTH_SECRET: "${BETTER_AUTH_SECRET:-}"`), as do Kubernetes manifests and most `.env`
 * loaders, so `process.env.X ?? fallback` reads a variable nobody set as *set to nothing* and skips
 * the fallback. Every caller here treats "not configured" as a real state with a defined behaviour —
 * derive the origin from the request, fall back to `DATABASE_URL`, refuse in production — and this
 * is what makes that state reachable from inside a container.
 */
export function optionalEnv(name: string): string | undefined {
  const value = process.env[name]
  return value !== undefined && value.trim() !== "" ? value : undefined
}

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
          "the process restarts, so every user would be signed out by a deploy. Name a file."
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
      "suffix, as the engine's DATABASE_URL carries, is stripped for you)."
  )
}

/**
 * The open handle, with its dialect still attached.
 *
 * Better Auth only needs the handle — it discovers the dialect itself. `lib/db.ts` needs both,
 * because the two business tables it reads are reached with SQL, and the placeholder syntax, the
 * UUID representation and the timestamp literal all differ between the two backends. Erasing the
 * distinction at this boundary would only mean re-deriving it there from the connection string.
 */
export type DatabaseDriver =
  | { kind: "postgres"; pool: Pool }
  | { kind: "sqlite"; db: BetterSqlite3.Database }

/** Opened on first use, then reused. See `databaseDriver`. */
let driver: DatabaseDriver | null = null

/**
 * The one connection this process holds to the accounts-and-business database.
 *
 * **Memoised, and shared with `lib/db.ts` rather than opened twice.** Better Auth resolves a
 * session on essentially every request, and the onboarding endpoint writes two rows in the same
 * database; two pools would double the connection count for no benefit and — worse on the SQLite
 * development path — mean two `better-sqlite3` handles on one file, which is how a write gets
 * `SQLITE_BUSY` from a process competing with itself.
 *
 * A `Pool`, not a connection: Next runs many requests concurrently in one process, and a single
 * connection would serialise every session lookup behind whichever request holds it. `better-sqlite3`
 * is synchronous by design and has no pool to size — which is one more reason it is a development
 * default rather than a deployment target.
 */
export function databaseDriver(): DatabaseDriver {
  if (driver) return driver

  const configured =
    optionalEnv("AUTH_DATABASE_URL") ?? optionalEnv("DATABASE_URL")

  if (!configured) {
    if (process.env.NODE_ENV === "production") {
      throw new Error(
        "AUTH_DATABASE_URL is not set. In production the user accounts and sessions must live in " +
          "the same Postgres the engine writes proposals to — set it to the engine's DATABASE_URL " +
          "(the +asyncpg suffix is stripped for you). There is deliberately no SQLite fallback here."
      )
    }
    driver = { kind: "sqlite", db: new BetterSqlite3(DEVELOPMENT_SQLITE_FILE) }
    return driver
  }

  const resolved = parseDatabaseUrl(configured)
  if (resolved.kind === "sqlite") {
    if (process.env.NODE_ENV === "production") {
      throw new Error(
        "AUTH_DATABASE_URL names a SQLite file and NODE_ENV is production. One writer, one file, " +
          "no replication and no encryption at rest is not where password hashes belong — the " +
          "engine refuses the same configuration for proposals. Point both at Postgres."
      )
    }
    driver = { kind: "sqlite", db: new BetterSqlite3(resolved.file) }
    return driver
  }

  driver = {
    kind: "postgres",
    pool: new Pool({ connectionString: resolved.url }),
  }
  return driver
}

/**
 * The database Better Auth is configured with — the handle from `databaseDriver`, dialect dropped.
 *
 * Called once, by `buildAuth()`, which `getAuth()` memoises.
 */
export function authDatabase(): AuthDatabase {
  const resolved = databaseDriver()
  return resolved.kind === "postgres" ? resolved.pool : resolved.db
}
