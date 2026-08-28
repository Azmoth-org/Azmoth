/**
 * SQL against the two business tables, on whichever backend this deployment runs. **Server-only.**
 *
 * ## What this is for, and what it is not
 *
 * `doctor_profiles` and `practices` are Alembic's — declared in `apps/engine/app/db/models.py` and
 * created by `alembic upgrade head`, in the same database Better Auth keeps its accounts in (see
 * `lib/auth-db.ts` for why one database). Nothing in the engine reads them yet, and the web tier is
 * the only writer, so the choice was between a pair of new engine endpoints and reaching the two
 * tables directly on the connection this process already holds. This is the second option, and it
 * is deliberately narrow: **a route handler must not import this to invent a query.** Every
 * statement lives in `lib/onboarding/store.ts`, so the set of SQL this application runs is a file
 * somebody can read, and everything else goes through `/api/engine/*` where the engine owns it.
 *
 * ## Two dialects, and the three things that differ
 *
 * The engine is developed against SQLite and deployed against Postgres — `apps/engine/app/db/base.py`
 * says the same thing from the other side — so anything written here has to mean the same in both.
 * Three differences are not papered over anywhere else, so they are handled here:
 *
 * **Placeholders.** `pg` numbers them (`$1`), `better-sqlite3` does not (`?`). Statements are
 * written with `?` and rewritten on the way to Postgres, because `?` is the form that reads and
 * because renumbering by hand after inserting a column is how a query comes to bind the wrong value
 * to the wrong column without failing.
 *
 * **UUIDs.** SQLAlchemy's `Uuid(native_uuid=True)` is Postgres' native `uuid` and `CHAR(32)`
 * everywhere else — and on SQLite it stores the *hex*, dashes stripped. A canonical UUID string
 * written into that column would be 36 characters where every row Alembic's own code writes is 32,
 * and the two would never match on a lookup. `newId` produces the right shape for the dialect and
 * `formatUuid` puts it back into canonical form on the way out, so the id in an API response does
 * not change format depending on where the application is running.
 *
 * **Timestamps.** Postgres has `TIMESTAMP WITH TIME ZONE` and SQLite has no timestamp type at all,
 * so SQLAlchemy writes a naive string that is UTC by convention (`app.db.models.utcnow`, and
 * `as_utc` re-attaching the zone on the way back). `nowStamp` writes the same convention from this
 * side — a row inserted here has to be indistinguishable from one inserted by the engine, or the
 * first `ORDER BY created_at` that mixes them sorts wrongly by an hour twice a year.
 */

import { randomUUID } from "node:crypto"

import { databaseDriver } from "@/lib/auth-db"

/** What a parameter may be. Deliberately no `Date` — see `nowStamp` for why. */
export type SqlValue = string | number | null

/** One row, as the driver handed it back. Values are narrowed by the caller that knows the table. */
export type SqlRow = Record<string, unknown>

/** Which backend is behind `query`. Callers need it for the two literals below, not for branching. */
export function dialect(): "postgres" | "sqlite" {
  return databaseDriver().kind
}

/**
 * Run one statement and return its rows. `?` placeholders, in order.
 *
 * Parameters are always bound, never interpolated — a LANR and a practice name are user input, and
 * a template literal here would be an injection into a database that also holds the session table.
 *
 * `RETURNING` works on both backends (SQLite has had it since 3.35 and `better-sqlite3` bundles far
 * newer), which is what lets an upsert answer with the row it wrote instead of costing a second
 * round-trip to read back what was just written.
 */
export async function query<T extends SqlRow>(
  sql: string,
  params: readonly SqlValue[] = []
): Promise<T[]> {
  const driver = databaseDriver()

  if (driver.kind === "postgres") {
    const result = await driver.pool.query(toNumberedPlaceholders(sql), [
      ...params,
    ])
    return result.rows as T[]
  }

  // Synchronous, and that is fine: `better-sqlite3` is the development path only, and awaiting a
  // resolved value costs a microtask rather than a thread.
  //
  // `.all()` on a statement that returns nothing is a `TypeError` from the driver rather than an
  // empty array — an asymmetry `pg` does not have, since it answers every statement with a result
  // object. `reader` is how the driver says which kind it prepared, so a DELETE or an UPDATE with
  // no RETURNING goes through `.run()` and comes back as no rows, which is what it is.
  const statement = driver.db.prepare(sql)
  if (!statement.reader) {
    statement.run(...params)
    return []
  }
  return statement.all(...params) as T[]
}

/**
 * `?, ?, ?` → `$1, $2, $3`, leaving anything inside a quoted string alone.
 *
 * The scan is what makes that last clause true. A naive `replace(/\?/g, …)` would renumber a
 * question mark inside a string literal — `'Wie bitte?'` — and produce a statement whose parameter
 * count no longer matches its arguments, which `pg` reports as a bind mismatch several columns away
 * from the actual mistake. Single quotes are the only string form SQL has here, and a doubled quote
 * (`'it''s'`) is an escaped quote rather than the end of one, which falls out of this loop for free:
 * the closing quote flips the flag off and the immediately following one flips it back on.
 */
