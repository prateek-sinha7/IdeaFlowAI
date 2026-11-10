---
name: velocity-ui-ux
display_name: Velocity UI and UX craft
description: "Product UI and UX rules: hierarchy, alignment, density, forms and inline errors, warnings vs blocks, every state, keyboard, responsive. Use for any screen."
category: workflow
isBeta: false
tags:
- ui
- ux
- layout
- accessibility
- forms
---

# UI and UX craft

The look (colour, type, radius, spacing scale) comes from the selected design; the structure comes from
the template. This skill decides how a screen is ORGANISED and how it BEHAVES. A screen is finished when
a user who has never seen it can do the job without asking.

## 1. Hierarchy: one job per screen

- The screen title says the job ("Change flights", not "Details"). One primary action per view, visually
  first; secondary actions are quieter; destructive actions are separated and confirm.
- Order content in the order the user works: what they load → what they check → what they decide → what
  they get. A step bar (`nav` `data-variant="steps"`) shows where they are when the documents describe a
  sequence; a step that cannot be opened yet looks disabled and says why on focus/hover.
- Group with sections and cards, not with lines and colour. Every group has a heading.

## 2. Layout and alignment

- Use the template's regions and grid; never invent widths. Fill the screen: panels stretch to the
  container, tables span their panel, no floating islands in empty space.
- Align labels and values on a shared edge. Numbers (amounts, counts, times) are right-aligned in tables
  and use the same decimals in a column; currency code once in the header or beside each amount, never
  mixed.
- Read-only records use label-above-value facts, never disabled inputs.
- Side-by-side comparison (before/after, old/new) uses two aligned columns with identical row order; the
  rows that differ are marked (badge or `data-state`), not only coloured.

## 3. Operational density

Operational tools (airline, finance, ops) favour density: compact tables, small badges, short labels,
monospace for codes and generated text. Show identifiers exactly (order ids, offer ids, codes). Long
values wrap or truncate with the full value available (title/tooltip or a detail view) — never overflow.

## 4. Forms and validation

- Every input has a visible label; required fields are marked; formats are shown as hint text
  (`MMYY`, `+34`, `4–14 digits`), never only as placeholder.
- Validate on blur and on submit; the error sits next to the field, says what is wrong and how to fix it
  ("Expiry must be MMYY, e.g. 0828"), and moves focus to the first error on submit.
- Read-only computed values (fixed amounts, generated ids) look read-only and say where they come from.
- Defaults from the requirements are pre-filled; "fill test data" style helpers are clearly secondary.

## 5. Warnings vs blocks

- **Warning**: the user may continue. Amber callout near the affected area, one line, names the fact
  ("Offer expired on 6 Nov 2026 22:59 UTC"). Several warnings → a list, each its own line.
- **Block**: the user cannot continue. The action is disabled AND the reason is visible next to it (not
  only in a tooltip). A blocked state always says what would unblock it.
- **Error** (bad input file, parse failure): an error callout with the parser's message and the file name,
  plus a way to try again. Never a silent failure, never a console-only error.

## 6. Every state exists

Each screen and list has: empty (what to do first, with the action), loading (spinner/skeleton for >
300 ms work), populated, warning, blocked, error, success (toast or inline confirmation). A list that is
empty because of a filter says so and offers to clear the filter; it never shows "no items" under items.

## 7. Keyboard and accessibility

Every control reachable by Tab in reading order, visible focus (the design provides it — never remove
outlines), Enter/Space activate, Escape closes dialogs, focus returns to the opener. Icons that act have
an `aria-label`. Status changes use `role="status"`. Contrast comes from the design tokens — never put
text on a colour the design did not pair with it.

## 8. Responsive, light and dark

Desktop first for tools, but nothing breaks at 1024 px: columns stack, tables scroll inside their panel
(never the page sideways). Never write colours: both themes come from the design's tokens, and the header
theme toggle stays.

## 9. Copy

Plain, specific, sentence case. Buttons are verbs ("Generate request", "Load OrderViewRS"). Use the
domain's own terms from the documents (OrderViewRS, AddCol, PTC) exactly; explain a code once in plain
words where the documents ask for it.
