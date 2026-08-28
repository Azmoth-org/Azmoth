"use client"

import { useRouter } from "next/navigation"
import * as React from "react"

import { Alert, AlertDescription } from "@workspace/ui/components/alert"
import { Button } from "@workspace/ui/components/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@workspace/ui/components/card"
import {
  Field,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
} from "@workspace/ui/components/field"
import { Input } from "@workspace/ui/components/input"
import {
  NativeSelect,
  NativeSelectOption,
} from "@workspace/ui/components/native-select"
import {
  Progress,
  ProgressLabel,
  ProgressValue,
} from "@workspace/ui/components/progress"

import { NETWORK_ERROR_MESSAGE } from "@/components/auth/auth-messages"

/**
 * The two-step form behind `/onboarding`. **Client component** — it holds step state.
 *
 * ## Why two steps rather than nine fields on one card
 *
 * They are two different questions asked of two different registers. *Arztprofil* is about a person
 * and their LANR; *Praxisdaten* is about a building and its BSNR — and the two numbers are nine
 * digits each, adjacent on the form, and describe entirely different things. Splitting them is what
 * makes it obvious which number is being asked for, and the progress bar is what stops a split
 * feeling like an unknown amount of work.
 *
 * ## Why the state is controlled, unlike the auth forms
 *
 * `components/auth/signup-form.tsx` reads uncontrolled inputs out of `FormData` on submit, which is
 * right for a single card that is submitted once. It cannot work here: stepping to *Praxisdaten*
 * unmounts the first card, and an uncontrolled input that unmounts takes its value with it — the
 * reader would step back to find their LANR gone. So every field is in one `values` object, and
 * stepping is a re-render rather than a navigation.
 *
 * ## Errors, and where they are allowed to come from
 *
 * `errors` is keyed by the exact field paths the API answers with — `doctor.lanr`, `practice.plz` —
 * so a 422 lands on the field it names with no mapping table in between. The same keys are used by
 * the client-side check that runs before *Weiter*, which is deliberately the *shape* check only
 * (present, nine digits, five digits): the server owns validation, this owns not making somebody
 * wait for a round-trip to be told a field is blank. `lib/onboarding/validate.ts` is the authority
 * and its messages are the ones a mismatch would show.
 *
 * A 422 naming a step-one field while the reader is on step two sends them back to step one. An
 * error on a card nobody is looking at is an error nobody can act on, and the submit button would
 * simply appear not to work.
 */

/** The nine values, flat and all strings — exactly what the inputs hold and the API takes. */
type Values = {
  title: string
  firstName: string
  lastName: string
  lanr: string
  specialty: string
  practiceName: string
  bsnr: string
  city: string
  plz: string
}

/** Field path → message, using the API's own paths. See the note above. */
type Errors = Partial<Record<string, string>>

/**
 * The academic titles offered, plus the empty option.
 *
 * A closed list because these are the forms that actually appear on a German Praxisschild, and a
 * free-text title field collects "Dr." and "Dr. " and "dr. med." for one person. The empty option
 * is first and is a real answer — `doctor_profiles.title` is the one nullable column in that table
 * precisely so that a physician without a title is not an incomplete record.
 */
const TITLES = [
  "Dr.",
  "Dr. med.",
  "Dr. med. dent.",
  "Prof. Dr.",
  "Prof. Dr. med.",
] as const

/** Which fields belong to which card, so a server error can be shown where its field is. */
const STEP_ONE_FIELDS = [
  "doctor.title",
  "doctor.firstName",
  "doctor.lastName",
  "doctor.lanr",
  "doctor.specialty",
] as const

