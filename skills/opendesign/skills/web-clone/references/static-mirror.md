# 1:1 faithful clone of statically-built sites: full asset mirroring

> Applies to: **Astro / Vite SSG / Hugo / Eleventy / any site whose client-side runtime outputs downloadable static assets** — even if it's a WebGL/Canvas/Gaussian-splat-heavy frontend.
> Does not apply to: true server-side rendering / data-driven SPAs (business data lives behind an API) → use `network-capture.mjs` to stub the API instead — not this approach.

## Core insight (why this achieves 1:1)
For these sites, "**the real source isn't on GitHub**", but **the deployed static assets are the ground truth**: HTML + bundled JS + CSS + binaries fetched at runtime (`.sog`/`.buf`/`.wasm`/`.riv`/fonts/images/video). Mirror these **as-is** and serve them from the web root, and what runs is **the real code + real assets** — not a rebuild — so it can be byte-for-byte 1:1, reproducing even the original site's bugs/quirks.

This is an extension of the "real source above all" rule to static sites: for a static site, "**obtaining the real source**" = "**mirroring the entire deployed asset set**".

> ⚠️ Decision-tree pitfall: don't see `astro:true` and jump to "go find the source theme on a theme marketplace" — that only applies to sites **using an off-the-shelf open-source theme**. **Custom Astro sites (e.g. Lusion oryzo.ai) have no theme you can buy** — the correct approach is the full mirror described here.

## Why you must "capture with a real browser, scrolling through the whole page" — you can't just grep / wget
- Binaries like `.buf`/`.sog`/`.riv` are **fetched by the JS runtime based on scroll progress**, and the URLs are often **assembled dynamically in the code** → grepping the bundle won't find them all, and `wget --mirror` won't discover them either (it only follows static links in the HTML).
- The only reliable method: **load with a real browser and scroll from top to bottom**, recording every **network request that actually happens**, then mirror based on that "list of actual requests".

## One-line script
```bash
node "$WEB_CLONE_SKILL_DIR/scripts/mirror-site.mjs" \
  --url https://<site>/ \
  --out "$WEB_CLONE_PROJECT"
```
Output:
- `<out>/site/…`: mirrored **same-origin** assets (paths preserved; directory URLs saved as `index.html`)
- `<out>/own-asset-urls.txt`: list of same-origin assets
- `<out>/third-party.json`: third-party hosts + hints for **webfont CSS that needs self-hosting** (Typekit/Google)
- `<out>/mirror-manifest.json`: all requests + status

The script uses a real browser to capture the full scroll + downloads via the browser's network stack (cookies/TUN/proxy match the page).

## Manual cleanup after mirroring (to make it run offline, 1:1)
The script only pulls same-origin assets and doesn't rewrite anything automatically — **handle third parties manually per `third-party.json`**:

1. **Self-host domain-locked fonts (most commonly Adobe Typekit)**
   Typekit kits lock authorization to a domain — remote `@import` may fail to render after a domain change → self-host instead:
   ```bash
   # 1. Download the kit CSS (direct connection — Typekit is often blocked by proxies → don't use a proxy)
   curl -sL -A "Mozilla/5.0 …Chrome…" -e "https://<site>/" "https://use.typekit.net/<kit>.css" -o site/typekit/kit.css
   # 2. Extract the use.typekit.net/af/... font URLs from kit.css's @font-face src, download each to site/typekit/fonts/
   #    Each font has 3 suffixes: /l=woff2  /d=woff  /a=otf (verify by file magic number wOF2/wOFF/0x00010000, not the filename)
   # 3. Write local @font-face rules (relative url + keep format hints), see below
   ```
   Local `@font-face`:
   ```css
   @font-face{ font-family:"<same name>"; src:url("./fonts/x.woff2") format("woff2"),
     url("./fonts/x.woff") format("woff"), url("./fonts/x.otf") format("opentype");
     font-display:swap; font-weight:<original range>; }
   ```
   Then update the reference — **note that Typekit is often the first line of the main CSS, `@import"https://use.typekit.net/<kit>.css"`, not an HTML `<link>`**:
   ```bash
   perl -0pi -e 's{\@import"https://use\.typekit\.net/<kit>\.css"}{\@import"/typekit/kit-local.css"}g' site/_astro/<main>.css
   ```

2. **Remove tracking**: Cloudflare beacon / GA / pixels — cut the `<script>` tag precisely.

3. **Public CDNs (Rive wasm@unpkg / third-party players)**: public CDNs can load fine cross-origin while served locally with internet access → can be left pointing online (fails offline; note it in NOTES). To go fully offline, mirror these too and rewrite the injection points.

4. **Vimeo/YouTube embeds**: iframes play online, unavailable offline → usually not above the fold, so just note it in NOTES.

## Serve + verify
```bash
cd "$WEB_CLONE_PROJECT/site"
python3 -m http.server 8124      # must serve from site/ as the web root, or root-relative paths (/_astro /models …) won't resolve
```
Then follow SKILL.md Step 5: 0 console errors in the browser + pixel comparison against the original site with `visual-diff.mjs`. For heavy WebGL sites, remember to **screenshot each section while scrolling** for comparison (a static full-page screenshot won't capture GL frames triggered by scrolling).

## Worked example: oryzo.ai (Lusion, L6)
- 135 same-origin assets (HTML+bundle+CSS + 25×`.buf` geometry/camera animation + 2×`.sog` Gaussian splats + sorting wasm + `.riv` + MSDF + fonts + 80+ images)
- Only rewrite needed: Typekit `@import` → locally self-hosted halyard + removed Cloudflare beacon
- Result: `scrollHeight` exactly matches, **0 console errors**, hero pixel diff **36/1.3M (5/5)**
- Left online: Vimeo gallery videos + unpkg Rive wasm (non-critical)
- Full record: `./website-clones/oryzo-clone/` (NOTES.md + TEARDOWN.md)
