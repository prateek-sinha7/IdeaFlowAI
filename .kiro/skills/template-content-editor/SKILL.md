---
name: template-content-editor
description: Convert any language content in an OpenDesign template to English. Translate all headings, paragraphs, body copy, button/link labels, list items, table cells, and alt text while preserving template structure, layout, CSS, design tokens, and scripts. Use when the user asks to "translate to English", "convert to English", or change template language to English.
---

# Template Content Editor Skill — Language to English Converter

Edit text inside an OpenDesign template by translating it from any language
to English. The design is already correct — your job is to translate what the
words say into English, not change how the page looks or is built.

Translation is **performed by you (the AI)** after reading and analyzing the
template. The user supplies the template with source-language content; you
supply the English translation while keeping layout and structure intact.

## Core invariant — text translation only

This skill translates **text and nothing else**. Everything that is not
human-readable copy must be byte-for-byte identical before and after your edit:
tags, nesting, element count, `class` / `id` / `style` / `data-*` attributes
(especially `data-od-id`), every `<style>` and `<script>` block, CSS tokens and
`:root` variables, image sources and `.ph-img` placeholders, layout, section
order, and responsive behavior. If a change would touch any of those, it is out
of scope — do not make it. When in doubt, leave it exactly as it was.

## Preserve length & layout

The layout was tuned to the *length* of the original copy — line breaks, the
number of lines a headline wraps to, how a stat fits its column, whether a
CTA stays on one line. Changing length silently breaks that tuning: text
reflows onto new lines, a one-line headline becomes two, a tight grid cell
overflows, and the deliberate visual rhythm and impact are diminished.

When translating to English, match the size of every slot:

- Keep the English translation within roughly ±10% of the original's
  **character count** for that slot. Short slots (headlines, buttons, labels)
  are the strictest — aim to match their character count as closely as
  possible; longer body paragraphs have slightly more slack.
- Preserve the same **structure and shape**: a one-line headline stays one
  line, a two-sentence paragraph stays two sentences, a stat value keeps the
  same footprint.
- Preserve punctuation density and any hard line breaks (`<br>`) exactly —
  they are layout, not prose.
- If the ideal English translation would run much longer or shorter than the
  original, rephrase it until it fits the original's footprint. Matching the
  length takes priority over perfect translation.

## Scope

OpenDesign templates live under `skills/opendesign/design-templates/<id>/`.
The files that carry visible content are:

- `example.html`         — the rendered preview / reference document
- `assets/template.html` — the seed (present on some templates)
- `references/*.md`      — paste-ready section skeletons (text only, no CSS)

Design tokens live in `skills/opendesign/design-systems/<id>/DESIGN.md`. This
skill does **not** touch design systems, craft rules, or CSS.

## Workflow

### Step 1 — Resolve the template

1. Identify which template the user means (a slug like `saas-landing`,
   `web-prototype`, `html-ppt-pitch-deck`). If ambiguous, list the closest
   matches from `design-templates/` and ask which one.
2. Confirm the folder exists: `skills/opendesign/design-templates/<id>/`.

### Step 2 — Read the template and identify source language

Read the target file(s) end-to-end **before** proposing any change. Never edit
HTML you have not read. Identify the current language of the content (Spanish,
French, German, Chinese, Japanese, Arabic, etc.).

### Step 3 — Analyze for translation

Build a written understanding of the template:

1. **Source language** — identify which language the content is currently in
2. **Section inventory** — walk the DOM top to bottom and list every content
   region in order (nav, hero, feature grid, stats, quote, pricing table,
   CTA, footer, slide 1..N, etc.), keyed by its `data-od-id` when present.
3. **Role of each slot** — note what each text slot contains: headline,
   paragraph, button label, stat, alt text, placeholder, etc.
4. **Length target per slot** — record each slot's current character count
   (especially important for headlines, buttons, and labels). This is the
   footprint the English translation must fit so the layout does not reflow.
5. **Tone and style** — capture the tone of the original copy (formal, casual,
   technical, marketing) so the English translation matches the intent

### Step 4 — Classify what is editable

Change ONLY text nodes and human-readable attribute values:

- Headings (`<h1>`–`<h6>`), paragraphs (`<p>`), spans, list items (`<li>`)
- Button and link labels, nav items, eyebrows, captions
- Table cell content (`<td>`, `<th>`)
- Visible text inside `<section>`, `<article>`, `<figure>` etc.
- Human-readable attributes: `alt`, `title`, `aria-label`, `placeholder`,
  and the document `<title>`

Do NOT change (treat as structure — leave byte-for-byte identical):

- Tag names, nesting, or the number of elements
- `class`, `id`, `style`, `data-*` attributes (especially `data-od-id`)
- Anything inside `<style>` or `<script>`, and CSS `:root` variables/tokens
- Image sources / placeholders (keep `.ph-img` placeholders; do not add
  external stock-photo URLs)
- Layout structure, section order, or responsive behavior

### Step 5 — Translate and match length

Translate each text slot into clear, idiomatic English:

- Translate the meaning and intent accurately
- **Match the character count of the original** (±10% for body text; aim for
  exact match on short slots). Rephrase until the English translation fits the
  footprint.
