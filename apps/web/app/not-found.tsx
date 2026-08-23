import { FileQuestionIcon } from "lucide-react"
import Link from "next/link"

import { Alert, AlertDescription, AlertTitle } from "@workspace/ui/components/alert"

import { NAV_ITEMS } from "@/components/layout/nav"

/**
 * An unknown path. Rendered inside the app shell, so the sidebar is still there and the reader is
 * one click from where they meant to go — which is the whole point of having a shell.
 */
export default function NotFound() {
  return (
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
  )
}
