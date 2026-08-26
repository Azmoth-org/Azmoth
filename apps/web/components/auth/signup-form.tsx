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
 * Create an account, and be signed in by it.
 *
 * `signUp.email` establishes the session itself — `requireEmailVerification` is off, see
 * `lib/auth.ts` — so there is no second sign-in call here and the new account lands on the screen
 * it was headed for.
 *
 * **The name is required, and that is a product decision rather than a schema one.** Better Auth
 * would accept an empty string. Every audit row this person then writes would be attributed to an
 * id with no human beside it, and the first time somebody has to answer "who approved this" the
 * answer would be a lookup that goes nowhere useful.
 *
 * The password floor is checked here *and* in `lib/auth.ts`. The server's check is the one that
 * matters; this one exists so that "too short" is said before the round-trip rather than after it,
 * and the number is stated in the hint rather than only in the error.
 */
const MIN_PASSWORD_LENGTH = 12

export function SignupForm({ next }: { next: string }) {
  const router = useRouter()
  const [name, setName] = React.useState("")
  const [email, setEmail] = React.useState("")
  const [password, setPassword] = React.useState("")
  const [error, setError] = React.useState<string | null>(null)
  const [pending, setPending] = React.useState(false)

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    if (pending) return

    if (password.length < MIN_PASSWORD_LENGTH) {
      setError(`Das Passwort muss mindestens ${MIN_PASSWORD_LENGTH} Zeichen lang sein.`)
      return
    }

    setError(null)
    setPending(true)
    try {
      const { error: failure } = await authClient.signUp.email({
        name: name.trim(),
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
        <Label htmlFor="name">Name</Label>
        <Input
          id="name"
          name="name"
          autoComplete="name"
          autoFocus
          required
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="Dr. med. Maria Muster"
          disabled={pending}
        />
        <p className="text-muted-foreground text-xs">
          Erscheint im Prüfprotokoll neben jeder Freigabe.
        </p>
      </div>

      <div className="space-y-2">
        <Label htmlFor="email">E-Mail</Label>
        <Input
          id="email"
          name="email"
          type="email"
          inputMode="email"
          autoComplete="username"
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
          autoComplete="new-password"
          required
          minLength={MIN_PASSWORD_LENGTH}
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          disabled={pending}
        />
        <p className="text-muted-foreground text-xs">
          Mindestens {MIN_PASSWORD_LENGTH} Zeichen.
        </p>
      </div>

      <Button type="submit" className="w-full" disabled={pending}>
        {pending ? "Konto wird erstellt…" : "Registrieren"}
      </Button>
    </form>
  )
}