- Preserve the tone and voice of the original
- Keep sentence count and structure similar (multi-line slots stay
  multi-line)
- Preserve any `<br>` tags and punctuation density
- Do NOT add or remove content; translate what exists

### Step 6 — Make targeted edits

- Use `str_replace` with enough surrounding context to hit exactly the right
  occurrence. Do not rewrite whole files.
- Replace each text slot with its English translation
- Preserve inline markup inside the text (e.g. `<strong>`, `<br>`, entities).
- If the same string appears in multiple places and all should translate, use
  `replace_all=true`; if only one should change, add context to isolate it.

### Step 7 — Verify (translation-only gate)

Before finishing, prove the edit changed text only. This step is mandatory.

- Run a diff of the file (e.g. `git diff -- <path>`). Inspect every changed
  line: the ONLY differences allowed are text nodes and human-readable
  attribute values (`alt`, `title`, `aria-label`, `placeholder`, `<title>`).
- If the diff shows any change to a tag, attribute name, `class`/`id`/`style`/
  `data-*` value, `<style>`/`<script>` content, CSS variable, image `src`, or
  the number/order of elements, **revert that change** and redo the edit
  targeting only the text.
- Confirm element count and `data-od-id` set are unchanged, and the HTML still
  balances (no tags dropped or added).
- If the file is HTML, optionally open it to confirm it still renders. If you
  cannot verify, say so explicitly rather than assuming success.

## Hard rules

- Never introduce new design tokens, colors, fonts, or CSS. Translation only.
- Never delete or renumber `<section>` blocks or their `data-od-id`s.
- Never touch the `od:` frontmatter of a `SKILL.md` or any `DESIGN.md`.
- If the user's request actually needs structural or design changes (new
  sections, different layout, restyling), say so and stop — that is out of
  scope for this skill and belongs to the template/design-system authoring
  flow, not a translation.

## Output

After editing, summarize in one or two sentences: which template file(s) you
changed, which language was translated from, and which pieces of copy were
updated (headers, paragraphs, labels, etc.).
Do not paste the whole file back.

## Language Translation to English

This skill also supports converting template content from any language into
English while preserving all structural and design integrity.

### When to translate

Use this workflow when:
- The user provides a template with content in a non-English language (Spanish,
  French, German, Chinese, Japanese, Arabic, etc.)
- The user asks to "translate to English", "convert to English", or "change the
  language to English"
- A template has mixed-language content that needs unified English copy

### Translation workflow

1. **Identify the source language** — before reading the template, confirm which
   language the content is currently in. If mixed languages are present, note
   which sections are which.

2. **Read and analyze the template** — follow Steps 1–3 from the main workflow
   above. In your deep analysis (Step 3), include:
   - Current language(s) in the template
   - Tone and style of the original copy (formal, casual, technical, marketing)
   - Any culturally specific phrases or idioms that need localization context
   - Length of each slot in characters (to ensure English translation fits the
     layout without reflow)

3. **Translate with layout preservation** — this is critical:
   - Translate each text slot into clear, idiomatic English
   - **Match the character count of the original** (±10% for body text; aim for
     exact match on short slots like headlines, buttons, stats, and labels).
     English can run longer or shorter than other languages, so reword until the
     translated copy fits the footprint.
   - Preserve the tone, voice, and intent of the original
   - Keep sentence count and structure similar (multi-line slots stay
     multi-line)
   - Preserve any `<br>` tags and punctuation density
   - Do NOT add or remove content; translate what exists

4. **Preserve all non-text elements** — same rules as content-only editing:
   - Tags, nesting, element count unchanged
   - All `class`, `id`, `style`, `data-*` attributes identical
   - Image sources, `alt` text placeholders, and layout structure untouched
   - `<style>` and `<script>` blocks, CSS variables, and tokens remain byte-for-byte

5. **Make targeted edits** — use `str_replace` to translate each slot with
   surrounding context to ensure precision.

6. **Verify the translation** — run a diff to confirm:
   - Only text nodes and human-readable attributes (`alt`, `title`,
     `aria-label`, `placeholder`) changed
   - No tags, attributes names, classes, IDs, styles, or `data-*` values
     were modified
   - Element count and structure are identical
   - HTML still renders correctly

### Translation examples

**Spanish → English (landing page hero)**
```
Original (Spanish):
  <h1>Revoluciona tu flujo de trabajo</h1>
  <p>La herramienta más rápida para automatizar tareas repetitivas.</p>

Translated (English, matching character count):
  <h1>Revolutionize your workflow</h1>
  <p>The fastest tool to automate repetitive tasks.</p>
```

**French → English (CTA button)**
```
Original (French):
  <button>Commencer maintenant</button>  <!-- 19 chars -->

Translated (English, ~19 chars):
  <button>Get started now</button>       <!-- 16 chars, within ±10% -->
```

## Output

After editing, summarize in one or two sentences: which template file(s) you
changed and which pieces of copy were updated (header, paragraph, labels).
Do not paste the whole file back.

For translations, add one line stating the source language and that content
was translated to English while preserving layout and design.
