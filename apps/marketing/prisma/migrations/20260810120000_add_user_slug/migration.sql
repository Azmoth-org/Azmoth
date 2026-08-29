-- Add a stable URL slug for the client portal (/client/{slug})
ALTER TABLE "user" ADD COLUMN "slug" TEXT;

-- Backfill from the email local-part (unique per email), slugified.
UPDATE "user"
SET "slug" = lower(regexp_replace(split_part(email, '@', 1), '[^a-z0-9]+', '-', 'g'))
WHERE "slug" IS NULL OR "slug" = '';

-- De-duplicate collisions deterministically (e.g. john@a.com vs john@b.com):
-- keep the first by email, append a 6-char hash of the email to the rest.
WITH ranked AS (
  SELECT id, slug, row_number() OVER (PARTITION BY slug ORDER BY email) AS rn
  FROM "user"
  WHERE "slug" IS NOT NULL AND "slug" <> ''
)
UPDATE "user" u
SET "slug" = d.slug || '-' || substr(md5(u.email), 1, 6)
FROM ranked d
WHERE d.id = u.id AND d.rn > 1;

-- Defensive fallback for empty local-parts: hash-based slug.
UPDATE "user"
SET "slug" = 'client-' || substr(md5(email), 1, 8)
WHERE "slug" IS NULL OR "slug" = '';

CREATE UNIQUE INDEX "user_slug_key" ON "user"("slug");
