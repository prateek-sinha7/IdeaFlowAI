# HTML Prototype Rules

## Output Format

- Emit exactly one self-contained HTML file starting with `<!doctype html>`.
- The file must be renderable in an iframe with no external network requests.
- No markdown code fences anywhere in the output — output raw HTML only.
- No explanation text before `<!doctype html>` or after `</html>`.

## Structure

- Use semantic HTML5 elements: `<main>`, `<nav>`, `<header>`, `<footer>`, `<section>`, `<aside>`.
- Every top-level region must carry a `data-od-id="<slug>"` attribute.
- Multi-page prototypes use a single-page application pattern: one `<section data-page="...">` per route, shown/hidden via JavaScript hash routing.
- The hash router and a central state store must be present in the `<script>` block.

## Styling

- All styles must be in a single `<style>` block in `<head>`.
- Define all design tokens in a `:root` block at the top of the style block.
- Use only values from the `:root` token block — no invented inline colours, fonts, or spacing.
- No external CSS frameworks loaded from a CDN. No Tailwind CDN, no Bootstrap CDN.
- Inline `style` attributes are permitted only for dynamic values set by JavaScript.

## JavaScript

- No external JavaScript libraries. No React, Vue, jQuery, or any CDN-loaded script.
- All JavaScript must be in a single `<script>` block at the end of `<body>`.
- State lives in a single `store` object. No global variables outside the store.
- Every `onclick` or event handler must reference a function defined in the script block.

## Content and Copy

- All copy must be domain-specific and plausible — no "Lorem ipsum", "Metric A/B/C", "Feature 1/2/3", or "Placeholder".
- No emoji used as icons. Use text initials, inline SVG, or Unicode symbols sparingly.
- No default Tailwind indigo or violet colours (`#6366f1`, `#4f46e5`, `indigo-*`, `violet-*`).

## Colour Palette

- **Always derive colours from the ACTIVE DESIGN SYSTEM** injected in the system prompt.
  Map the DS tokens to `:root` variables (`--bg`, `--fg`, `--accent`, `--surface`, `--border`, `--muted`).
  Do NOT use hardcoded hex values outside `:root`.
- If no design system is present, fall back to: Background `#F8F9FA`, text `#111827`, accent navy `#1d4ed8`, surface `#FFFFFF`, border `#E5E7EB`, muted `#6B7280`.
- No multicolour gradients or decorative colour fills — keep the palette clean and purposeful.

## Navigation and Layout

- Sidebar: 220px wide, white background, right border.
- Navigation must remain functional after any content change.
- All pages in the SPA must share identical chrome (sidebar/topbar); only the active nav state differs.

## Hash Router — CRITICAL RULES

The `data-page` attribute is ONLY for `<section>` elements — NEVER add `data-page` to `<a>` or any
other element. Nav links use `href="#/{page-id}"` ONLY.

The router MUST use `section[data-page]` (not just `[data-page]`) to avoid matching nav links:

```javascript
function handleRouteChange() {
  const hash = window.location.hash.replace(/^#\/?/, '') || 'home';
  document.querySelectorAll('section[data-page]').forEach(s => s.classList.remove('is-active'));
  const page = document.querySelector('section[data-page="' + hash + '"]');
  if (page) page.classList.add('is-active');
  // Update nav active state separately using href
  document.querySelectorAll('[data-page-link]').forEach(a => a.classList.remove('active'));
  document.querySelectorAll('[data-page-link="' + hash + '"]').forEach(a => a.classList.add('active'));
}
window.addEventListener('hashchange', handleRouteChange);
window.addEventListener('load', handleRouteChange);
```

Nav link pattern — use `data-page-link` (NOT `data-page`) on anchor tags:
```html
<a href="#/dashboard" data-page-link="dashboard" class="nav-link">Dashboard</a>
```

Section pattern:
```html
<section data-page="dashboard" class="page">...</section>
```
