"use client"

import { useRouter } from "next/navigation"
import * as React from "react"

import { Alert, AlertDescription } from "@workspace/ui/components/alert"
import { Button } from "@workspace/ui/components/button"
import { Input } from "@workspace/ui/components/input"
import { Label } from "@workspace/ui/components/label"

import { NETWORK_ERROR_MESSAGE, authErrorMessage } from "@/components/auth/auth-messages"
import { authClient } from "@/lib/auth-client"

/**
 * Sign in with an email address and a password.
 *
 * ## `router.refresh()` before the push, every time
 *
 * The screens behind `/login` are server components, and Next caches their rendered output per
 * route. Pushing straight to `next` after a successful sign-in can therefore land on a cached copy
 * rendered for whoever was signed in before — or on the redirect the middleware produced a moment
 * ago. `refresh()` discards that cache so the destination is rendered against the session that now
 * exists.
 *
 * ## The failure is a value, not a thrown error
 *
 * `authClient.signIn.email` resolves with `{ error }` rather than rejecting, so the `catch` below is
 * for the transport only — no network, DNS gone, the server not running. Those two cases read
 * differently to the person in front of the form ("your password is wrong" versus "we could not
 * ask"), which is why they produce different sentences.
 */
export function LoginForm({ next }: { next: string }) {
  const router = useRouter()
  const [email, setEmail] = React.useState("")
  const [password, setPassword] = React.useState("")
  const [error, setError] = React.useState<string | null>(null)
  const [pending, setPending] = React.useState(false)

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    if (pending) return

    setError(null)
    setPending(true)
    try {
      const { error: failure } = await authClient.signIn.email({
        email: email.trim(),
        password,
      })
      if (failure) {
        setError(authErrorMessage(failure))
        setPending(false)
        return
      }
      router.refresh()
      router.push(next)
      // `pending` stays true through the navigation on purpose: releasing it here puts the button
      // back to "Anmelden" for the moment before the new screen paints, which reads as a sign-in
      // that did nothing.
    } catch {
      setError(NETWORK_ERROR_MESSAGE)
      setPending(false)
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4" noValidate>
      {error ? (
        <Alert variant="destructive" role="alert">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      <div className="space-y-2">
        <Label htmlFor="email">E-Mail</Label>
        <Input
          id="email"
          name="email"
          type="email"
          inputMode="email"
          autoComplete="username"
          // The cursor starts here. On a form of two fields that is the difference between typing
          // and reaching for the mouse first.
          autoFocus
          required
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          placeholder="name@praxis.de"
          disabled={pending}
        />
      </div>

      <div className="space-y-2">
        <Label htmlFor="password">Passwort</Label>
        <Input
          id="password"
          name="password"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          disabled={pending}
        />
      </div>

      <Button type="submit" className="w-full" disabled={pending}>
        {pending ? "Wird angemeldet…" : "Anmelden"}
      </Button>
    </form>
  )
}
