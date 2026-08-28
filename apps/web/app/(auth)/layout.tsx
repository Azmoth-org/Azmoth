import type { Metadata } from "next"

/**
 * The signed-out half: `/login` and `/signup`, and nothing else.
 *
 * Deliberately not the app shell. A sidebar full of links to screens the visitor cannot open is
 * worse than no sidebar — it says "you are inside the application" to somebody who is not, and
 * every one of those links bounces straight back to this page.
 *
 * It renders its children and no markup of its own. The frame both screens share — the wordmark,
 * the column widths, the disclaimer, the panel on the right — is `components/auth/auth-shell.tsx`,
 * and it has to be a component rather than this layout because it is a full-bleed two-column grid
 * that owns `min-h-svh` itself. A layout that also centred and padded would be fighting it. What is
 * left here is the part that genuinely belongs to the route segment rather than to the page:
 * `robots`, stated because a login form is the one page here with a public URL, and an indexed one
 * advertises that this deployment exists to anyone searching for the product name.
 */
export const metadata: Metadata = {
  robots: { index: false, follow: false },
}

export default function AuthLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return <>{children}</>
}
