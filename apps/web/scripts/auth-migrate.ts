/**
 * Create (or update) Better Auth's tables in the accounts database.
 *
 *     pnpm --filter web auth:migrate          apply
 *     pnpm --filter web auth:migrate --dry    print the SQL and change nothing
 *
 * ## Why this exists rather than `npx @better-auth/cli migrate`
 *
 * The published CLI tracks its own release line and currently resolves an older `@better-auth/core`
 * than the library this app depends on, which fails at import. More importantly, a CLI that pulls
 * its *own* copy of Better Auth would compute the schema from that copy — so the tables could be
 * built for a version the application does not run. This calls `getMigrations` from the very
 * instance `lib/auth.ts` configures, so what is created is by construction what the running app
 * expects, plugins and field overrides included.
 *
 * ## What it touches, and what it must not
 *
 * `user`, `session`, `account`, `verification` — and only those. It is Kysely's `CREATE TABLE` for
 * whatever is missing plus `ALTER TABLE ADD COLUMN` for fields a Better Auth upgrade introduced;
 * it never drops anything, and it does not know the engine's tables exist. Those are Alembic's
 * (`apps/engine/alembic/`), which correspondingly excludes these four from autogenerate. Two
 * migrators, one database, disjoint table sets — see `lib/auth-db.ts` for why they share it.
 *
 * `--dry` prints the statements instead of executing them. Run it first against anything that holds
 * accounts: this is the only preview there is, because unlike Alembic there is no migration file to
 * read in a diff.
 */

import { getMigrations } from "better-auth/db/migration"

import { getAuth } from "../lib/auth"

async function main(): Promise<void> {
  const dry = process.argv.includes("--dry")

  const {
    toBeCreated,
    toBeAdded,
    unsafeChanges,
    runMigrations,
    compileMigrations,
  } = await getMigrations(getAuth().options, { throwOnUnsafe: !dry })

  if (toBeCreated.length === 0 && toBeAdded.length === 0) {
    console.log("Better Auth: schema is already up to date. Nothing to do.")
    return
  }

  for (const { table, fields } of toBeCreated) {
    console.log(`create table ${table} (${Object.keys(fields).join(", ")})`)
  }
  for (const { table, fields } of toBeAdded) {
    console.log(`alter table ${table} add ${Object.keys(fields).join(", ")}`)
  }

  // Reported rather than swallowed: a required column with no default cannot be added to a table
  // that already has rows, and the honest answer is to say so and let a person decide the backfill.
  for (const change of unsafeChanges) {
    console.warn(`refused as unsafe: ${change}`)
  }

  if (dry) {
    console.log("\n-- SQL (dry run, nothing executed) --\n")
    console.log(await compileMigrations())
    return
  }

  await runMigrations()
  console.log("Better Auth: schema applied.")
}

main().then(
  () => process.exit(0),
  (error: unknown) => {
    console.error(error)
    process.exit(1)
  }
)