export function toNumberedPlaceholders(sql: string): string {
  let out = ""
  let index = 0
  let inString = false

  for (const character of sql) {
    if (character === "'") inString = !inString
    if (character === "?" && !inString) {
      index += 1
      out += `$${index}`
      continue
    }
    out += character
  }

  return out
}

/**
 * A primary key in the form this dialect's `id` column stores.
 *
 * Canonical on Postgres, 32 hex characters on SQLite — see the module docstring. Generated here
 * rather than left to a column default because neither table has one: Alembic declares
 * `default=uuid.uuid4` on the *mapper*, which is Python-side and does nothing for a statement that
 * did not come from SQLAlchemy.
 */
export function newId(): string {
  const id = randomUUID()
  return dialect() === "sqlite" ? id.replace(/-/g, "") : id
}

/** Canonical `8-4-4-4-12`, whichever form the row came back in. Non-UUID input is returned as-is. */
export function formatUuid(value: unknown): string {
  const raw = typeof value === "string" ? value : String(value ?? "")
  if (!/^[0-9a-f]{32}$/i.test(raw)) return raw
  return [
    raw.slice(0, 8),
    raw.slice(8, 12),
    raw.slice(12, 16),
    raw.slice(16, 20),
    raw.slice(20),
  ].join("-")
}

/**
 * Now, in the literal this dialect's timestamp columns hold.
 *
 * ISO 8601 with the zone for Postgres, which parses it into `timestamptz`. For SQLite, the exact
 * shape SQLAlchemy writes — `YYYY-MM-DD HH:MM:SS.ffffff`, naive, UTC by convention — because the
 * column is TEXT underneath and rows are compared and ordered as strings. An ISO string with a `T`
 * and a `Z` in that column would sort *after* every row the engine wrote, forever.
 *
 * A string rather than a `Date` for the additional reason that `better-sqlite3` refuses to bind a
 * `Date` at all; making the value explicit here is better than discovering that at the call site.
 */
export function nowStamp(): string {
  const now = new Date()
  if (dialect() === "postgres") return now.toISOString()
  return `${now.toISOString().replace("T", " ").replace("Z", "")}000`
}

/**
 * Read a timestamp column back as an ISO 8601 instant, whichever dialect produced it.
 *
 * `pg` hands back a `Date`; SQLite hands back the naive UTC string above, which `new Date(...)`
 * would otherwise read as *local* time — the classic way an audit timestamp lands an hour out. The
 * `Z` is appended before parsing to say what the convention already guarantees.
 */
export function toIso(value: unknown): string {
  if (value instanceof Date) return value.toISOString()
  if (typeof value !== "string") return new Date(0).toISOString()
  const normalised = value.includes("T") ? value : value.replace(" ", "T")
  const withZone = /(?:Z|[+-]\d{2}:?\d{2})$/.test(normalised)
    ? normalised
    : `${normalised}Z`
  const parsed = new Date(withZone)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toISOString()
}

/**
 * The column a unique index refused this write on, or `null` if that is not what went wrong.
 *
 * Both drivers say so and neither says it the same way: Postgres raises SQLSTATE `23505` with the
 * *index* name in `constraint`, SQLite raises `SQLITE_CONSTRAINT_UNIQUE` with `table.column` in the
 * message. Both are normalised to the column name, because that is what a caller needs in order to
 * answer "diese LANR ist bereits vergeben" rather than a generic 500 — a duplicate LANR is the one
 * failure onboarding can actually expect, and it deserves a sentence rather than a stack trace.
 *
 * Index names are the ones `alembic/versions/20260828_0005_practice_identity.py` creates. A future
 * migration that renames one degrades this to `null`, which costs the specific message and nothing
 * else: the caller still refuses the write.
 */
export function uniqueViolationColumn(error: unknown): string | null {
  if (typeof error !== "object" || error === null) return null
  const candidate = error as {
    code?: unknown
    constraint?: unknown
    message?: unknown
  }

  if (candidate.code === "23505") {
    const constraint =
      typeof candidate.constraint === "string" ? candidate.constraint : ""
    // `ix_doctor_profiles_lanr` → `lanr`, and `..._user_id` / `..._organization_id` likewise.
    const match = /^ix_(?:doctor_profiles|practices)_(.+)$/.exec(constraint)
    return match?.[1] ?? null
  }

  if (candidate.code === "SQLITE_CONSTRAINT_UNIQUE") {
    const message =
      typeof candidate.message === "string" ? candidate.message : ""
    // "UNIQUE constraint failed: doctor_profiles.lanr"
    const match = /UNIQUE constraint failed: \w+\.(\w+)/.exec(message)
    return match?.[1] ?? null
  }

  return null
}
