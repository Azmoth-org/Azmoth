#!/usr/bin/env node
/**
 * i18n coverage checker for the SILKDEV custom I18nProvider setup.
 *
 * Mirrors the kind of report i18n-ally produces for the messages/ folder:
 *   1. MISSING      — keys referenced in code (t("...") / t.raw("...")) but
 *                     absent from a locale's messages/<locale>.json
 *   2. UNUSED       — keys present in the base locale JSON but never referenced
 *   3. STRUCTURE    — leaf paths present in the base locale but missing from
 *                     other locales (catches whole dropped sub-sections)
 *   4. DYNAMIC      — template-literal / variable keys that static analysis
 *                     cannot resolve (and which often fail at runtime)
 *   5. UNKNOWN NS   — useTranslations("<ns>") where <ns> is not a top-level key
 *
 * Parsing is done with the TypeScript compiler API (already a devDependency),
 * so no new packages are needed. No build step required.
 *
 * Usage:
 *   node scripts/i18n-coverage.mjs                 # all locales vs en (base)
 *   node scripts/i18n-coverage.mjs --locales fr    # only fr (plus base table)
 *   node scripts/i18n-coverage.mjs --base en       # which locale is source of truth
 *   node scripts/i18n-coverage.mjs --ci            # exit 1 if any locale has missing keys
 *   node scripts/i18n-coverage.mjs --json          # machine-readable JSON on stdout
 *   node scripts/i18n-coverage.mjs --src src --messages messages
 */

import ts from "typescript";
import { readFileSync, readdirSync } from "node:fs";
import { join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = fileURLToPath(new URL(".", import.meta.url));
const root = resolve(__dirname, "..");

// ---------------------------------------------------------------------------
// CLI args
// ---------------------------------------------------------------------------
const args = process.argv.slice(2);
const flag = (name, def) => {
  const i = args.indexOf(name);
  return i === -1 ? def : args[i + 1];
};
const has = (name) => args.includes(name);

const srcDir = resolve(root, flag("--src", "src"));
const messagesDir = resolve(root, flag("--messages", "messages"));
const baseLocale = flag("--base", "en");
const wantLocales = flag("--locales", "")
  .split(",")
  .map((s) => s.trim())
  .filter(Boolean);
const jsonOut = has("--json");
const ciMode = has("--ci");
const showAllUnused = has("--all-unused"); // show unused even when > 50 entries

// ---------------------------------------------------------------------------
// Load messages
// ---------------------------------------------------------------------------
const dicts = {};
for (const f of readdirSync(messagesDir).filter((f) => f.endsWith(".json"))) {
  dicts[f.replace(/\.json$/, "")] = JSON.parse(readFileSync(join(messagesDir, f), "utf8"));
}
if (!dicts[baseLocale]) {
  console.error(`i18n-coverage: unknown base locale "${baseLocale}" (have: ${Object.keys(dicts).join(", ")})`);
  process.exit(2);
}
const locales = wantLocales.length
  ? wantLocales
  : Object.keys(dicts).filter((l) => l !== baseLocale);
for (const l of locales) {
  if (!dicts[l]) {
    console.error(`i18n-coverage: unknown locale "${l}" (have: ${Object.keys(dicts).join(", ")})`);
    process.exit(2);
  }
}
const namespaces = Object.keys(dicts[baseLocale]).filter((k) => k !== "$schema");

// ---------------------------------------------------------------------------
// Scan source files with the TS compiler API
// ---------------------------------------------------------------------------
function walkDir(dir) {
  const out = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const p = join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === "node_modules" || entry.name.startsWith(".")) continue;
      out.push(...walkDir(p));
    } else if (/\.(ts|tsx|js|jsx)$/.test(entry.name)) {
      out.push(p);
    }
  }
  return out;
}

const SCRIPT_KIND = {
  ".ts": ts.ScriptKind.TS,
  ".tsx": ts.ScriptKind.TSX,
  ".js": ts.ScriptKind.JS,
  ".jsx": ts.ScriptKind.JSX,
};

/** binding name -> { namespace, dynamicNamespace, file, line } */
const bindings = new Map();
/** resolved usages: { namespace, key, dynamic, pattern, file, line, isRaw, via } */
const usages = [];
/** useTranslations(<non-literal>) */
const dynamicNamespaces = [];

