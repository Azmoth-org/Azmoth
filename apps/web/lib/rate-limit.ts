/**
 * A per-IP request budget for the credential endpoints, held in this process's memory.
 *
 * ## What it is for, and what it is not for
 *
 * It exists to make online password guessing expensive. Five attempts a minute turns an
 * eight-character-password search from a weekend into geological time, and it does so without a
 * dependency, a migration or an operational surface — which is the trade this pilot wants.
 *
 * It is **not** a general API rate limiter and must not become one. It counts in a `Map` in one
 * Node process, so:
 *
 * - **It resets on deploy.** Every container restart empties the budget. For brute-force defence
 *   that is a rounding error; for anything billed or contractual it would be a hole.
 * - **It does not span instances.** Two web containers behind the same Caddy give an attacker
 *   2 × 5 attempts a minute. Today there is exactly one (`infra/docker/docker-compose.yml`
 *   declares a single `web` service), so this is a note about what would have to change rather
 *   than a bug — the moment a second replica exists, this needs a shared store and the honest
 *   options are Redis or Better Auth's own database-backed limiter.
 * - **It is per IP, so it is per NAT gateway too.** A practice behind one public address shares a
 *   budget. Five a minute is set where it is partly for that reason: it is generous enough that a
 *   waiting room full of staff signing in does not collide, and mean enough that a script does.
 *
 * The engine has the same shape of control in `app/api/ratelimit.py` for its partner API. This one
 * is separate rather than shared because the two limit different things for different reasons — one
 * meters a paying integration by API key, this one blunts password guessing by address.
 *
 * ## Why a sliding window rather than a fixed one
 *
 * A fixed window resets on the minute, so an attacker who sends five at 11:59.9 and five at 12:00.1
 * gets ten in 200 ms while never exceeding "five per minute". Keeping the timestamps and discarding
 * the expired ones costs at most `LIMIT` numbers per address and removes that edge entirely. At
 * five entries per IP the "cheaper" option is not measurably cheaper.
 *
 * ## Memory is bounded on purpose
 *
 * An unbounded `Map` keyed by client IP is a denial-of-service primitive: an attacker with a wide
 * source range fills the heap by making one request from each address. `MAX_TRACKED_CLIENTS` and
 * the sweep in `prune` are what stop that, and the eviction policy is chosen to fail in the safe
 * direction — see `evictOldest`.
 */

/** Requests allowed per window, per client address. */
export const LIMIT = 5

/** The window, in milliseconds. */
export const WINDOW_MS = 60_000

/**
 * How many addresses are tracked at once.
 *
 * Ten thousand entries of at most five numbers each is a couple of megabytes — small beside a Node
 * heap, and far above the number of distinct addresses a pilot with a few dozen practices sees in
 * any minute. The cap is not sized for normal traffic; it is sized so that abnormal traffic hits a
 * ceiling instead of the heap.
 */
const MAX_TRACKED_CLIENTS = 10_000

/**
 * Timestamps of the recent attempts from each address, oldest first.
 *
 * Module scope, so it survives between requests within one server instance and is garbage collected
 * with it. There is deliberately no persistence: see the header note on what resets mean here.
 */
const attempts = new Map<string, number[]>()

/** When the last sweep ran, so a burst of requests does not each walk the whole map. */
let lastSweep = 0

/** How often the opportunistic sweep is allowed to run. */
const SWEEP_INTERVAL_MS = WINDOW_MS

/**
 * Drop addresses whose entries have all expired, at most once per window.
 *
 * Called from the request path rather than from a timer, because a timer holding a reference to
 * this module keeps it alive in ways that are awkward in a serverless or Edge isolate and buy
 * nothing: an entry that is never swept is also never read, and costs only its own bytes.
 */
function prune(now: number): void {
  if (now - lastSweep < SWEEP_INTERVAL_MS) return
  lastSweep = now

  for (const [key, timestamps] of attempts) {
    // Only the last one needs checking: the array is append-ordered, so if the newest has expired
    // then so has everything before it.
    const newest = timestamps[timestamps.length - 1]
    if (newest === undefined || now - newest >= WINDOW_MS) {
      attempts.delete(key)
    }
  }
}

/**
 * Make room by dropping the least recently active address.
 *
 * **This is the failure mode worth being explicit about.** Evicting an entry forgives whatever that
 * address had spent, so an attacker who can push the map past its cap can buy themselves a reset —
 * but only by making requests from more than ten thousand distinct addresses inside one minute,
 * and only to reset the address that has been quietest, which is the least likely to be theirs.
 * Choosing the *oldest* rather than a random or newest entry is what makes that true: the addresses
 * an attacker is actively spending from are the ones this will not touch.
 *
 * The alternative — refusing all new addresses once full — turns the same flood into a total
 * lockout of every legitimate practice, which is a worse outcome than a partially forgiven budget.
 */
