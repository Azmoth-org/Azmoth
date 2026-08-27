"use client"

import { BuildingIcon } from "lucide-react"
import { useRouter } from "next/navigation"
import * as React from "react"

import {
  OrgSwitcher,
  type OrgSwitcherItem,
} from "@workspace/ui/components/org-switcher"

import {
  authClient,
  useActiveOrganization,
  useListOrganizations,
} from "@/lib/auth-client"

/** What the server already knew about the organisations, so the first paint is not an empty rail. */
export type OrganisationSnapshot = {
  items: OrgSwitcherItem[]
  activeId: string | null
}

/**
 * The organisation in the rail's header, wired to Better Auth.
 *
 * ## Server snapshot first, hooks after
 *
 * `(app)/layout.tsx` has already resolved the session in order to decide whether this screen renders
 * at all, and asking Better Auth for the organisation list in the same pass costs one query against
 * a connection that is already open. So the rail's first paint is correct, and `useListOrganizations`
 * / `useActiveOrganization` take over once they have answered — `??` rather than `||` because an
 * empty list is a real answer that must not fall back to the snapshot.
 *
 * Without the snapshot the header renders "Keine Organisation" for the length of a round-trip on
 * every navigation, and then corrects itself. That is the same reasoning `UserMenu` was built on.
 *
 * ## Switching is a session change, so the server has to re-render
 *
 * `organization.setActive` writes `activeOrganizationId` onto the session row. Every server
 * component that read the session is now stale, and Next has their output cached per route — so
 * `router.refresh()` is not a nicety here, it is what makes the switch visible anywhere other than
 * this dropdown. The plugin's own atoms update themselves; the rest of the page does not.
 *
 * ## Creating one is a prompt, and that is a deliberate floor
 *
 * `window.prompt` is not a designed dialogue and is not pretending to be. The alternative was a form
 * in a sheet, and it would be the wrong thing to build blind: an organisation is where an invite
 * flow, a member list and a slug the URLs will carry all have to land, and none of that is designed
 * yet. This is enough to create the first practice on a fresh database and no more, and it is marked
 * so the next reader does not mistake it for a finished screen.
 */
export function OrganisationSwitcher({
  snapshot,
}: {
  snapshot: OrganisationSnapshot
}) {
  const router = useRouter()
  const { data: organisations } = useListOrganizations()
  const { data: active } = useActiveOrganization()
  const [pending, setPending] = React.useState(false)

  const items: OrgSwitcherItem[] =
    organisations?.map((organisation) => ({
      id: organisation.id,
      name: organisation.name,
      meta: organisation.slug,
    })) ?? snapshot.items

  const activeId = active?.id ?? snapshot.activeId

  async function select(id: string) {
    if (pending || id === activeId) return
    setPending(true)
    try {
      await authClient.organization.setActive({ organizationId: id })
      router.refresh()
    } finally {
      setPending(false)
    }
  }

  async function create() {
    if (pending) return

    const name = window.prompt("Name der Organisation")?.trim()
    if (!name) return

    setPending(true)
    try {
      await authClient.organization.create({ name, slug: slugify(name) })
      router.refresh()
    } finally {
      setPending(false)
    }
  }

  return (
    <OrgSwitcher
      items={items}
      activeId={activeId}
      onSelect={select}
      pending={pending}
      label="Organisation wechseln"
      emptyName="Keine Organisation"
      emptyMeta="Noch keiner zugeordnet"
      fallbackLogo={<BuildingIcon />}
      addLabel="Organisation anlegen"
      onAdd={create}
      triggerLabel="Organisation wechseln"
    />
  )
}

/**
 * A URL-safe slug from a practice's name.
 *
 * Better Auth requires one and enforces its uniqueness, so this only has to produce something legal
 * and recognisable. German names are the whole input here, which is why the umlauts are transliterated
 * rather than stripped: `NFD` alone would turn "Röntgenpraxis" into "Rontgenpraxis", and ö → oe is
 * what a German reader expects to see. The random suffix is what stops the second "Praxis Müller"
 * from colliding with the first and failing with an error this prompt has nowhere to put.
 */
function slugify(name: string): string {
  const base = name
    .toLowerCase()
    .replace(/ä/g, "ae")
    .replace(/ö/g, "oe")
    .replace(/ü/g, "ue")
    .replace(/ß/g, "ss")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 40)

  const suffix = Math.random().toString(36).slice(2, 6)
  return base ? `${base}-${suffix}` : `organisation-${suffix}`
}
