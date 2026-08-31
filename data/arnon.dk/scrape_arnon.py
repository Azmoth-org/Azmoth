#!/usr/bin/env python3
"""
Scrape all blogs and guides from https://arnon.dk using Scrapling.

Discovery is done via the site's Yoast sitemaps (post + page sitemaps),
then each article page is fetched with Scrapling's Fetcher and parsed
into structured data.

Outputs (written to ./data):
  - articles.json        full structured data for every article
  - articles.csv         flat metadata table
  - markdown/<slug>.md   one Markdown file per article
"""

import csv
import json
import re
import sys
import time
from pathlib import Path

from scrapling.fetchers import Fetcher, FetcherSession

BASE_URL = "https://arnon.dk"
SITEMAP_INDEX = f"{BASE_URL}/sitemap_index.xml"

OUT_DIR = Path(__file__).resolve().parent / "data"
MD_DIR = OUT_DIR / "markdown"

# Politeness settings
REQUEST_DELAY = 0.4  # seconds between article requests
MAX_ARTICLES = 0     # 0 = no limit (scrape everything)


def slugify(url: str) -> str:
    """Turn an article URL into a filesystem-safe slug."""
    path = url.rstrip("/").split("/")[-1]
    path = re.sub(r"[^a-z0-9\-_]+", "-", path.lower()).strip("-")
    return path or "index"


def fetch_sitemap_urls(session) -> list[str]:
    """Return the ordered list of article URLs from the Yoast sitemaps."""
    urls: list[str] = []
    index = session.get(SITEMAP_INDEX)
    if index.status != 200:
        raise RuntimeError(f"Could not fetch sitemap index ({index.status})")

    # Collect sub-sitemaps, preferring the content sitemaps
    sub_sitemaps = [
        loc.strip()
        for loc in index.css("loc::text").getall()
    ]
    # We only care about posts and pages (not images/attachments/tags)
    wanted = [s for s in sub_sitemaps if "post-sitemap" in s or "page-sitemap" in s]
    print(f"Found {len(sub_sitemaps)} sitemaps, using {len(wanted)} content sitemaps")

    for sm_url in wanted:
        sm = session.get(sm_url)
        if sm.status != 200:
            print(f"  ! Skipping {sm_url} (status {sm.status})", file=sys.stderr)
            continue
        locs = [loc.strip() for loc in sm.css("loc::text").getall()]
        print(f"  {sm_url.split('/')[-1]}: {len(locs)} URLs")
        urls.extend(locs)

    # De-dupe while preserving order
    seen = set()
    unique = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            unique.append(u)
    return unique


def extract_article(page, url: str, kind: str) -> dict:
    """Parse a single fetched article page into a structured dict."""

    def meta(prop: str):
        sel = page.css(f'meta[property="{prop}"]::attr(content)')
        return (sel.get() or "").strip()

    def meta_name(name: str):
        sel = page.css(f'meta[name="{name}"]::attr(content)')
        return (sel.get() or "").strip()

    # --- Title ---
    title = (page.css("h1.wp-block-post-title::text").get() or "").strip()
    if not title:
        title = meta("og:title").split(" - Arnon Shimoni")[0].strip()

    # --- Date ---
    published = meta("article:published_time")
    modified = meta("article:modified_time")
    if not published:
        t = page.css("time::attr(datetime)").get()
        published = (t or "").strip()

    # --- Author ---
    author = meta_name("twitter:data1") or meta_name("author")
    if not author:
        author = (page.css(".wp-block-post-author__name::text").get() or "").strip()

    # --- Categories (topics) ---
    categories = [
        (c or "").strip()
        for c in page.css(".taxonomy-category.wp-block-post-terms a::text").getall()
        if (c or "").strip()
    ]
    if not categories:
        cats = meta("article:section")
        if cats:
            categories = [c.strip() for c in cats.split(",") if c.strip()]
    seen = set()
    categories = [c for c in categories if not (c in seen or seen.add(c))]

    # --- Tags ---
    tags = [
        (t or "").strip()
        for t in page.css(".taxonomy-post_tag.wp-block-post-terms a::text").getall()
        if (t or "").strip()
    ]
    seen = set()
    tags = [t for t in tags if not (t in seen or seen.add(t))]

    # --- Description / excerpt ---
    description = meta("og:description") or meta_name("description")

    # --- Reading time ---
    reading_time = meta_name("twitter:data2")

    # --- Featured image ---
    featured_image = meta("og:image")

    # --- Content ---
    content = page.css(".entry-content.wp-block-post-content").first
    if content is None:
        content = page.css("article").first
    if content is None:
        content = page.css("main").first

    content_html = ""
    content_text = ""
    if content is not None:
        content_html = content.html_content
        content_text = content.get_all_text(separator="\n\n", strip=True)

    return {
        "url": url,
        "kind": kind,  # "post" or "page"
        "title": title,
        "slug": slugify(url),
        "author": author,
        "published": published,
        "modified": modified,
        "categories": categories,
        "tags": tags,
        "description": description,
        "reading_time": reading_time,
        "featured_image": featured_image,
        "content_html": content_html,
        "content_text": content_text,
    }