export function OnboardingForm({
  initial,
  next,
}: {
  /** Whatever onboarding has already stored, so a half-finished form re-opens where it stopped. */
  initial: Values
  /** Where a successful submit lands. Already passed through `safeNext` by the page. */
  next: string
}) {
  const router = useRouter()
  const [step, setStep] = React.useState<1 | 2>(1)
  const [values, setValues] = React.useState<Values>(initial)
  const [errors, setErrors] = React.useState<Errors>({})
  const [failure, setFailure] = React.useState<string | null>(null)
  const [pending, setPending] = React.useState(false)

  function set(field: keyof Values, value: string) {
    setValues((current) => ({ ...current, [field]: value }))
  }

  /**
   * The shape check for one step. Mirrors `lib/onboarding/validate.ts`, never replaces it.
   *
   * Whitespace is stripped from the three numbers before checking, exactly as the server does —
   * people read a LANR off a letter in groups, and refusing a paste over its spaces would be
   * pedantry rather than validation.
   */
  function check(which: 1 | 2): Errors {
    const found: Errors = {}
    const digits = (value: string) => value.replace(/\s+/g, "")

    if (which === 1) {
      if (!values.firstName.trim())
        found["doctor.firstName"] = "Der Vorname ist erforderlich."
      if (!values.lastName.trim())
        found["doctor.lastName"] = "Der Nachname ist erforderlich."
      if (!/^\d{9}$/.test(digits(values.lanr)))
        found["doctor.lanr"] = "Die LANR besteht aus genau neun Ziffern."
      if (!values.specialty.trim())
        found["doctor.specialty"] = "Die Fachrichtung ist erforderlich."
    } else {
      if (!values.practiceName.trim())
        found["practice.practiceName"] = "Der Praxisname ist erforderlich."
      if (!/^\d{9}$/.test(digits(values.bsnr)))
        found["practice.bsnr"] = "Die BSNR besteht aus genau neun Ziffern."
      if (!/^\d{5}$/.test(digits(values.plz)))
        found["practice.plz"] = "Die PLZ besteht aus genau fünf Ziffern."
      if (!values.city.trim())
        found["practice.city"] = "Der Ort ist erforderlich."
    }

    return found
  }

  function forward() {
    const found = check(1)
    setErrors(found)
    if (Object.keys(found).length > 0) return
    setFailure(null)
    setStep(2)
  }

  function back() {
    setFailure(null)
    setStep(1)
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (pending) return

    // Both steps, not just the visible one. Stepping forward validated step one, but the reader
    // could have stepped back, emptied a field and come forward again.
    const found = { ...check(1), ...check(2) }
    if (Object.keys(found).length > 0) {
      setErrors(found)
      if (STEP_ONE_FIELDS.some((field) => field in found)) setStep(1)
      return
    }

    setErrors({})
    setFailure(null)
    setPending(true)

    try {
      const response = await fetch("/api/onboarding", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          doctor: {
            title: values.title,
            firstName: values.firstName,
            lastName: values.lastName,
            lanr: values.lanr,
            specialty: values.specialty,
          },
          practice: {
            practiceName: values.practiceName,
            bsnr: values.bsnr,
            city: values.city,
            plz: values.plz,
          },
        }),
      })

      if (response.ok) {
        // `refresh()` before `push()`, for the same reason the auth forms do it: the shell is a
        // server component holding the organisation switcher, and without this the reader lands on
        // a dashboard whose rail still shows the practice they had before this form renamed it.
        router.refresh()
        router.push(next)
        return
      }

      const body: unknown = await response.json().catch(() => null)
      setErrors(fieldErrorsFrom(response.status, body))
      setFailure(summaryFrom(response.status, body))
      // A LANR collision is reported on the field, and the field is on the first card.
      if (response.status === 409) setStep(1)
      setPending(false)
    } catch {
      setFailure(NETWORK_ERROR_MESSAGE)
      setPending(false)
    }
  }

  const percent = step === 1 ? 50 : 100

  return (
    <form onSubmit={submit} noValidate>
      <Card>
        <CardHeader>
          {/*
            The bar carries its own label and value, so the step is legible without counting cards.
            `aria-label` on the root names the whole control for a screen reader, which otherwise
            hears two unattached numbers.
          */}
          <Progress
            value={percent}
            aria-label="Fortschritt der Einrichtung"
            className="mb-4"
          >
            <ProgressLabel>Schritt {step} von 2</ProgressLabel>
            <ProgressValue />
          </Progress>

          <CardTitle>{step === 1 ? "Arztprofil" : "Praxisdaten"}</CardTitle>
          <CardDescription>
            {step === 1
              ? "Diese Angaben erscheinen als verantwortliche Ärztin oder verantwortlicher Arzt auf jeder geprüften Abrechnung."
              : "Die Betriebsstätte, für die abgerechnet wird. Der Praxisname wird auch als Name Ihrer Organisation übernommen."}
          </CardDescription>
        </CardHeader>

        <CardContent>
          {failure ? (
            <Alert variant="destructive" role="alert" className="mb-6">
              <AlertDescription>{failure}</AlertDescription>
            </Alert>
          ) : null}

          {step === 1 ? (
            <FieldGroup>
              <Field>
                <FieldLabel htmlFor="title">Titel</FieldLabel>
                {/*
                  The wrapper is `w-fit` by default, which on a phone leaves a select narrower than
                  every input beside it. `w-full` on the wrapper rather than the select, because the
                  chevron is positioned against the wrapper.
                */}
                <NativeSelect
                  className="w-full"
                  id="title"
                  name="title"
                  value={values.title}
                  onChange={(event) => set("title", event.target.value)}
                  disabled={pending}
                >
                  <NativeSelectOption value="">Kein Titel</NativeSelectOption>
                  {TITLES.map((title) => (
                    <NativeSelectOption key={title} value={title}>
                      {title}
                    </NativeSelectOption>
                  ))}
                </NativeSelect>
                <FieldDescription>Optional.</FieldDescription>
              </Field>

              {/*
                Two columns from `sm:` up, one below it. The names are short and belong side by
                side on any screen wide enough; on a phone they stack, which is the layout the whole
                card falls back to.
              */}
              <div className="grid gap-6 sm:grid-cols-2">
                <TextField
                  id="firstName"
                  label="Vorname"
                  value={values.firstName}
                  onChange={(value) => set("firstName", value)}
                  error={errors["doctor.firstName"]}
                  autoComplete="given-name"
                  autoFocus
                  disabled={pending}
                />
                <TextField
                  id="lastName"
                  label="Nachname"
                  value={values.lastName}
                  onChange={(value) => set("lastName", value)}
                  error={errors["doctor.lastName"]}
                  autoComplete="family-name"
                  disabled={pending}
                />
              </div>

              <TextField
                id="lanr"
                label="LANR"
                value={values.lanr}
                onChange={(value) => set("lanr", value)}
                error={errors["doctor.lanr"]}
                description="Lebenslange Arztnummer — neun Ziffern."
                inputMode="numeric"
                placeholder="123456789"
                disabled={pending}
              />

              <TextField
                id="specialty"
                label="Fachrichtung"
                value={values.specialty}
                onChange={(value) => set("specialty", value)}
                error={errors["doctor.specialty"]}
                placeholder="Allgemeinmedizin"
                disabled={pending}
              />
            </FieldGroup>
          ) : (
            <FieldGroup>
              <TextField
                id="practiceName"
                label="Praxisname"
                value={values.practiceName}
                onChange={(value) => set("practiceName", value)}
                error={errors["practice.practiceName"]}
                placeholder="Praxis am Markt"
                autoFocus
                disabled={pending}
              />

              <TextField
                id="bsnr"
                label="BSNR"
                value={values.bsnr}
                onChange={(value) => set("bsnr", value)}
                error={errors["practice.bsnr"]}
                description="Betriebsstättennummer — neun Ziffern."
                inputMode="numeric"
                placeholder="987654321"
                disabled={pending}
              />

              {/*
                PLZ narrow, Ort wide — a five-digit box the width of a city name invites somebody to
                type the city into it. `inputMode="numeric"` rather than `type="number"`: a number
                input strips the leading zero that a third of German postcodes start with.
              */}
              <div className="grid gap-6 sm:grid-cols-[8rem_1fr]">
                <TextField
                  id="plz"
                  label="PLZ"
                  value={values.plz}
                  onChange={(value) => set("plz", value)}
                  error={errors["practice.plz"]}
                  inputMode="numeric"
                  autoComplete="postal-code"
                  placeholder="53111"
                  disabled={pending}
                />
                <TextField
                  id="city"
                  label="Ort"
                  value={values.city}
                  onChange={(value) => set("city", value)}
                  error={errors["practice.city"]}
                  autoComplete="address-level2"
                  placeholder="Bonn"
                  disabled={pending}
                />
              </div>
            </FieldGroup>
          )}
        </CardContent>

        {/*
          Stacked and full-width on a phone, side by side from `sm:` up. `flex-col-reverse` so the
          primary action is the one under the reader's thumb while still being second in the DOM,
          which is the order a keyboard should tab through them in.
        */}
        <CardFooter className="flex flex-col-reverse gap-3 sm:flex-row sm:justify-between">
          {step === 2 ? (
            <Button
              type="button"
              variant="outline"
              onClick={back}
              disabled={pending}
              className="w-full sm:w-auto"
            >
              Zurück
            </Button>
          ) : (
            <span className="hidden sm:block" />
          )}

          {step === 1 ? (
            <Button
              type="button"
              onClick={forward}
              className="w-full sm:w-auto"
            >
              Weiter
            </Button>
          ) : (
            <Button
              type="submit"
              disabled={pending}
              className="w-full sm:w-auto"
            >
              {pending ? "Wird gespeichert…" : "Einrichtung abschließen"}
            </Button>
          )}
        </CardFooter>
      </Card>
    </form>
  )
}