for (const file of walkDir(srcDir)) {
  const text = readFileSync(file, "utf8");
  const kind = SCRIPT_KIND[file.slice(file.lastIndexOf("."))] ?? ts.ScriptKind.TSX;
  const sf = ts.createSourceFile(file, text, ts.ScriptTarget.Latest, true, kind);
  const rel = relative(root, file);
  /** per-file constant resolution (dynamic-key heuristics) */
  const constArrays = new Map(); // name -> string[]
  const constStrings = new Map(); // name -> string
  const paramArrays = new Map(); // callback/loop param -> string[]

  function visit(node) {
    // ── collect per-file constants for resolving dynamic keys ──
    // const NAME = ["a", "b"] / const NAME = "a"
    if (ts.isVariableDeclaration(node) && ts.isIdentifier(node.name)) {
      let init = node.initializer;
      while (init && (ts.isAsExpression(init) || ts.isParenthesizedExpression(init))) init = init.expression;
      if (init && ts.isArrayLiteralExpression(init)) {
        const values = [];
        let allStrings = true;
        for (const el of init.elements) {
          if (ts.isStringLiteral(el)) values.push(el.text);
          else {
            allStrings = false;
            break;
          }
        }
        if (allStrings && values.length) constArrays.set(node.name.text, values);
      } else if (init && ts.isStringLiteral(init)) {
        constStrings.set(node.name.text, init.text);
      }
    }
    // ARR.map((k, i) => ...) / ARR.forEach((k) => ...) where ARR is a const array
    if (
      ts.isPropertyAccessExpression(node) &&
      (node.name.text === "map" || node.name.text === "forEach") &&
      node.parent &&
      ts.isCallExpression(node.parent)
    ) {
      const receiver = node.expression;
      if (ts.isIdentifier(receiver) && constArrays.has(receiver.text)) {
        const cb = node.parent.arguments[0];
        if (cb && (ts.isArrowFunction(cb) || ts.isFunctionExpression(cb)) && cb.parameters.length > 0) {
          const p = cb.parameters[0].name;
          if (ts.isIdentifier(p)) paramArrays.set(p.text, constArrays.get(receiver.text));
        }
      }
    }
    // for (const k of ARR)
    if (ts.isForOfStatement(node) && ts.isIdentifier(node.expression) && constArrays.has(node.expression.text)) {
      const decl = node.initializer.declarations[0];
      if (decl && ts.isIdentifier(decl.name)) paramArrays.set(decl.name.text, constArrays.get(node.expression.text));
    }

    if (ts.isCallExpression(node)) {
      const callee = node.expression;
      const isUseTranslations =
        (ts.isIdentifier(callee) && callee.text === "useTranslations") ||
        (ts.isPropertyAccessExpression(callee) && callee.name.text === "useTranslations");

      if (isUseTranslations) {
        const arg = node.arguments[0];
        let namespace = null;
        let dynamic = false;
        if (arg && ts.isStringLiteral(arg)) namespace = arg.text;
        else if (arg && ts.isTemplateLiteral(arg) && arg.templateSpans.length === 0) namespace = arg.text;
        else if (arg) {
          dynamic = true;
          namespace = arg.getText(sf);
        }

        // resolve the binding: `const t = useTranslations(...)` / `t = useTranslations(...)`
        let binding = null;
        const p1 = node.parent;
        if (p1 && ts.isVariableDeclaration(p1) && ts.isIdentifier(p1.name)) binding = p1.name.text;
        else if (p1 && ts.isBinaryExpression(p1) && ts.isIdentifier(p1.left)) binding = p1.left.text;

        const line = sf.getLineAndCharacterOfPosition(node.getStart(sf)).line + 1;
        if (binding) {
          bindings.set(binding, { namespace, dynamicNamespace: dynamic, file: rel, line });
          if (dynamic) dynamicNamespaces.push({ binding, expr: namespace, file: rel, line });
        } else {
          dynamicNamespaces.push({ binding: "(unassigned)", expr: namespace, file: rel, line });
        }
      } else {
        // usage of a bound translator: t("key") or t.raw("key")
        let binding = null;
        let isRaw = false;
        if (ts.isIdentifier(callee)) {
          binding = callee.text;
        } else if (
          ts.isPropertyAccessExpression(callee) &&
          callee.name.text === "raw" &&
          ts.isIdentifier(callee.expression)
        ) {
          binding = callee.expression.text;
          isRaw = true;
        }
        if (binding && bindings.has(binding)) {
          const b = bindings.get(binding);
          const arg = node.arguments[0];
          let keys = null; // one or more statically-resolved keys
          let dynamic = false;
          let pattern = null;
          let via = null; // how an identifier arg was resolved
          if (arg && ts.isStringLiteral(arg)) {
            keys = [arg.text];
          } else if (arg && ts.isTemplateLiteral(arg)) {
            if (arg.templateSpans.length === 0) keys = [arg.text];
            else {
              dynamic = true;
              pattern =
                arg.head.text +
                arg.templateSpans
                  .map((s) => `\${${s.expression.getText(sf)}}${s.literal.text}`)
                  .join("");
            }
          } else if (arg && ts.isIdentifier(arg)) {
            const name = arg.text;
            if (constStrings.has(name)) {
              keys = [constStrings.get(name)];
              via = name;
            } else if (constArrays.has(name)) {
              keys = constArrays.get(name);
              via = name;
            } else if (paramArrays.has(name)) {
              keys = paramArrays.get(name);
              via = name;
            } else {
              dynamic = true;
              pattern = name;
            }
          } else if (arg) {
            dynamic = true;
            pattern = arg.getText(sf);
          }
          const line = sf.getLineAndCharacterOfPosition(node.getStart(sf)).line + 1;
          if (keys) {
            for (const k of keys) {
              usages.push({ namespace: b.namespace, key: k, dynamic: false, pattern: null, file: rel, line, isRaw, via });
            }
          } else {
            usages.push({ namespace: b.namespace, key: null, dynamic, pattern, file: rel, line, isRaw, via });
          }
        }
      }
    }
    ts.forEachChild(node, visit);
  }
  visit(sf);
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function resolvePath(obj, path) {
  const parts = path.split(/\.|\[|\]/).filter(Boolean);
  let cur = obj;
  for (const p of parts) {
    if (cur == null || typeof cur !== "object" || !(p in cur)) return undefined;
    cur = cur[p];
  }
  return cur;
}

/** Matches runtime behaviour of I18nProvider#t: flat lookup, but also accepts
 *  dotted paths for reporting purposes (they'd fail at runtime, flagged later). */
function hasKey(dict, ns, key) {
  const nsObj = dict[ns];
  if (nsObj == null || typeof nsObj !== "object") return false;
  if (!key.includes(".") && !key.includes("[")) return key in nsObj;
  return resolvePath(nsObj, key) !== undefined;
}

/** Flatten a JSON object to leaf paths; arrays become `name[0]`, `name[1]`, … */
function flatten(obj, prefix = "", out = []) {
  if (obj === null || typeof obj !== "object") {
    if (prefix) out.push(prefix);
    return out;
  }
  if (Array.isArray(obj)) {
    obj.forEach((v, i) => flatten(v, `${prefix}[${i}]`, out));
  } else {
    for (const [k, v] of Object.entries(obj)) {
      const p = prefix ? `${prefix}.${k}` : k;
      flatten(v, p, out);
    }
  }
  return out;
}

// ---------------------------------------------------------------------------
// Analysis
// ---------------------------------------------------------------------------
/** ns -> Map<key, [{file,line}]>  (static usages only) */
const usedByNs = new Map();
for (const u of usages) {
  if (u.dynamic) continue;
  if (!usedByNs.has(u.namespace)) usedByNs.set(u.namespace, new Map());
  const m = usedByNs.get(u.namespace);
  if (!m.has(u.key)) m.set(u.key, []);
  m.get(u.key).push({ file: u.file, line: u.line });
}

const dynamicKeys = usages.filter((u) => u.dynamic);
const dottedKeys = usages.filter((u) => !u.dynamic && /[.\[]/.test(u.key));

/** namespaces referenced in code that don't exist in the base dictionary */
const unknownNamespaces = [...usedByNs.keys()].filter((ns) => !namespaces.includes(ns));

/** per-locale coverage + missing lists */
const report = {};
for (const locale of [baseLocale, ...locales]) {
  const dict = dicts[locale];
  const perNs = {};
  let totalUsed = 0;
  let totalPresent = 0;
  const missing = [];
  for (const ns of namespaces) {
    const keyMap = usedByNs.get(ns);
    const used = keyMap ? keyMap.size : 0;
    let present = 0;
    const miss = [];
    if (keyMap) {
      for (const [key, refs] of keyMap) {
        if (hasKey(dict, ns, key)) present += 1;
        else miss.push({ key, refs });
      }
    }
    perNs[ns] = { used, present, missing: miss };
    totalUsed += used;
    totalPresent += present;
    missing.push(...miss.map((m) => ({ ns, ...m })));
  }
  report[locale] = {
    perNs,
    totalUsed,
    totalPresent,
    missing,
    coverage: totalUsed === 0 ? 100 : Math.round((totalPresent / totalUsed) * 1000) / 10,
  };
}

/** unused keys in the base locale */
const usedTop = new Map();
for (const [ns, m] of usedByNs) {
  const s = new Set();
  for (const key of m.keys()) s.add(key.split(/\.|\[/)[0]);
  usedTop.set(ns, s);
}
// dynamic patterns still mark their first segment as used (e.g. `ctaService.${x}.title`)
for (const u of dynamicKeys) {
  if (!u.pattern) continue;
  const first = u.pattern.split(/\.|\[/)[0];
  if (first && usedByNs.has(u.namespace)) usedTop.get(u.namespace).add(first);
}
const unused = [];
for (const ns of namespaces) {
  const nsObj = dicts[baseLocale][ns];
  if (nsObj == null || typeof nsObj !== "object") continue;
  const used = usedTop.get(ns) ?? new Set();
  for (const key of Object.keys(nsObj)) {
    if (!used.has(key)) unused.push({ ns, key });
  }
}

/** structural parity: base leaf paths missing from other locales */
const basePaths = flatten(dicts[baseLocale]).filter((p) => p !== "$schema");
const structural = {};
for (const locale of locales) {
  const present = new Set(flatten(dicts[locale]));
  structural[locale] = basePaths.filter((p) => !present.has(p));
}

// ---------------------------------------------------------------------------
// Output
// ---------------------------------------------------------------------------
if (jsonOut) {
  console.log(
    JSON.stringify(
      {
        scannedFiles: walkDir(srcDir).map((f) => relative(root, f)),
        baseLocale,
        namespaces,
        report,
        unused,
        dynamicKeys: dynamicKeys.map((d) => ({
          namespace: d.namespace,
          pattern: d.pattern,
          file: d.file,
          line: d.line,
        })),
        dottedKeys: dottedKeys.map((d) => ({
          namespace: d.namespace,
          key: d.key,
          file: d.file,
          line: d.line,
        })),
        unknownNamespaces,
        structural,
        dynamicNamespaces,
      },
      null,
      2
    )
  );
  process.exit(ciMode && Object.values(report).some((r) => r.missing.length > 0) ? 1 : 0);
}

const filesScanned = walkDir(srcDir).length;
const totalStaticKeys = new Set(
  usages.filter((u) => !u.dynamic).map((u) => `${u.namespace}.${u.key}`)
).size;

console.log(`i18n coverage — ${relative(root, srcDir) || srcDir}`);
console.log(
  `Scanned ${filesScanned} source file(s), ${namespaces.length} namespace(s), ` +
    `${totalStaticKeys} distinct static key(s) referenced, ` +
    `${dynamicKeys.length} dynamic key usage(s).\n`
);

// --- summary table ---
const header = `  ${"locale".padEnd(9)}${"used".padStart(6)}${"present".padStart(9)}${"missing".padStart(9)}${"coverage".padStart(10)}`;
console.log(header);
console.log("  " + "-".repeat(header.length - 2));
for (const locale of [baseLocale, ...locales]) {
  const r = report[locale];
  console.log(
    `  ${locale.padEnd(9)}${String(r.totalUsed).padStart(6)}${String(r.totalPresent).padStart(9)}` +
      `${String(r.missing.length).padStart(9)}${String(r.coverage + "%").padStart(10)}`
  );
}
console.log();

// --- per-namespace matrix ---
console.log("Coverage per namespace:");
const nsHeader = `  ${"namespace".padEnd(24)}` + locales.map((l) => l.padStart(9)).join("") + `    ${baseLocale}`;
console.log(nsHeader);
console.log("  " + "-".repeat(nsHeader.length - 2));
for (const ns of namespaces) {
  const row = `  ${ns.padEnd(24)}`;
  const cells = locales.map((l) => {
    const p = report[l].perNs[ns];
    if (!p || p.used === 0) return "   —  ";
    return String(Math.round((p.present / p.used) * 1000) / 10 + "%").padStart(9);
  });
  const baseP = report[baseLocale].perNs[ns];
  const baseCell = baseP && baseP.used > 0 ? String(Math.round((baseP.present / baseP.used) * 1000) / 10 + "%").padStart(9) : "   —  ";
  console.log(row + cells.join("") + `    ${baseCell}`);
}
console.log();

// --- missing keys ---
const anyMissing = Object.values(report).some((r) => r.missing.length > 0);
if (anyMissing) {
  console.log("MISSING — referenced in code, absent from locale JSON:");
  for (const locale of [baseLocale, ...locales]) {
    const miss = report[locale].missing;
    if (miss.length === 0) continue;
    console.log(`\n  ${locale} (${miss.length}):`);
    for (const m of miss) {
      const refs = m.refs.map((r) => `${r.file}:${r.line}`).join(", ");
      console.log(`    ${m.ns}.${m.key}`);
      console.log(`        used at ${refs}`);
    }
  }
  console.log();
} else {
  console.log("MISSING — none. Every static key referenced in code exists in all locales.\n");
}

// --- unknown namespaces ---
if (unknownNamespaces.length) {
  console.log(`UNKNOWN NAMESPACES — useTranslations() with a namespace that is not a top-level key of ${baseLocale}.json:`);
  for (const ns of unknownNamespaces) {
    for (const [key, refs] of usedByNs.get(ns) ?? []) {
      console.log(`  ${ns} — "${key}" at ${refs.map((r) => `${r.file}:${r.line}`).join(", ")}`);
    }
  }
  console.log();
}

// --- dotted static keys ---
if (dottedKeys.length) {
  console.log("DOTTED STATIC KEYS — t() performs a FLAT lookup (dict[namespace][key]);");
  console.log("  these keys will NOT resolve at runtime and render the raw key string:");
  for (const d of dottedKeys) {
    console.log(`  ${d.namespace}.${d.key} → ${d.file}:${d.line}`);
  }
  console.log();
}

// --- dynamic keys ---
if (dynamicKeys.length) {
  console.log("DYNAMIC KEYS — template literals / variables, unverifiable statically:");
  for (const d of dynamicKeys) {
    console.log(`  ${d.namespace}: ${d.pattern} → ${d.file}:${d.line}`);
  }
  console.log(
    "  Note: verify these resolve at runtime. With the flat t() lookup, dotted\n" +
      "  patterns (e.g. `ctaService.ctaWeb.title`) render the raw key string.\n"
  );
}

// --- unused ---
if (unused.length) {
  const shown = showAllUnused ? unused : unused.slice(0, 50);
  console.log(`UNUSED — present in ${baseLocale}.json but never referenced in code (${unused.length}):`);
  for (const u of shown) console.log(`  ${u.ns}.${u.key}`);
  if (shown.length < unused.length) console.log(`  … and ${unused.length - shown.length} more (pass --all-unused to list them all)`);
  console.log();
} else {
  console.log("UNUSED — none.\n");
}

// --- structural parity ---
const anyStructural = Object.values(structural).some((v) => v.length > 0);
if (anyStructural) {
  console.log("STRUCTURE GAPS — leaf paths present in base locale but missing from other locales:");
  for (const [locale, paths] of Object.entries(structural)) {
    if (paths.length === 0) continue;
    console.log(`\n  ${locale} (${paths.length}):`);
    const shown = paths.slice(0, 30);
    for (const p of shown) console.log(`    ${p}`);
    if (shown.length < paths.length) console.log(`    … and ${paths.length - shown.length} more`);
  }
  console.log();
} else {
  console.log("STRUCTURE GAPS — none. All locales mirror the base structure.\n");
}

// ---------------------------------------------------------------------------
// Exit code for CI
// ---------------------------------------------------------------------------
if (ciMode) {
  const failures = Object.entries(report).filter(([, r]) => r.missing.length > 0);
  if (failures.length > 0) {
    console.error(
      `i18n-coverage: ${failures.map(([l, r]) => `${l} (${r.missing.length} missing)`).join(", ")}`
    );
    process.exit(1);
  }
}
