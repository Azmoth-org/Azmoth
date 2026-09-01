#!/usr/bin/env node
/**
 * Derive the shippable brand assets from the Figma exports in `brand/`.
 *
 *     node scripts/build-brand-assets.mjs
 *
 * ## Why this script exists
 *
 * The exports in `brand/` are what a designer handed over, and they cannot be served. Fifteen of the
 * sixteen files are between 840 kB and 1.8 MB each, because Figma wrote the "Az" monogram as a
 * 2676x1492 base64 PNG embedded inside an `<svg>` — a vector container around a megabyte of raster.
 * Put in `public/`, they are 13 MB per application of files a browser would actually download: a
 * 1 MB header logo is a page that never passes a performance budget, and a 2 MB `favicon.svg` is 2 MB
 * fetched for a 16-pixel tab icon.
 *
 * So `brand/` is the source of truth and is not served, and this script emits the small set that is:
 *
 *     public/brand/azmoth-mark.png       the monogram, trimmed, transparent, 192x192
 *     public/brand/azmoth-wordmark.svg   "azmoth" as real vector paths, in currentColor
 *     src/lib/brand-mark.ts              the same monogram as a data URI (marketing only)
 *
 * Both are committed. This script is how they are regenerated when the brand changes, not something
 * a build has to run — a build step that needs `sharp` and 13 MB of inputs to produce 12 kB of output
 * is a build step that breaks in CI for no benefit.
 *
 * ## What comes from where
 *
 * `brand/tr-icon.svg` holds the master raster with a real alpha channel (the `tr-` prefix is the
 * transparent variant; `main-`, `black-` and `white-` are the same artwork over an opaque
 * background rect, which is unusable in a header). Its embedded PNG contains the monogram at
 * y=269..964 and the wordmark at y=1014..1241 — measured, not guessed, by the alpha bounding boxes
 * this script computes.
 *
 * `brand/tr-text.svg` is the one export that is genuinely vector: 5.6 kB of real path data for the
 * wordmark, transparent, no raster anywhere. That is the file the header and footer render, which is
 * why the wordmark is crisp at any size and the monogram beside it is a raster.
 *
 * **The monogram is not vectorised, and it is not going to be here.** Tracing it would need a
 * vectoriser and would produce paths nobody drew, on a mark that is the company's signature. A 192px
 * transparent PNG at ~6 kB is the honest answer for something displayed at 20-32 px; the day a large
 * vector monogram is wanted, it should come from the designer's original curves.
 */

import { createRequire } from "node:module";
import { Buffer } from "node:buffer";
import { readdirSync } from "node:fs";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);

const ROOT_GUESS = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

/**
 * `sharp`, wherever pnpm happens to have put it.
 *
 * It is **not** a dependency of this repository and is deliberately not being made one: it is a
 * native module with a platform-specific binary, and taking it on so that a script run twice a year
 * can resolve it would put it in every install and every CI image. It is present anyway, as a
 * transitive dependency of Next's image optimiser, so this looks for it there — and says what to do
 * when it is absent rather than failing with a bare MODULE_NOT_FOUND.
 */
function loadSharp() {
  const candidates = [
    "sharp",
    ...["apps/web", "apps/marketing"].map((app) =>
      path.join(ROOT_GUESS, app, "node_modules", "sharp")
    ),
  ];

  for (const candidate of candidates) {
    try {
      return require(candidate);
    } catch {
      // try the next one
    }
  }

  // pnpm's content-addressed store: `node_modules/.pnpm/sharp@<version>/node_modules/sharp`.
  const store = path.join(ROOT_GUESS, "node_modules", ".pnpm");
  try {
    const found = readdirSync(store)
      .filter((entry) => entry.startsWith("sharp@"))
      .sort()
      .reverse();
    for (const entry of found) {
      try {
        return require(path.join(store, entry, "node_modules", "sharp"));
      } catch {
        // try the next one
      }
    }
  } catch {
    // no .pnpm directory; fall through to the message below
  }

  throw new Error(
    "sharp could not be resolved. It is not a dependency of this repository — see loadSharp(). " +
      "Run `pnpm install` (it arrives with Next), or `pnpm dlx --package=sharp node " +
      "scripts/build-brand-assets.mjs`."
  );
}

const ROOT = ROOT_GUESS;
const SOURCE = path.join(ROOT, "brand");

const sharp = loadSharp();

/** Where the derived set lands. Both applications get their own copy — see the note below. */
const TARGETS = [
  path.join(ROOT, "apps", "marketing", "public", "brand"),
  path.join(ROOT, "apps", "web", "public", "brand"),
  /*
   * The documentation site renders the same lockup in its Fumadocs navbar, and the monogram is a
   * `mask-image` at an origin-relative path — so it needs the file on its own origin, exactly as
   * the other two do. `@workspace/ui/components/logo` says the same thing from the other side.
   */
  path.join(ROOT, "apps", "docs", "public", "brand"),
];

