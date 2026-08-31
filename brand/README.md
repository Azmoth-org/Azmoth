# Brand source artwork

The designer's Figma exports of the Azmoth mark. **Nothing in this directory is served to a
browser**, and that is the whole reason it exists.

Regenerate the shippable assets with:

```
node scripts/build-brand-assets.mjs
```

## Only five of the sixteen are tracked in git

Eleven of them embed the **byte-identical** raster (md5 `a40b77353418`) — the same 2676×1492
monogram PNG — differing only in a background `<rect>` of black, white or `#D9D9D9`. Committing all
sixteen would store that one megabyte eleven times, for 13 MB in the repository's history forever.

So `brand/.gitignore` tracks `tr-icon.svg` (the master, and the file the build reads) and the four
pure-vector `*-text.svg` wordmarks, and ignores the rest. **Nothing was deleted** — the full
hand-over is on disk and can be re-exported or force-added (`git add -f brand/<file>.svg`) at any
time. Every ignored file is reproducible from `tr-icon.svg` by compositing a background, which is
precisely what it is.

## Why these files cannot be served

Sixteen files, 13 MB. Fifteen of them are between 840 kB and 1.8 MB **each**, because Figma wrote the
"Az" monogram as a 2676×1492 base64 PNG embedded inside an `<svg>` — a vector container wrapped
around a megabyte of raster. They were originally dropped into `apps/marketing/public/images/` and
`apps/web/public/images/`, which made them 26 MB of files a browser could actually fetch: a 1 MB
header logo is a page that never passes a performance budget.

The favicon generator's `favicon.svg` had the same shape and was **2.0 MB**. Browsers *prefer* an SVG
icon when one is offered, so linking it would have cost every cold visit two megabytes for a
16-pixel tab icon. It is here and not linked anywhere.

## What is actually usable, and what is derived from it

| File | What it is |
|---|---|
| `tr-icon.svg` | The master. Transparent, and its embedded raster has a real alpha channel. The monogram sits at y=269–964, the wordmark at y=1014–1241. |
| `tr-text.svg` | **The one genuinely vector export**: 5.6 kB of real path data for the "azmoth" wordmark, transparent, no raster. |
| `tr-hor.svg`, `tr-main.svg` | The horizontal and stacked lockups. Transparent, and raster. |
| `main-*`, `black-*`, `white-*` | The same artwork over an opaque background rect (`#D9D9D9`, black, white). Unusable on any surface that is not exactly that colour — which is why the `tr-` variants are the ones the build reads. |
| `bkack-hor.svg` | As delivered, including the typo. Left as received: renaming a source file to fix a spelling makes the next hand-over ambiguous about which is which. |
| `*-text.svg` | The wordmark alone, per background. All four are real vector; `tr-text.svg` is the one used. |

`scripts/build-brand-assets.mjs` produces, into both applications:

- `public/brand/azmoth-mark.png` — the monogram, trimmed to its ink, transparent, 192×192, ~10 kB
- `public/brand/azmoth-wordmark.svg` — the wordmark, tight `viewBox`, `fill="currentColor"`, 5.6 kB

and `apps/marketing/src/lib/brand-mark.ts`, the mark as a data URI for the Open Graph card (which is
drawn by Satori at request time and so can neither fetch a URL nor read a file safely).

The PDF report's masthead carries the same monogram as a deflated grayscale stream in
`apps/engine/app/services/pdf_mark.py`, which documents its own regeneration step.

## The monogram is a raster everywhere, and here is what would change that

Every export of it is the same embedded PNG. Tracing it would need a vectoriser and would produce
paths nobody drew, on a mark that is the company's signature — so the derived assets are rasters at
the sizes they are displayed at (20–34 px in a header, 128 px in the PDF, 16–512 px as icons), where
a raster is indistinguishable from a curve.

**The fix is an SVG of the monogram with real path data, from the designer's original curves.** Drop
it in here as `tr-icon-vector.svg` and `build-brand-assets.mjs` becomes a much shorter script.