function evictOldest(): void {
  let oldestKey: string | null = null
  let oldestSeen = Infinity

  for (const [key, timestamps] of attempts) {
    const newest = timestamps[timestamps.length - 1] ?? 0
    if (newest < oldestSeen) {
      oldestSeen = newest
      oldestKey = key
    }
  }

  if (oldestKey !== null) attempts.delete(oldestKey)
}

/**
 * The client's address, as reported by the proxy in front of this process.
 *
 * **The last entry of `X-Forwarded-For`, not the first, and the difference is the whole point of
 * this function.** The header is a list that each hop appends to, so a client is free to arrive
 * having already sent `X-Forwarded-For: 1.2.3.4`; Caddy appends the address it actually sees, and
 * the result is `1.2.3.4, <real client>`. Reading the *first* entry — which is the conventional
 * "original client" reading, and is correct when you trust every hop — would mean an attacker
 * picks their own rate-limit bucket, and defeats this file entirely by incrementing a counter in
 * a header. The last entry is the only one no client can write, because our own proxy wrote it.
 *
 * This is therefore correct **only** because exactly one trusted proxy sits in front: Caddy, in
 * `infra/docker/Caddyfile`, and the engine's port is not published (`docker-compose.azure.yml`
 * resets it). Putting a second proxy or a CDN in front of Caddy would add a hop, and the address to
 * trust would become the second-to-last. That is a change to make deliberately, here.
 *
 * Returns `null` when no proxy header is present at all, which in this deployment means the request
 * did not come through Caddy — see the caller for why that is not treated as exempt.
 */
export function clientAddress(headers: Headers): string | null {
  const forwarded = headers.get("x-forwarded-for")
  if (forwarded) {
    const hops = forwarded
      .split(",")
      .map((hop) => hop.trim())
      .filter(Boolean)
    const nearest = hops[hops.length - 1]
    if (nearest) return nearest
  }

  // Caddy does not set this, but a different proxy might, and it carries a single value rather than
  // a list so there is no hop to choose. Checked second precisely because it is not what our own
  // proxy sends.
  const real = headers.get("x-real-ip")?.trim()
  return real ? real : null
}

/** What `consume` decided, and the numbers a caller needs to build headers from it. */
export interface RateLimitDecision {
  allowed: boolean
  /** Requests still available in the current window. Zero on a refusal. */
  remaining: number
  /** Seconds until the oldest counted attempt expires. At least 1 on a refusal. */
  retryAfterSeconds: number
  /** The window's ceiling, echoed so a caller need not import `LIMIT` to render a header. */
  limit: number
}

/**
 * Record one attempt from `key` and say whether it is allowed.
 *
 * A refused attempt is **not** recorded, which is a deliberate choice and the opposite of what some
 * limiters do. Counting refusals would mean a client that keeps retrying pushes its own unlock
 * further away every time — the window never empties, and a legitimate user who fat-fingers a
 * password and then retries twice is locked out for far longer than a minute with nothing on screen
 * explaining why. Refusing without recording means the budget always recovers `WINDOW_MS` after the
 * last *accepted* attempt, which is what the `Retry-After` header then truthfully promises.
 */
export function consume(key: string, now: number = Date.now()): RateLimitDecision {
  prune(now)

  const cutoff = now - WINDOW_MS
  const recent = (attempts.get(key) ?? []).filter((at) => at > cutoff)

  if (recent.length >= LIMIT) {
    const oldest = recent[0] as number
    // Round up, and never below 1: a `Retry-After: 0` invites an immediate retry that is certain to
    // be refused again, and `Math.ceil` of 200 ms is 1 rather than 0.
    const retryAfterSeconds = Math.max(1, Math.ceil((oldest + WINDOW_MS - now) / 1000))
    // Write the filtered array back even on a refusal, so the expired entries are not re-filtered
    // on every subsequent request from an address that is being hammered.
    attempts.set(key, recent)
    return { allowed: false, remaining: 0, retryAfterSeconds, limit: LIMIT }
  }

  recent.push(now)

  if (!attempts.has(key) && attempts.size >= MAX_TRACKED_CLIENTS) {
    evictOldest()
  }
  attempts.set(key, recent)

  return {
    allowed: true,
    remaining: LIMIT - recent.length,
    retryAfterSeconds: 0,
    limit: LIMIT,
  }
}

/** Forget every recorded attempt. Tests only — there is no operational reason to clear this. */
export function reset(): void {
  attempts.clear()
  lastSweep = 0
}