/**
 * The monogram's rendered size, in pixels.
 *
 * It is displayed at 20-28 px in a header and 24 px in the footer, so 192 covers a 3x display with
 * room to spare and costs about 6 kB. Larger would be paying for pixels no surface asks for; the
 * favicon set (16/32/48/96/180/192/512) is generated separately and already covers the icon sizes.
 */
const MARK_PX = 192;

/** Extracts the one base64 PNG embedded in a Figma "vector" export. */
async function embeddedRaster(file) {
  const svg = await readFile(path.join(SOURCE, file), "utf8");
  const match = svg.match(/xlink:href="data:image\/png;base64,([^"]+)"/);
  if (!match) throw new Error(`${file} carries no embedded PNG; has the export changed?`);
  return Buffer.from(match[1], "base64");
}

/**
 * The tight bounding box of everything non-transparent in one horizontal band.
 *
 * Measured rather than hard-coded, so a re-export whose artwork sits a few pixels over still
 * produces a correctly trimmed mark instead of a clipped one. `> 16` rather than `> 0` on the alpha:
 * Figma's export has a faint halo of near-zero alpha around the strokes, and trimming to that would
 * leave a few pixels of transparent margin on every side.
 */
async function alphaBands(png) {
  const image = sharp(png).ensureAlpha();
  const { width, height } = await image.metadata();
  const { data } = await image.raw().toBuffer({ resolveWithObject: true });

  const filled = [];
  for (let y = 0; y < height; y += 1) {
    let any = false;
    for (let x = 0; x < width && !any; x += 1) {
      if (data[(y * width + x) * 4 + 3] > 16) any = true;
    }
    filled.push(any);
  }

  const bands = [];
  let start = -1;
  for (let y = 0; y <= height; y += 1) {
    const on = y < height && filled[y];
    if (on && start < 0) start = y;
    if (!on && start >= 0) {
      let x0 = width;
      let x1 = 0;
      for (let y2 = start; y2 < y; y2 += 1) {
        for (let x = 0; x < width; x += 1) {
          if (data[(y2 * width + x) * 4 + 3] > 16) {
            if (x < x0) x0 = x;
            if (x > x1) x1 = x;
          }
        }
      }
      bands.push({ top: start, left: x0, width: x1 - x0 + 1, height: y - start });
      start = -1;
    }
  }
  return bands;
}

/**
 * The monogram, trimmed to its ink and centred in a transparent square.
 *
 * Square because every surface that shows it — a header slot, a footer, a favicon, the PDF masthead —
 * reserves a square box, and a non-square asset would need each of them to know the aspect ratio.
 * Centred with `contain`, so the glyph keeps its proportions rather than being stretched to fill.
 */
async function buildMark() {
  const png = await embeddedRaster("tr-icon.svg");
  const bands = await alphaBands(png);
  if (bands.length === 0) throw new Error("tr-icon.svg's raster is entirely transparent");

  // The first band is the monogram; the second, when present, is the wordmark beneath it. Taking
  // the first by position rather than the largest by area, because "the mark is above the words" is
  // a fact about the lockup and "the mark has more ink" is a coincidence.
  const mark = bands[0];
  console.log(
    `  monogram found at ${mark.left},${mark.top} ${mark.width}x${mark.height}`
  );

  return sharp(png)
    .extract({
      left: mark.left,
      top: mark.top,
      width: mark.width,
      height: mark.height,
    })
    .resize(MARK_PX, MARK_PX, {
      fit: "contain",
      background: { r: 0, g: 0, b: 0, alpha: 0 },
    })
    .png({ compressionLevel: 9, palette: true })
    .toBuffer();
}

/**
 * The wordmark, retargeted so it can be dropped into a layout.
 *
 * Three changes to the export, and each is load-bearing:
 *
 * 1. **`fill="currentColor"`** instead of the hard-coded `#1E1E1E`. The wordmark then inherits
 *    whatever the surface sets, which is what lets one file serve a light header, a dark footer and
 *    a muted variant without three copies of the path data.
 * 2. **A tight `viewBox`.** The export is an 809x809 square with the words floating in the middle of
 *    it, so `height: 1.5rem` would render a 1.5rem *square* with a quarter-rem of text in it. The
 *    box is narrowed to the glyphs, so the SVG's own aspect ratio is the wordmark's.
 * 3. **No `width`/`height` attributes.** With those present the element ignores CSS sizing in some
 *    engines; without them, and with a viewBox, it scales to whatever the container says.
 *
 * The viewBox is computed by rendering the file and measuring, then mapping back into the export's
 * own coordinate space — so it stays correct if the designer re-exports at a different canvas size.
 */
