import { FileQuestionIcon } from "lucide-react"
import Link from "next/link"

import { Alert, AlertDescription, AlertTitle } from "@workspace/ui/components/alert"

import { NAV_ITEMS } from "@/components/layout/nav"

/**
 * An unknown path.
 *
 * It is the *root* not-found, which is the one Next.js serves for a URL that matches no route at
 * all — so it renders in the root layout and no longer inherits the app shell, which now lives in
 * `app/(app)/layout.tsx`. That is why it brings its own page frame and why the list of workspaces
 * below matters more than it used to: with no sidebar to fall back on, these links are the way
 * back. They are still generated from `NAV_ITEMS`, so a screen added tomorrow appears here too.
 *
 * A signed-out visitor never reaches this page — `middleware.ts` matches every path and sends them
 * to `/login` first — so every reader of it is somebody who can follow the links.
 */
export default function NotFound() {
  return (
    <main className="mx-auto w-full max-w-3xl px-4 py-10 sm:px-6">
      <Alert>
        <FileQuestionIcon />
        <AlertTitle>Diese Seite gibt es nicht</AlertTitle>
        <AlertDescription className="space-y-3">
          <p>Die aufgerufene Adresse gehört zu keinem Arbeitsbereich dieser Anwendung.</p>
          <ul className="list-disc space-y-1 pl-4">
            {NAV_ITEMS.map((item) => (
              <li key={item.href}>
                <Link href={item.href} className="underline underline-offset-4">
                  {item.label}
                </Link>
              </li>
            ))}
          </ul>
        </AlertDescription>
      </Alert>
    </main>
  )
}
