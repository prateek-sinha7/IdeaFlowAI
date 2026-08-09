# Underwriting Workbench — pre-emit checklist

Run this before finishing. **P0 must all pass** — a P0 failure means the deliverable is
broken, not merely imperfect. Reported failures should name the check.

## P0 — build fails or the artifact is unusable

- [ ] The file is written to **`prototype.html`** on disk (`write_file` on task 1,
      `edit_file` after). Nothing is streamed as chat text — a streamed response leaves
      the deliverable empty.
- [ ] Exactly one `<section data-page="…">` carries `class="page is-active"`.
- [ ] Section ids and `routes` keys are **1:1** — no section without a routes entry, no
      routes key without a section.
- [ ] `data-page` appears on `<section>` elements **only** — never on an `<a>`.
- [ ] Every nav anchor carries all three of `class="nav-item"`, `data-page-link="<id>"`,
      `href="#/<id>"`.
- [ ] Every `onclick="fn(...)"` calls a function defined in the `<script>` block.
- [ ] Zero external requests: no `http(s)://`, no `<link>`, no `<script src>`, no CDN,
      no web fonts. The file renders standalone in a sandboxed iframe.
- [ ] No console errors on load or when switching any page.
- [ ] One `<style>` block in `<head>`, one `<script>` block at the end of `<body>`.

## P1 — the template contract

- [ ] **No raw hex outside `:root`.** Every colour is a `var(--token)`. SVG icons use
      `stroke="currentColor"` / `fill="currentColor"` plus a colour class — `var()` is
      invalid inside a `stroke=`/`fill=` attribute.
- [ ] The six core roles (`--bg --fg --accent --surface --border --muted`) are bound to
      the active DESIGN.md; extended roles derive from them.
- [ ] `data-od-id` on every top-level region (chrome, each routed section, modals, toast).
- [ ] All state on the single `store` object; no globals beside it.
- [ ] Wizard steps, identification topics, forms sub-tabs and modals are `store` state —
      **not** extra routes.
- [ ] Shell is the 54px top bar, not a sidebar. Tables stay dense: 10.5px uppercase
      headers, 12.5–14px rows.
- [ ] Identifiers (policy / submission numbers, form codes, ZIPs) render in the mono font.

## P1 — behaviour that must actually work

- [ ] Every top-nav item switches pages; a reload on a deep link (e.g. `#/reports`)
      restores that page.
- [ ] Drill-down into a record works, and the breadcrumb returns.
- [ ] All wizard steps switch from the numbered tabs; completed steps show a check.
- [ ] The document step shows the draft watermark until finalized, then the finalized
      stamp; the save action stays disabled until then.
- [ ] Every modal opens, and closes on backdrop click, on Cancel, and on Escape.
- [ ] Creating a record leaves it **visible** — reset any active filter that would hide it.

## P2 — craft

- [ ] Copy is domain-specific throughout. No "Lorem ipsum", no "Metric A/B/C", no
      "Feature 1/2/3", no placeholder names left in.
- [ ] No emoji used as icons — inline SVG or a single letter in a rounded tile.
- [ ] Numbers are internally consistent: the pricing breakdown adds up, and the document
      shows the same figures as the summary panel.
- [ ] Field help says *why* a field matters, not just what it is.
- [ ] Read-only/pre-filled fields are visibly distinct from editable ones.

## Anti-slop spot-check

Would a practitioner in this domain recognise their own workflow here — the record
lifecycle, the document library, the draft-to-final gate? If any screen reads like a
generic CRUD table with the nouns swapped, it is not done.
