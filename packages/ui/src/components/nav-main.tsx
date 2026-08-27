"use client"

import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@workspace/ui/components/collapsible"
import {
  SidebarGroup,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
} from "@workspace/ui/components/sidebar"
import { ChevronRightIcon } from "lucide-react"

/** One entry in the rail. Nests one level deep, and only if `items` is non-empty. */
export type NavMainItem = {
  title: string
  url: string
  icon?: React.ReactNode
  /** Highlights the row. The caller resolves this — see `activeHref` in `apps/web`. */
  isActive?: boolean
  items?: {
    title: string
    url: string
    isActive?: boolean
  }[]
}

/**
 * A group of navigation rows, flat or one level deep.
 *
 * Two changes from the shadcn template it started as, both of them the difference between a sample
 * and something an application can actually render.
 *
 * **The group's name is a prop.** It was the hardcoded string "Platform". A shared package that
 * names its own groups can be used once, in one language.
 *
 * **A flat item is a link, not an empty accordion.** The template wrapped every row in a
 * `Collapsible` whose trigger swallowed the click, so an entry with no children rendered a chevron
 * that opened nothing and never navigated. Most of this application's nav is flat, so the branch
 * below is not an optimisation — without it the rail does not work.
 *
 * `linkRender` keeps the package router-agnostic: `apps/web` hands back a `next/link`, and the
 * default is a plain anchor so the component still works on its own. It receives the whole item
 * rather than just the url, because the caller is the one that knows how to spell `aria-current`.
 */
export function NavMain({
  label,
  items,
  linkRender = (item) => <a href={item.url} />,
}: {
  /** The group's heading. Omitted renders no heading at all. */
  label?: string
  items: readonly NavMainItem[]
  linkRender?: (item: { url: string; isActive?: boolean }) => React.ReactElement
}) {
  if (items.length === 0) return null

  return (
    <SidebarGroup>
      {label ? <SidebarGroupLabel>{label}</SidebarGroupLabel> : null}
      <SidebarMenu>
        {items.map((item) =>
          item.items && item.items.length > 0 ? (
            <Collapsible
              key={item.url}
              defaultOpen={item.isActive}
              className="group/collapsible"
              render={<SidebarMenuItem />}
            >
              <CollapsibleTrigger
                render={<SidebarMenuButton tooltip={item.title} />}
              >
                {item.icon}
                <span>{item.title}</span>
                <ChevronRightIcon className="ml-auto transition-transform duration-200 group-data-open/collapsible:rotate-90" />
              </CollapsibleTrigger>
              <CollapsibleContent>
                <SidebarMenuSub>
                  {item.items.map((subItem) => (
                    <SidebarMenuSubItem key={subItem.url}>
                      <SidebarMenuSubButton
                        isActive={subItem.isActive}
                        render={linkRender(subItem)}
                      >
                        <span>{subItem.title}</span>
                      </SidebarMenuSubButton>
                    </SidebarMenuSubItem>
                  ))}
                </SidebarMenuSub>
              </CollapsibleContent>
            </Collapsible>
          ) : (
            <SidebarMenuItem key={item.url}>
              <SidebarMenuButton
                isActive={item.isActive}
                // The name, for the collapsed rail — where the label is not rendered at all and an
                // icon on its own is a guess.
                tooltip={item.title}
                render={linkRender(item)}
              >
                {item.icon}
                <span>{item.title}</span>
              </SidebarMenuButton>
            </SidebarMenuItem>
          )
        )}
      </SidebarMenu>
    </SidebarGroup>
  )
}
