---
name: Magazine Editorial Deck
description: Generates a "digital magazine × e-ink" style horizontal-swipe web PPT (a single HTML file), featuring a WebGL fluid background, serif headings + sans-serif body text, chapter title cards, big-number stat pages, image grids, and more templates. Use when the user needs to make a share/talk/launch-event style web PPT, or mentions "magazine-style PPT", "horizontal swipe deck", "editorial magazine", or "e-ink presentation".
triggers:
  - "ppt"
  - "deck"
  - "slides"
  - "presentation"
  - "magazine"
  - "magazine style"
  - "magazine style PPT"
  - "horizontal swipe"
  - "horizontal swipe deck"
  - "editorial magazine"
  - "e-ink presentation"
  - "web PPT"
  - "product launch"
  - "share deck"
od:
  mode: deck
  scenario: marketing
  featured: 0.02
  default_for: deck
  upstream: "https://github.com/op7418/guizang-ppt-skill"
  preview:
    type: html
    entry: index.html
  design_system:
    requires: false
  example_prompt: "Help me make a magazine-style PPT — about 'The One-Person Company: an Organization Folded by AI', for a 25-minute talk, targeting designers and founders. First recommend a direction (Monocle / WIRED / Kinfolk / Domus / Lab) for me to pick."
---

# Magazine Web Ppt

## What this skill does

Generates a **single-file HTML** horizontal-swipe PPT with this visual tone:

- A **digital magazine + e-ink** hybrid style
- **WebGL fluid / contour / dispersion backgrounds** (visible on hero pages)
- **Serif headings (Noto Serif SC + Playfair Display) + sans-serif body (Noto Sans SC + Inter) + monospace metadata (IBM Plex Mono)**
- **Lucide line icons** (no emoji)
- **Horizontal left/right paging** (keyboard ← →, scroll wheel, touch swipe, bottom dots, ESC index)
- **Smooth theme interpolation**: colors and shader transition smoothly when swiping into a hero page

This skill's aesthetic isn't "business PPT," nor "consumer internet UI" — it looks like *Monocle* magazine after someone slapped code on it.

## When to use it

**Good fit**:
- In-person talks / internal industry talks / private sharing sessions
- AI product launches / demo days
- Talks with a strong personal style
- A "do it once, no need for a slide tool" web-based slide deck

**Not a good fit**:
- Heavy tabular data or overlapping charts (use a regular PPT)
- Training materials (information density too low)
- Needs multi-person collaborative editing (this is static HTML)

## Workflow

### Step 0 · Pick a direction (Direction · mandatory first step)

**Before asking the 6 clarifying questions, have the user pick one of the 5 magazine directions first**. Each direction bundles "theme color / recommended layout / chrome style / recommended slide count," so picking a direction answers half the clarifying questions already.

Open `references/styles.md`, **copy the whole section over** to show the user the 1-line summary of the 5 directions, then have them choose:

```
1. Monocle Editorial · international magazine style ✦ default
2. WIRED Tech · data + engineering
3. Kinfolk Slow · slow living / humanities
4. Domus Architectural · architecture / spatial feel
5. Lab / Reference · academic + technical manual
```

If the user says "I don't know, you pick" — **default to Monocle Editorial**, since it has the lowest failure rate. If the user mentions "AI / benchmark / tech launch" — recommend WIRED; "reading / private share / social feed" — recommend Kinfolk; "design / architecture / portfolio" — recommend Domus; "research / academic / methodology" — recommend Lab.

After picking a direction, create or update `project-notes.md` in the project directory, and write the direction + theme color + audience + duration clearly on the first line (see template at the end of `styles.md`). **Never switch directions mid-way** — switching halfway through wastes everything done so far.

### Step 1 · Requirements clarification (**mandatory before starting**)

**If the user has already given a complete outline + images**, you can skip straight to Step 2.

**If the user only gave a topic or a vague idea**, align on these 6 questions one by one before starting. Don't start writing slides based on guesses — once the structure is wrong, revisions later are very costly:

#### 6-question clarification checklist

> Question 5 was already answered during Step 0's direction pick (direction → theme color). In the 5 questions below, question 5 can be left blank.

