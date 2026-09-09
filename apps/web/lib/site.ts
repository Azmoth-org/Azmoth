/**
 * The handful of externally-facing URLs the public `/demo` surface links to, in one place.
 *
 * `apps/marketing/src/lib/site.ts` and `apps/docs/lib/site.ts` centralise their cross-origin
 * links the same way, for the same reason: spreading `process.env.NEXT_PUBLIC_X` across every
 * `href` is how a button quietly loses its destination when nobody notices the variable was never
 * set.
 *
 * `NEXT_PUBLIC_*` is read with plain dot access (not the `optionalEnv()` helper in
 * `@/lib/auth-db.ts`, which indexes by name) because Next.js only inlines the literal
 * `process.env.NEXT_PUBLIC_X` expression at build time — a dynamic lookup would still work on the
 * server but silently resolve to `undefined` in the client bundle, and `start-demo-button.tsx` is
 * a client component. The blank-string guard below reuses `optionalEnv()`'s reasoning: Compose and
 * most `.env` loaders write an unset variable through as `""`, not as a missing key.
 */

function publicEnv(value: string | undefined): string | undefined {
  return value !== undefined && value.trim() !== "" ? value : undefined
}

/** Where the `/demo` CTAs send a visitor to book a call, instead of self-serving into the app. */
export function getCalComUrl(): string {
  return publicEnv(process.env.NEXT_PUBLIC_CAL_COM_URL) ?? "https://cal.com/azmoth"
}