def write_markdown(article: dict) -> None:
    """Write one article to a Markdown file."""
    lines = []
    lines.append(f"# {article['title']}")
    lines.append("")
    meta_rows = [
        ("URL", article["url"]),
        ("Author", article["author"]),
        ("Published", article["published"]),
        ("Modified", article["modified"]),
        ("Type", article["kind"]),
    ]
    if article["categories"]:
        meta_rows.append(("Topics", ", ".join(article["categories"])))
    if article["tags"]:
        meta_rows.append(("Tags", ", ".join(article["tags"])))
    if article["reading_time"]:
        meta_rows.append(("Reading time", article["reading_time"]))
    if article["description"]:
        meta_rows.append(("Description", article["description"]))
    for k, v in meta_rows:
        if v:
            lines.append(f"- **{k}:** {v}")
    lines.append("")
    if article["content_text"]:
        lines.append(article["content_text"])
    else:
        lines.append("_No text content extracted._")
    lines.append("")

    safe_slug = article["slug"]
    (MD_DIR / f"{safe_slug}.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    MD_DIR.mkdir(exist_ok=True)

    print(f"Fetching sitemap index: {SITEMAP_INDEX}")
    with FetcherSession(
        impersonate="chrome",
        stealthy_headers=True,
        timeout=30,
        retries=3,
    ) as session:
        urls = fetch_sitemap_urls(session)

        # Classify and optionally cap
        items = []
        for u in urls:
            if u == f"{BASE_URL}/" or u == BASE_URL:
                continue  # skip homepage
            kind = "page" if u in (
                f"{BASE_URL}/about/", f"{BASE_URL}/now/",
            ) else "post"
            items.append((u, kind))

        if MAX_ARTICLES:
            items = items[:MAX_ARTICLES]

        print(f"\nScraping {len(items)} articles...\n")

        articles = []
        for i, (url, kind) in enumerate(items, 1):
            try:
                page = session.get(url)
                if page.status != 200:
                    print(f"[{i}/{len(items)}] {page.status} {url}", file=sys.stderr)
                    continue
                article = extract_article(page, url, kind)
                articles.append(article)
                print(f"[{i}/{len(items)}] {article['title'][:70]}")
            except Exception as exc:  # noqa: BLE001
                print(f"[{i}/{len(items)}] ERROR {url}: {exc}", file=sys.stderr)
            time.sleep(REQUEST_DELAY)

    if not articles:
        print("No articles scraped.", file=sys.stderr)
        sys.exit(1)

    # --- Persist ---
    (OUT_DIR / "articles.json").write_text(
        json.dumps(articles, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # CSV (drop the heavy HTML fields)
    flat = []
    for a in articles:
        flat.append({
            "slug": a["slug"],
            "title": a["title"],
            "url": a["url"],
            "kind": a["kind"],
            "author": a["author"],
            "published": a["published"],
            "modified": a["modified"],
            "topics": ";".join(a["categories"]),
            "tags": ";".join(a["tags"]),
            "reading_time": a["reading_time"],
            "featured_image": a["featured_image"],
            "description": a["description"],
            "word_count": len((a["content_text"] or "").split()),
        })
    fieldnames = list(flat[0].keys())
    with open(OUT_DIR / "articles.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(flat)

    for a in articles:
        write_markdown(a)

    print("\n" + "=" * 60)
    print(f"Done. Scraped {len(articles)} articles.")
    print(f"  JSON:     {OUT_DIR / 'articles.json'}")
    print(f"  CSV:      {OUT_DIR / 'articles.csv'}")
    print(f"  Markdown: {MD_DIR}/  ({len(list(MD_DIR.glob('*.md')))} files)")


if __name__ == "__main__":
    main()