| # | Question | Why it matters |
|---|------|-----------|
| 1 | **Who's the audience? What's the setting?** (internal industry talk / commercial launch / demo day / private sharing) | Determines tone and depth |
| 2 | **How long is the talk?** | 15 min ≈ 10 pages, 30 min ≈ 20 pages, 45 min ≈ 25-30 pages (see recommended ranges per direction in `styles.md`) |
| 3 | **Is there existing source material?** (documents / data / an old PPT / article links) | Build from source material if available, otherwise help construct it |
| 4 | **Are there images? Where are they?** | See "Image conventions" below |
| 5 | ~~**Which theme color set do you want?**~~ | ✓ Already decided by the direction in Step 0 |
| 6 | **Are there any hard constraints?** (must include XX data / must not mention YY) | Avoids rework |

#### Outline assistance (if the user has no outline)

Build the skeleton using a "narrative arc" template, then fill in content:

```
Hook             → 1 page   : Open with a contrast / question / hard number that makes people stop
Context          → 1-2 pages: Explain background / who you are / why this topic
Core             → 3-5 pages: Core content, interspersed with Layout 4/5/6/9/10
Shift            → 1 page   : Break expectations / introduce a new viewpoint
Takeaway         → 1-2 pages: A memorable line / a suspenseful question / a call to action
```

Align the narrative arc + page count plan + theme rhythm table (see `layouts.md`) **all three together** before moving to Step 2.

Save the outline as `project-notes.md` or `outline-v1.md` for easier iteration later.

#### Image conventions (tell the user)

Before starting, make clear to the user:

- **Folder location**: under `project/XXX/ppt/images/` (same level as `index.html`)
- **Naming convention**: `{page-number}-{semantic-name}.{ext}`, e.g. `01-cover.jpg` / `03-figma.jpg` / `05-dashboard.png`
  - Zero-pad page numbers for sorting
  - Use English for the semantic part, short, specific, and matching the content
- **Spec recommendations**:
  - Each image ≥ 1600px wide (avoid blurring on large screens)
  - JPG for photos/screenshots, PNG for transparent UI/charts
  - Keep total size under 10MB (affects paging smoothness)
- **How to replace**: overwriting with the **same filename** is safest (no need to change paths in the HTML); if a filename changes, remember to globally search `images/old-name` and replace it with the new name
- **What if there are no images**: align with the user — you can generate the structure first with placeholder color blocks and fill in images later, but note that layouts 4/5/10 and other image-text pages can't be visually verified without images

### Step 2 · Copy the template

Copy a fresh instance from `assets/template.html` to the target location (usually `project/XXX/ppt/index.html`), and create a sibling `images/` folder ready for images.

```bash
mkdir -p "project/XXX/ppt/images"
cp "<SKILL_ROOT>/assets/template.html" "project/XXX/ppt/index.html"
```

`template.html` is a **fully runnable** file — CSS, WebGL shader, paging JS, and font/icon CDNs are all preset — only `<main id="deck">` contains 3 example slides (cover, chapter title card, blank filler page).

#### 2.1 · Placeholders you must change (**easy to miss**)

Immediately after copying, change these placeholders, otherwise the browser tab will show awkward text like "[Required] Replace with PPT title":

| Location | Original | Change to |
|------|------|--------|
| `<title>` | `[Required] Replace with PPT title · Deck Title` | The actual deck title (e.g. `A New Way to Work · Luke Wroblewski`) |

Every time you copy template.html, the first thing to do is grep for "[Required]" to confirm everything is replaced.

#### 2.2 · Choose a theme color set (5 presets · no custom colors allowed)

This skill **only allows choosing from 5 carefully curated presets** and does not accept custom hex values from the user — a mismatched color combination instantly makes the deck ugly, and protecting the aesthetic matters more than giving free rein.

| # | Theme | Best for |
|---|------|--------|
| 1 | 🖋 Classic Ink | General / commercial launches / the default when unsure |
| 2 | 🌊 Indigo Porcelain | Tech / research / data / tech launch events |
| 3 | 🌿 Forest Ink | Nature / sustainability / culture / non-fiction |
| 4 | 🍂 Kraft Paper | Nostalgia / humanities / literature / independent magazines |
| 5 | 🌙 Dune | Art / design / creative / gallery |

**Steps**:
1. Recommend a set based on the content topic, or just ask the user to pick one
2. Open `references/themes.md`, find the corresponding theme's `:root` block
3. **Replace wholesale** the lines marked with a "theme color" comment inside the `:root{` block at the start of `assets/template.html` (the copied version) (`--ink` / `--ink-rgb` / `--paper` / `--paper-rgb` / `--paper-tint` / `--ink-tint`)
4. All other CSS uses `var(--...)`, no other changes needed