/**
 * One labelled text input with its description and its error.
 *
 * Local to this file rather than in `@workspace/ui`, because it encodes this form's conventions —
 * the error replaces the description, `aria-invalid` follows the error — rather than a component
 * the rest of the application asked for.
 */
function TextField({
  id,
  label,
  value,
  onChange,
  error,
  description,
  ...input
}: {
  id: string
  label: string
  value: string
  onChange: (value: string) => void
  error?: string
  description?: string
} & Omit<
  React.ComponentProps<typeof Input>,
  "id" | "value" | "onChange" | "aria-invalid"
>) {
  return (
    <Field data-invalid={error ? true : undefined}>
      <FieldLabel htmlFor={id}>{label}</FieldLabel>
      <Input
        id={id}
        name={id}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${id}-error` : undefined}
        {...input}
      />
      {error ? (
        <FieldError id={`${id}-error`}>{error}</FieldError>
      ) : description ? (
        <FieldDescription>{description}</FieldDescription>
      ) : null}
    </Field>
  )
}

/**
 * The field-level errors in a failed response, keyed the way `errors` is.
 *
 * A 422 carries `details` as the array `lib/onboarding/validate.ts` produced, field paths included,
 * so it maps across directly. A 409 carries the single field the unique index refused. Anything
 * else has no field to attach to and is reported by `summaryFrom` alone.
 */
function fieldErrorsFrom(status: number, body: unknown): Errors {
  const envelope = asRecord(body)

  if (status === 422 && Array.isArray(envelope.details)) {
    const found: Errors = {}
    for (const entry of envelope.details) {
      const item = asRecord(entry)
      if (typeof item.field === "string" && typeof item.message === "string") {
        found[item.field] = item.message
      }
    }
    return found
  }

  if (status === 409) {
    const field = asRecord(envelope.details).field
    if (typeof field === "string") {
      return { [field]: LANR_TAKEN }
    }
  }

  return {}
}

/** The one message the brief names verbatim. Shown on the field and in the banner. */
const LANR_TAKEN = "Diese LANR ist bereits registriert."

/**
 * The sentence at the top of the card, or `null` when every problem is already on a field.
 *
 * A 422 gets no banner: each message is beside the input it belongs to, and a second copy at the
 * top would say the same thing twice. Everything else does, because a 403 or a 500 has no field to
 * point at and a silent failure reads as a broken button.
 */
function summaryFrom(status: number, body: unknown): string | null {
  if (status === 422) return null
  if (status === 409) return LANR_TAKEN

  const message = asRecord(body).message
  if (typeof message === "string" && message) return message

  if (status === 401) {
    return "Die Sitzung ist abgelaufen. Bitte melden Sie sich erneut an."
  }
  return "Die Angaben konnten nicht gespeichert werden. Bitte versuchen Sie es erneut."
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null
    ? (value as Record<string, unknown>)
    : {}
}
