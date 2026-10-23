# Template SKILL.md skeleton

Copy, then replace every `<…>`. Keep the frontmatter keys and the section headings:
`validate_template.py` checks them.

## Prototype

```markdown
---
name: <Display Name>
description: |
  <Two to four sentences: what the product is, who uses it, the screens it covers.
  End with "Use when the brief asks for …" listing the briefs it fits.>
triggers:
  - "<phrase a user would type>"
  - "<…5-10 phrases>"
od:
  mode: prototype
  shape: thin   # only for a frame plus one finished screen; omit for full templates
  platform: <desktop|mobile>
  scenario: <operations|product|engineering|design|marketing|finance|hr>
  preview:
    type: html
    entry: example.html
  design_system:
    requires: true
    sections: [color, typography, layout, components]
  craft:
    requires: [state-coverage, accessibility-baseline, laws-of-ux, form-validation]
  outputs:
    primary: prototype.html
  example_prompt: "<One sentence a user could launch with, naming the key screens.>"
  inputs:
    - "<What the user must tell the builder: who, what data, which rules, which approvals>"
---

# <Display Name>

## What this template is
<One paragraph: the product, the user, the job. Imported from <source> on <date>.>

## Chrome
<The frame around every screen: brand bar (say "fixed" only if it is position:fixed in the example), side nav (items, numbering, shortcuts), status strip, account menu.>

## How the example is organised
- One `<section class="pattern" data-pattern="<id>">` per screen, each preceded by
  `<!-- PATTERN <id> - <purpose> -->`. Only the first is visible.
- Nav items are `.nav-item[data-go="<id>"]`. `.is-active` marks the current one.
- Tokens live in `:root` (first `<style>`).
- <Only if example.html has them:> Shared classes are `<prefix>-N` (inline styles of the source, kept as classes).

## Role views
<Which roles the source has, which patterns belong to each, and what changes in
the chrome per role. The captured chrome is the <first role>'s: builders swap the
user name and position for the others.>

## Screen patterns
One row per `data-pattern` in example.html, no more and no fewer (the validator checks this).
| Pattern | Purpose | Key components |
|---|---|---|
| `<id>` | <what the user does here> | <the components it really contains (from validate --describe)> |

Not in the example: <source screens or states that were not carried over, and why>.

## Components
<The reusable pieces (buttons, chips, KPI tiles, tables, drawers) and their classes.>

## Theme
Use only these variables: `--bg --surface --fg --muted --border --accent --accent-on
--font-display --font-body --font-mono` <plus any semantic ones declared>.

## Interactions in the real product
<What each control does in the source prototype (navigation, filters, approvals,
dialogs). The static example does not run these; builders wire them with the
prototype runtime's data-goto / data-opens / data-toast hooks.>

Outside the prompt window: <patterns that start after char 120,000, or "none">.

## Hard rules
- <Brand and accessibility rules carried over from the source>
- Role colours and fonts come from the `:root` variables. One-off literals in the
  example stay as they are; new markup uses the variables.
- Keep every screen inside the frame. No new top-level layout.
```

## Deck

```markdown
---
name: <Display Name containing the tab keyword>
description: |
  <What the deck is for, its look, the slide types it contains. "Use when …">
triggers:
  - "<…5-10 phrases>"
od:
  mode: deck
  platform: desktop
  scenario: <marketing|creative|engineering|operations|product|finance>
  preview:
    type: html
    entry: example.html
  design_system:
    requires: <true to let the user pick a design system, false to keep the template's own look>
  outputs:
    primary: presentation.html
  example_prompt: "<One sentence brief.>"
  inputs:
    - "<Topic, audience, slide count, data to show>"
---

# <Display Name>

## What this template is
<Look, audience, slide count. Imported from <source> on <date>.>

## Workflow
1. Read the brief. Map each requested slide to one slide type below.
2. Copy `example.html`'s `<style>` blocks and the navigation `<script>` verbatim.
3. Write one `<section class="slide" data-label="…">` per slide, inside `div.deck`.
4. Keep every slide 1920x1080. No external images or scripts.

## Slide types
| Type | Example slide | Use for |
|---|---|---|
| <cover> | 1 | <title, presenter, date> |

## Theme
<Variables in :root and what each is for.>

## Original runtime features not carried over
<For a <deck-stage> source: the nav pill, R reset, number keys, speaker-notes UI.
Write "none" if nothing was lost.>

## Hard rules
- <Typography, colour, density rules of the source>
- Keep the source's colours and fonts; new slides use the :root variables.
- Exactly one `section.slide` per slide in the brief.
```