**Hard rules**:
- Use only one theme per deck, don't switch colors midway
- Don't accept arbitrary hex values from the user — politely decline and show the 5 sets for them to pick from
- Don't mix and match (e.g. taking ink from Classic Ink and paper from Dune) — it will clash badly

### Step 3 · Fill in content

#### 3.0 · Pre-flight check: class names must be defined in template.html (**most important**)

**This is the source of every generation problem**. The skeletons in layouts.md use many class names (`h-hero` / `h-xl` / `stat-card` / `pipeline` / `grid-2-7-5`, etc.) — if `assets/template.html`'s `<style>` block doesn't define the corresponding class, the browser will fall back to default styling — big headings become sans-serif, stat cards crowd together, the pipeline collapses into one line, images pile up at the bottom of the page.

**Before writing any slide code:**

1. **Read `assets/template.html` first** (at least through the end of the `<style>` block)
2. **Cross-check against the Pre-flight list in layouts.md** to confirm every class you plan to use exists in `<style>`
3. If a class is missing: **add it inside template.html's `<style>` block**, don't rewrite it inline in each slide
4. **template.html is the single source of truth for class names** — don't invent new classes; if you need something custom, use an inline `style="..."`

Commonly missed classes (must be confirmed to exist beforehand):
`h-hero` / `h-xl` / `h-sub` / `h-md` / `lead` / `kicker` / `meta-row` / `stat-card` / `stat-label` / `stat-nb` / `stat-unit` / `stat-note` / `pipeline-section` / `pipeline-label` / `pipeline` / `step` / `step-nb` / `step-title` / `step-desc` / `grid-2-7-5` / `grid-2-6-6` / `grid-2-8-4` / `grid-3-3` / `grid-6` / `grid-3` / `grid-4` / `frame` / `frame-img` / `img-cap` / `callout` / `callout-src` / `chrome` / `foot`

#### 3.0.5 · Plan the theme rhythm (**just as important as the class pre-flight**)

**Before picking layouts**, you must first list out each page's theme class (`hero dark` / `hero light` / `light` / `dark`) and write it into a document or draft to align on. See the "Theme rhythm planning" section at the top of `references/layouts.md` for detailed rules.

**Mandatory rules**:

- Every section per page must carry one of `light` / `dark` / `hero light` / `hero dark` — don't just write `hero`
- 3+ consecutive pages with the same theme = visual fatigue, not allowed
- 8+ pages must have ≥1 `hero dark` and ≥1 `hero light`
- The whole deck can't be all `light` body pages — there must be `dark` body pages to give it room to breathe
- Insert 1 hero page every 3-4 pages (cover / title card / question / big quote)

**Self-check after generating**: `grep 'class="slide' index.html` to list all themes, and manually confirm the rhythm makes sense before delivering.

#### 3.1 · Pick a layout

**Don't write a slide from scratch**. Open `references/layouts.md`, which has 10 ready-made layout skeletons, each a complete, paste-ready `<section>` code block:

| Layout | Purpose |
|---|---|
| 1. Opening cover | Page 1 |
| 2. Chapter title card | Start of each chapter |
| 3. Big-number stat page | Deliver a hard number |
| 4. Text-left, image-right (Quote + Image) | Identity contrast / story |
| 5. Image grid | Multi-image comparison / screenshot evidence |
| 6. Two-column pipeline | Workflow |
| 7. Suspenseful close / question page | End of chapter / closing |
| 8. Big quote page | Serif punchline / takeaway |
| 9. Side-by-side comparison (Before / After) | Old pattern vs new pattern |
| 10. Mixed image-text (Lead Image + Side Text) | Information-dense image-text page |

Pick the matching layout, paste it in, and just change the copy and image paths. **Be sure to finish the 3.0 pre-flight check first**.

#### 3.2 · Image aspect-ratio rules

Always use **standard aspect ratios**, never the source image's odd native ratio (e.g. `2592/1798`):

| Scenario | Recommended ratio |
|------|---------|
| Text-left/image-right main image | 16:10 or 4:3 + `max-height:56vh` |
| Image grid (multi-image comparison) | **Fixed `height:26vh`**, don't use aspect-ratio |
| Small image left + text right | 1:1 or 3:2 |
| Full-screen hero visual | 16:9 + `max-height:64vh` |
| Small inline image in mixed layout | 3:2 or 3:4 |

