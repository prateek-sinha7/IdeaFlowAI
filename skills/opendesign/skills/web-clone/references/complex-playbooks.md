# Complex Site Cloning Playbooks

For L4-L6 sites, the goal is to break "looks complex" down into an executable path.

## L4 Animated Brand Sites

1. `recon-site.mjs` captures three tiers of screenshots, sections, and video/canvas counts.
2. Record scroll library signals: GSAP / Lenis / ScrollTrigger / Locomotive.
3. Split the page into five categories: hero, scroll narrative, video masking, hover, and transitions.
4. Prioritize cloning the rhythm and visual grammar; micro-interactions can be approximated, but differences must be noted in `CLONE_REPORT.md`.
5. Use `visual-diff.mjs` to score screenshots of the hero and key scroll positions.

## L5 WebGL / Canvas / Three.js

1. First look for the real source code, source maps, or a public repo; only reverse-engineer the bundle if none is found.
2. `recon-site.mjs` records canvas dimensions, count, and framework signals.
3. `sourcemap-hunt.mjs` attempts to download the source map.
4. Break the technical pillars apart: rendering, shaders, post-processing, physics, interaction, audio, asset loading.
5. Don't blindly write complex shaders; build the minimal working scene first, then fill in materials, lighting, and post-processing incrementally.
6. Interaction must be verified with actual browser operation or screenshot/video evidence — code review alone is not enough.

## L6 SaaS / E-commerce / Login-based Business Systems

By default, only clone the presentation layer and the demoable flow — do not promise real accounts, payments, orders, or permissions.

1. For pages behind a login, confirm authorization and privacy boundaries first.
2. `network-capture.mjs` saves XHR/fetch responses as fixtures.
3. Split the interfaces into: content endpoints, search/filter, user state, and transaction/write operations.
4. Content endpoints can be stubbed with local JSON; transaction/write endpoints should only mock success/failure states.
5. Preserve empty states, loading states, error states, and insufficient-permission states — don't build the happy path only.
6. `audit-clone.mjs` scans for external links, leftover original branding, and tracking scripts.

## Multi-page / CMS / Enterprise Sites

1. First capture the sitemap, navigation, footer, and main templates.
2. Only clone representative templates: homepage, listing page, detail page, search/filter page, contact page.
3. Generate repeated content from a data file rather than hand-writing every page.
4. Do not clone the CMS backend; if editing capability is needed, substitute a local JSON/Markdown store.

## Success Criteria

- Complete evidence from the original site: screenshots, recon JSON, network manifest, asset manifest.
- The cloned site runs locally with zero console/page errors, or any remaining ones explained.
- `CLONE_REPORT.md` scores structure, visuals, interaction, responsiveness, and functional boundaries.
- `CLONE_AUDIT.md` shows no tracking scripts, no leftover original branding, and no unexplained leftover foreign-language text/external-link risk.
- Clearly document the boundaries for anything not achievable: real backends, proprietary APIs, copyrighted assets.
</content>
</invoke>
