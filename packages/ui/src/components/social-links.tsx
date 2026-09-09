import {
  IconBrandFacebook,
  IconBrandInstagram,
  IconBrandLinkedin,
  IconBrandProducthunt,
  IconBrandTwitter,
} from "@tabler/icons-react";

import { cn } from "@workspace/ui/lib/utils";

/**
 * `lucide-react` dropped brand/company glyphs, so these come from `@tabler/icons-react` — already
 * a dependency here for other icons in this package.
 *
 * One entry per env var: a site links only the profiles it has a URL for, so an unset var hides
 * its icon rather than pointing at a placeholder.
 */
const SOCIAL_LINKS = [
  {
    url: process.env.NEXT_PUBLIC_FACEBOOK_URL,
    label: "Facebook",
    Icon: IconBrandFacebook,
  },
  {
    url: process.env.NEXT_PUBLIC_INSTAGRAM_URL,
    label: "Instagram",
    Icon: IconBrandInstagram,
  },
  {
    url: process.env.NEXT_PUBLIC_LINKEDIN_URL,
    label: "LinkedIn",
    Icon: IconBrandLinkedin,
  },
  {
    url: process.env.NEXT_PUBLIC_PRODUCTHUNT_URL,
    label: "Product Hunt",
    Icon: IconBrandProducthunt,
  },
  {
    url: process.env.NEXT_PUBLIC_TWITTER_URL,
    label: "Twitter",
    Icon: IconBrandTwitter,
  },
] as const;

export function SocialLinks({ className }: { className?: string }) {
  const links = SOCIAL_LINKS.filter((link) => link.url);

  if (links.length === 0) return null;

  return (
    <div className={cn("flex items-center gap-3", className)}>
      {links.map(({ url, label, Icon }) => (
        <a
          key={label}
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          aria-label={label}
          className="text-muted-foreground transition-colors hover:text-foreground"
        >
          <Icon className="size-4" aria-hidden />
        </a>
      ))}
    </div>
  );
}