**Never use `align-self:end` on images** — it will slide down and get covered by the browser toolbar. Use a grid container + `align-items:start` (already preset in the template) to pin images to the top; if the left column needs to be bottom-aligned, use flex column + `justify-content:space-between`.

Component details (fonts, colors, grids, icons, callouts, stat-cards, etc.) are in `references/components.md`.

### Step 4 · Self-check against the checklist

Once generation is done, always open `references/checklist.md` and go through it item by item. It summarizes **every pitfall hit during real iteration** — P0-level issues (emoji, images breaking layout, heading wrapping, font role mixing) must all pass.

Pay special attention to these:

1. **Big headings must be serif** — if they render as sans-serif, 99% of the time the Step 3.0 pre-flight wasn't done and the `h-hero` class is missing from template.html
2. **In image grids, only use `height:Nvh`, never `aspect-ratio`** (it will break the layout)
3. **Images must not pile up at the bottom of the page** — don't use `align-self:end`; use grid + `align-items:start` (see Step 3.2)
4. **Images must use standard ratios only** (16:10 / 4:3 / 3:2 / 1:1 / 16:9), don't copy the source image's odd native ratio
5. **Large CJK headings ≤ 5 characters and `nowrap`** (avoid one character per line)
6. **Use Lucide, not emoji**
7. **Headings use serif, body uses sans-serif, metadata uses monospace**

### Step 5 · Local preview

Just open `index.html` directly in a browser. On macOS:

```bash
open "project/XXX/ppt/index.html"
```

No local server needed. Images use relative paths like `images/xxx.png`.

### Step 6 · Iteration

Revise based on user feedback — the template's CSS is highly parameterized, so 90% of adjustments are just changing inline styles (font size `font-size:Xvw` / height `height:Yvh` / spacing `gap:Zvh`).

---

## Resource file guide

```
magazine-web-ppt/
├── SKILL.md              ← you're reading this
├── assets/
│   ├── template.html     ← the fully runnable template (seed file)
│   └── example-slides.html ← a 9-page sample deck (for Examples preview)
└── references/
    ├── styles.md         ← 5 magazine directions (Monocle / WIRED / Kinfolk / Domus / Lab)
    ├── components.md     ← component manual (fonts, colors, grids, icons, callouts, stats, pipeline...)
    ├── layouts.md         ← 10 page layout skeletons (paste-ready)
    ├── themes.md         ← 5 theme color presets (choose only, no customizing)
    └── checklist.md      ← quality checklist (graded P0/P1/P2/P3)
```

**Recommended loading order**:
1. Read `SKILL.md` (this file) first to get the overall picture
2. **When picking a direction in Step 0, read `styles.md`** — each of the 5 directions bundles a theme color + recommended layout + chrome style
3. After finishing Step 1's requirements clarification, if the direction needs confirming, read `themes.md` for palette details
4. **Before starting, Read the `<style>` block of `assets/template.html`** — this is the single source of truth for class names; a missing class breaks the whole page's styling
5. Read `layouts.md` to pick a layout (Pre-flight class checklist and theme rhythm planning are at the top)
6. When fine-tuning details, read `components.md` to look up components
7. After generating, read `checklist.md` to self-check (the P0-0 rule at the top enforces the pre-flight check)

## Core design principles (philosophy)

> These principles are distilled from 5 iterations on a "one-person company" share-deck talk. Violate any of them and the visual feel falls apart.

1. **Restraint over showing off** — the WebGL background only shows through on hero pages; it's barely visible on regular pages
2. **Structure over decoration** — no shadows, no floating cards, no padding boxes; all hierarchy comes from **large type + font contrast + grid whitespace**
3. **Content hierarchy is defined jointly by font size and typeface** — largest serif = main title, medium serif = subtitle, large sans-serif = lead, small sans-serif = body, monospace = metadata
4. **Images are first-class citizens** — images are only cropped at the bottom, keeping the top and sides intact; grids use fixed `height:Nvh`, never stretch with `aspect-ratio`
5. **Rhythm comes from hero pages** — alternating hero and non-hero pages keeps the eyes from getting tired
6. **Terminology stays consistent** — "Skills" stays "Skills," don't mix translated and untranslated terms

## Reference works

This skill's visual tone draws on:

- Guī Cáng's "The One-Person Company: an Organization Folded by AI" talk (2026-04-22, 27 pages)
- The layout of *Monocle* magazine
- The demo from YC president Garry Tan's "Thin Harness, Fat Skills" blog post

Treat these as style anchor points.
