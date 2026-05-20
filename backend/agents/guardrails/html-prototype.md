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

- Background: #F8F9FA (page), #FFFFFF (cards and sidebar).
- Primary text: #111827. Secondary text: #6B7280.
- Accent: a single navy or brand colour, used sparingly (at most 3 uses per viewport).
- Border: #E5E7EB.
- Monochrome palette only — no multicolour gradients or decorative colour fills.

## Navigation and Layout

- Sidebar: 220px wide, white background, right border.
- Navigation must remain functional after any content change.
- All pages in the SPA must share identical chrome (sidebar/topbar); only the active nav state differs.
