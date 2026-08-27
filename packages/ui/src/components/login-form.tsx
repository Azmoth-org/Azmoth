import { cn } from "@workspace/ui/lib/utils"
import { Button } from "@workspace/ui/components/button"
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
  FieldSeparator,
} from "@workspace/ui/components/field"
import { Input } from "@workspace/ui/components/input"

/**
 * The sign-in form's layout, and none of its words.
 *
 * The shadcn template this came from carried its own copy ("Login to your account"), its own social
 * provider (a GitHub button) and its own dead `href="#"` links. All three are gone: every string is
 * a prop and both the provider button and the footer are slots. That is what lets a German
 * application render it without a translation layer, and what stops a second consumer from
 * inheriting the first one's provider — `apps/web` passes a Google button, and nothing in this
 * package knows or cares which provider that is.
 *
 * Uncontrolled on purpose. The inputs carry `name`, so the caller reads them from the submitted
 * `FormData` rather than mirroring every keystroke into React state — two fields do not need a
 * reducer, and it keeps this file free of the `useState` that would force `"use client"` on it.
 *
 * `alert` sits above the fields rather than beside the button that caused it, because the failure it
 * usually reports is an OAuth round-trip that happened on a previous render — by the time it is read
 * the button is no longer what the reader is looking at.
 */
export function LoginForm({
  title,
  description,
  emailLabel,
  emailPlaceholder,
  passwordLabel,
  passwordHint,
  submitLabel,
  separatorLabel,
  alert,
  social,
  footer,
  pending = false,
  className,
  ...props
}: Omit<React.ComponentProps<"form">, "title"> & {
  /** The screen's name. Rendered as the page's `<h1>` — this form *is* the page. */
  title: string
  description: string
  emailLabel: string
  emailPlaceholder?: string
  passwordLabel: string
  /** The "forgot your password?" link, or nothing on a deployment that has no reset flow. */
  passwordHint?: React.ReactNode
  /** Already resolved for the pending state by the caller, so this component owns no copy. */
  submitLabel: string
  /** Names the rule above the provider button. Omitted along with `social`. */
  separatorLabel?: string
  /** A failure from a previous render — see the note above. */
  alert?: React.ReactNode
  /** The OAuth button, on deployments that registered a provider. Omitted entirely on those that did not. */
  social?: React.ReactNode
  /** The link to the sign-up screen. */
  footer?: React.ReactNode
  /** Disables every control and is reflected in `submitLabel` by the caller. */
  pending?: boolean
}) {
  return (
    <form className={cn("flex flex-col gap-6", className)} {...props}>
      <FieldGroup>
        <div className="flex flex-col items-center gap-1 text-center">
          {/*
            An `<h1>`, not a `<div>`. On a screen whose entire content is one form, the form's name
            is the page's name, and a page with no level-1 heading gives a screen-reader user nothing
            to land on.
          */}
          <h1 className="text-xl font-semibold">{title}</h1>
          <p className="text-sm text-balance text-muted-foreground">
            {description}
          </p>
        </div>

        {alert}

        <Field>
          <FieldLabel htmlFor="email">{emailLabel}</FieldLabel>
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
            placeholder={emailPlaceholder}
            disabled={pending}
          />
        </Field>

        <Field>
          <div className="flex items-center">
            <FieldLabel htmlFor="password">{passwordLabel}</FieldLabel>
            {passwordHint ? (
              <div className="ml-auto text-sm">{passwordHint}</div>
            ) : null}
          </div>
          <Input
            id="password"
            name="password"
            type="password"
            autoComplete="current-password"
            required
            disabled={pending}
          />
        </Field>

        <Field>
          <Button type="submit" disabled={pending}>
            {submitLabel}
          </Button>
        </Field>

        {social ? (
          <>
            {/*
              `FieldSeparator` punches its label out of `bg-background`, and this form is rendered on
              a `<Card>` — which is a different token in both themes (white on gray-50 in light).
              The override repaints the label with the surface it actually sits on; without it the
              rule's label is a visibly grey rectangle on a white card.
            */}
            <FieldSeparator className="*:data-[slot=field-separator-content]:bg-card">
              {separatorLabel}
            </FieldSeparator>
            <Field>{social}</Field>
          </>
        ) : null}

        {footer ? (
          <FieldDescription className="text-center">{footer}</FieldDescription>
        ) : null}
      </FieldGroup>
    </form>
  )
}
