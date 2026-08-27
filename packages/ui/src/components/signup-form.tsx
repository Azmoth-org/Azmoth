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
 * The sign-up form's layout, and none of its words. The counterpart to `LoginForm`, and the same
 * bargain: every string is a prop, the provider button and the footer are slots, and the shadcn
 * template's GitHub button and `href="#"` links are gone. See that file for the reasoning.
 *
 * Four fields rather than the login screen's two, and the extra two are the reason this is a
 * separate component rather than a `mode` prop on one: a name that will appear in an audit trail and
 * a password confirmation are not variations on signing in, and a single component switching between
 * the two shapes reads worse than two that each do one thing.
 *
 * The confirmation field is compared by the caller, not here. Whether the two passwords match is a
 * validation decision with a message attached, and the message is German in `apps/web` and unknown
 * in this package — so the comparison lives where the words do.
 */
export function SignupForm({
  title,
  description,
  nameLabel,
  namePlaceholder,
  nameHint,
  emailLabel,
  emailPlaceholder,
  passwordLabel,
  passwordHint,
  confirmLabel,
  submitLabel,
  separatorLabel,
  alert,
  social,
  footer,
  pending = false,
  minPasswordLength,
  className,
  ...props
}: Omit<React.ComponentProps<"form">, "title"> & {
  /** The screen's name. Rendered as the page's `<h1>` — this form *is* the page. */
  title: string
  description: string
  nameLabel: string
  namePlaceholder?: string
  /** Why the name is asked for. It ends up beside every approval in the audit trail. */
  nameHint?: React.ReactNode
  emailLabel: string
  emailPlaceholder?: string
  passwordLabel: string
  /** The password floor, stated where it can be read before it is enforced. */
  passwordHint?: React.ReactNode
  confirmLabel: string
  /** Already resolved for the pending state by the caller, so this component owns no copy. */
  submitLabel: string
  /** Names the rule above the provider button. Omitted along with `social`. */
  separatorLabel?: string
  alert?: React.ReactNode
  /** The OAuth button, on deployments that registered a provider. */
  social?: React.ReactNode
  /** The link to the sign-in screen. */
  footer?: React.ReactNode
  pending?: boolean
  /**
   * Mirrors the server's `minPasswordLength` into the browser's own validation, so the shortest
   * possible rejection costs no round-trip. The server remains the one that decides.
   */
  minPasswordLength?: number
}) {
  return (
    <form className={cn("flex flex-col gap-6", className)} {...props}>
      <FieldGroup>
        <div className="flex flex-col items-center gap-1 text-center">
          <h1 className="text-xl font-semibold">{title}</h1>
          <p className="text-sm text-balance text-muted-foreground">
            {description}
          </p>
        </div>

        {alert}

        <Field>
          <FieldLabel htmlFor="name">{nameLabel}</FieldLabel>
          <Input
            id="name"
            name="name"
            type="text"
            autoComplete="name"
            autoFocus
            required
            placeholder={namePlaceholder}
            disabled={pending}
          />
          {nameHint ? <FieldDescription>{nameHint}</FieldDescription> : null}
        </Field>

        <Field>
          <FieldLabel htmlFor="email">{emailLabel}</FieldLabel>
          <Input
            id="email"
            name="email"
            type="email"
            inputMode="email"
            autoComplete="username"
            required
            placeholder={emailPlaceholder}
            disabled={pending}
          />
        </Field>

        <Field>
          <FieldLabel htmlFor="password">{passwordLabel}</FieldLabel>
          <Input
            id="password"
            name="password"
            type="password"
            autoComplete="new-password"
            required
            minLength={minPasswordLength}
            disabled={pending}
          />
          {passwordHint ? (
            <FieldDescription>{passwordHint}</FieldDescription>
          ) : null}
        </Field>

        <Field>
          <FieldLabel htmlFor="confirm-password">{confirmLabel}</FieldLabel>
          <Input
            id="confirm-password"
            name="confirm-password"
            type="password"
            autoComplete="new-password"
            required
            minLength={minPasswordLength}
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
            {/* See `LoginForm` — the label has to be repainted with the card's own surface. */}
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
