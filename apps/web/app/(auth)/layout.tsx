import type { Metadata } from "next"

/**
 * The signed-out half: `/login` and `/signup`, and nothing else.
 *
 * Deliberately not the app shell. A sidebar full of links to screens the visitor cannot open is
 * worse than no sidebar — it says "you are inside the application" to somebody who is not, and
 * every one of those links bounces straight back to this page. What it renders instead is a single
 * centred card on the application's own ground, which is also what makes the two screens legible on
 * a phone without any of the shell's off-canvas machinery.
 *
 * `robots` is stated because a login form is the one page here with a public URL, and an indexed
 * one advertises that this deployment exists to anyone searching for the product name.
 */
export const metadata: Metadata = {
  robots: { index: false, follow: false },
}

export default function AuthLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <div className="bg-muted/40 flex min-h-svh flex-col items-center justify-center gap-6 px-4 py-10">
      {children}
    </div>
  )
}