async function buildWordmark() {
  const file = path.join(SOURCE, "tr-text.svg");
  const svg = await readFile(file, "utf8");

  const canvas = svg.match(/viewBox="0 0 (\d+(?:\.\d+)?) (\d+(?:\.\d+)?)"/);
  if (!canvas) throw new Error("tr-text.svg has no parseable viewBox");
  const canvasWidth = Number(canvas[1]);
  const canvasHeight = Number(canvas[2]);

  // Rendered at 2x the canvas so the measured box is accurate to half a user unit.
  const scale = 2;
  const rendered = await sharp(Buffer.from(svg), { density: 72 * scale })
    .resize({ width: Math.round(canvasWidth * scale) })
    .png()
    .toBuffer();
  const bands = await alphaBands(rendered);
  if (bands.length === 0) throw new Error("tr-text.svg rendered empty");

  const top = Math.min(...bands.map((band) => band.top));
  const bottom = Math.max(...bands.map((band) => band.top + band.height));
  const left = Math.min(...bands.map((band) => band.left));
  const right = Math.max(...bands.map((band) => band.left + band.width));

  // Back into the export's coordinate space, with one unit of bleed so an anti-aliased edge is not
  // clipped by a box measured from thresholded alpha.
  const bleed = 1;
  const box = {
    x: Math.max(0, left / scale - bleed),
    y: Math.max(0, top / scale - bleed),
    width: Math.min(canvasWidth, (right - left) / scale + bleed * 2),
    height: Math.min(canvasHeight, (bottom - top) / scale + bleed * 2),
  };
  const round = (value) => Math.round(value * 100) / 100;
  console.log(
    `  wordmark box ${round(box.x)},${round(box.y)} ${round(box.width)}x${round(box.height)}`
  );

  const header = [
    "<!-- Generated by scripts/build-brand-assets.mjs from brand/tr-text.svg. Do not hand-edit. -->",
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${round(box.x)} ${round(box.y)} ${round(box.width)} ${round(box.height)}"`,
    ' fill="currentColor" role="img" aria-label="azmoth">',
  ].join("");

  const body = svg
    .replace(/^[\s\S]*?<svg[^>]*>/, "")
    .replace(/<\/svg>\s*$/, "")
    .replaceAll('fill="#1E1E1E"', "")
    .replaceAll('fill="none"', "")
    .trim();

  return `${header}\n${body}\n</svg>\n`;
}

/**
 * The monogram as a `data:` URI in a TypeScript module, for the Open Graph card.
 *
 * The card is drawn by Satori at request time (`src/lib/og-image.tsx`), and Satori needs the image
 * bytes. Neither of the two obvious ways to give it them is safe here:
 *
 * - **An absolute URL** makes rendering the card depend on a network fetch. `og-image.tsx` already
 *   refuses to fetch a font for exactly this reason — *"a fetch that fails takes the whole route
 *   with it"* — and an OG route that 500s when a CDN blinks is a social preview that silently stops
 *   working.
 * - **`readFileSync` from `public/`** depends on the file being traced into whatever the deployment
 *   bundles. It works locally and is the classic thing that breaks only in production.
 *
 * A generated module is neither: the compiler bundles it like any other import, so there is nothing
 * to fetch and nothing to trace. The cost is ~13 kB of base64 in the repository, in a file that says
 * at the top that it is generated.
 */
async function writeDataUriModule(mark) {
  const file = path.join(
    ROOT,
    "apps",
    "marketing",
    "src",
    "lib",
    "brand-mark.ts"
  );
  const source = `/**
 * The Azmoth monogram as a data URI.
 *
 * **Generated by \`scripts/build-brand-assets.mjs\` from \`brand/tr-icon.svg\`. Do not hand-edit.**
 *
 * It exists as a module rather than as a file read or a URL fetch because the Open Graph card is
 * drawn by Satori at request time, and both of those alternatives can fail at request time — see the
 * generator for the full reasoning. Imported by \`src/lib/og-image.tsx\`.
 *
 * The same artwork is served as \`/brand/azmoth-mark.png\` for the header and footer; this copy is
 * for the one consumer that cannot load it over HTTP.
 */
export const AZMOTH_MARK_DATA_URI =
  "data:image/png;base64,${mark.toString("base64")}";
`;
  await writeFile(file, source, "utf8");
  console.log(
    `  wrote ${path.relative(ROOT, file)} (${(
      Buffer.byteLength(source) / 1024
    ).toFixed(1)} kB)`
  );
}

async function main() {
  console.log(`brand assets from ${path.relative(process.cwd(), SOURCE)}`);

  const mark = await buildMark();
  const wordmark = await buildWordmark();

  for (const target of TARGETS) {
    await mkdir(target, { recursive: true });
    await writeFile(path.join(target, "azmoth-mark.png"), mark);
    await writeFile(path.join(target, "azmoth-wordmark.svg"), wordmark, "utf8");
    console.log(
      `  wrote ${path.relative(ROOT, target)}/ ` +
        `(mark ${(mark.length / 1024).toFixed(1)} kB, wordmark ${(
          Buffer.byteLength(wordmark) / 1024
        ).toFixed(1)} kB)`
    );
  }

  await writeDataUriModule(mark);
}

await main();
