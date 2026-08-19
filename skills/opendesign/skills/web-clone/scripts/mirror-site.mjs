#!/usr/bin/env node
// mirror-site.mjs — mirrors the full deployed asset set of a "statically built site" (Astro / Vite SSG / Hugo, etc.)
// to produce a faithful 1:1 clone.
// Principle: for these sites the "real source" isn't on GitHub, but the deployed static assets (HTML + bundle + CSS +
//       runtime-fetched .sog/.buf/.wasm/.riv/fonts/images) are the ground truth. Use a real browser to scroll through
//       the entire page, capture every real request, and mirror same-origin assets by path.
// Usage:
//   node scripts/mirror-site.mjs --url <URL> --out <dir> [--scroll-step 700] [--settle 2500] [--max-ms 90000]
// Output:
//   <dir>/site/...                mirrored same-origin assets (paths preserved; directory URLs saved as index.html)
//   <dir>/mirror-manifest.json    all requests (same-origin + third-party) with status for each
//   <dir>/own-asset-urls.txt      list of same-origin asset paths
//   <dir>/third-party.json        third-party hosts + hints for webfont CSS (typekit/google) that needs self-hosting
// Discipline: only move assets that were "actually requested" — never guess at paths. Third-party CDNs (fonts/wasm/video)
//       are not auto-rewritten — handle them manually per third-party.json.
//       Follow-up manual steps: self-host domain-locked fonts (typical Typekit @import) → rewrite CSS @import to local →
//       strip tracking → serve site/ as the web root.
//       Full recipe in references/static-mirror.md.

import { loadPlaywright, launchChromium } from "./lib/playwright-loader.mjs";
import fs from "node:fs";
import path from "node:path";

function parseArgs(argv) {
  const o = { url: "", out: "", scrollStep: 700, settle: 2500, maxMs: 90000, help: false };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--help" || a === "-h") o.help = true;
    else if (a === "--url") o.url = argv[++i] || "";
    else if (a === "--out") o.out = argv[++i] || "";
    else if (a === "--scroll-step") o.scrollStep = parseInt(argv[++i] || "700", 10);
    else if (a === "--settle") o.settle = parseInt(argv[++i] || "2500", 10);
    else if (a === "--max-ms") o.maxMs = parseInt(argv[++i] || "90000", 10);
  }
  return o;
}

function usage() {
  console.log(`mirror-site.mjs — full asset mirror of a statically built site (faithful 1:1 clone)

  node scripts/mirror-site.mjs --url <URL> --out <dir> [--scroll-step 700] [--settle 2500] [--max-ms 90000]

Suitable for: Astro / Vite SSG / Hugo / any site whose client runtime outputs downloadable static assets (including heavy WebGL/Canvas frontends).
Not suitable for: true server-side-rendered / data-driven SPAs (use network-capture.mjs to stub the API instead).
Recipe and follow-up rewrite steps (self-host fonts/strip tracking/serve) → references/static-mirror.md`);
}

// same-origin asset URL → local relative path (strip query string; directory-ending paths saved as index.html)
function urlToLocalPath(u, origin) {
  let p = u.slice(origin.length);
  const q = p.indexOf("?");
  if (q >= 0) p = p.slice(0, q);
  if (p === "" || p.endsWith("/")) p += "index.html";
  return p.replace(/^\/+/, "");
}

const args = parseArgs(process.argv.slice(2));
if (args.help || !args.url || !args.out) {
  usage();
  process.exit(args.help ? 0 : 1);
}

const origin = new URL(args.url).origin;
const siteDir = path.join(path.resolve(args.out), "site");
fs.mkdirSync(siteDir, { recursive: true });

const responses = new Map(); // url -> {status, type, ct}
const pw = loadPlaywright();
const browser = await launchChromium(pw.chromium);
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
const page = await ctx.newPage();
page.on("response", (resp) => {
  try {
    const h = resp.headers();
    responses.set(resp.url(), { status: resp.status(), type: resp.request().resourceType(), ct: h["content-type"] || "" });
  } catch {}
});

console.log(`▸ Loading + capturing via full scroll: ${args.url}`);
await page.goto(args.url, { waitUntil: "networkidle", timeout: args.maxMs }).catch((e) => console.warn("  goto:", e.message));
const total = await page.evaluate(() => document.documentElement.scrollHeight);
for (let y = 0; y <= total; y += args.scrollStep) {
  await page.evaluate((yy) => window.scrollTo(0, yy), y);
  await page.waitForTimeout(180);
}
await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
await page.waitForTimeout(args.settle);
await page.evaluate(() => window.scrollTo(0, 0));
await page.waitForTimeout(1200);

const all = [...responses.entries()].map(([url, m]) => ({ url, ...m }));
const ownUrls = all.filter((r) => r.url.startsWith(origin + "/") || r.url === origin || r.url === origin + "/");

console.log(`▸ Captured ${all.length} requests; ${ownUrls.length} same-origin, starting download…`);
let ok = 0, fail = 0;
const failed = [];
for (const r of ownUrls) {
  const rel = urlToLocalPath(r.url, origin);
  const dest = path.join(siteDir, rel);
  try {
    const resp = await ctx.request.get(r.url); // reuse the browser's network stack (consistent cookies/TUN/proxy)
    if (!resp.ok()) { fail++; failed.push(`HTTP${resp.status()} ${rel}`); continue; }
    const buf = await resp.body();
    fs.mkdirSync(path.dirname(dest), { recursive: true });
    fs.writeFileSync(dest, buf);
    ok++;
  } catch (e) {
    fail++; failed.push(`${e.message} ${rel}`);
  }
}

// third-party + webfont hints
const thirdHosts = [...new Set(all.filter((r) => !r.url.startsWith(origin)).map((r) => { try { return new URL(r.url).host; } catch { return r.url; } }))];
const webfontCss = all.map((r) => r.url).filter((u) => /use\.typekit\.net\/[a-z0-9]+\.css|fonts\.googleapis\.com\/css/i.test(u));
const outRoot = path.resolve(args.out);
fs.writeFileSync(path.join(outRoot, "mirror-manifest.json"), JSON.stringify(all, null, 2));
fs.writeFileSync(path.join(outRoot, "own-asset-urls.txt"), ownUrls.map((r) => urlToLocalPath(r.url, origin)).sort().join("\n") + "\n");
fs.writeFileSync(path.join(outRoot, "third-party.json"), JSON.stringify({ hosts: thirdHosts, webfont_css_to_selfhost: webfontCss }, null, 2));

console.log(`✅ Mirror complete: ${ok} succeeded / ${fail} failed → ${siteDir}`);
if (failed.length) console.log("  ⚠️ Failed:\n   " + failed.slice(0, 20).join("\n   "));
console.log(`▸ Third-party hosts: ${thirdHosts.join(", ") || "(none)"}`);
if (webfontCss.length) console.log(`▸ Webfont CSS that needs self-hosting (domain-locked, see static-mirror.md): \n   ${webfontCss.join("\n   ")}`);
console.log(`▸ Next steps: self-host fonts + rewrite CSS @import + strip tracking → cd ${siteDir} && python3 -m http.server 8124`);
await browser.close();
