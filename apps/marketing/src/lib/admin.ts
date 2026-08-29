type SessionLike = {
  user?: {
    id?: string;
    email?: string | null;
    role?: string | null;
  } | null;
} | null;

/**
 * Admin check used by both API routes and the agency console.
 * A user is admin if their role is "admin", or their email is in the
 * ADMIN_EMAILS comma-separated env var (useful for bootstrapping the
 * first admin before role management exists).
 */
export function isAdmin(session: SessionLike): boolean {
  if (!session?.user?.id) return false;
  if (session.user.role === "admin") return true;
  const allowed = (process.env.ADMIN_EMAILS || "")
    .split(",")
    .map((e) => e.trim().toLowerCase())
    .filter(Boolean);
  return allowed.includes((session.user.email || "").toLowerCase());
}
