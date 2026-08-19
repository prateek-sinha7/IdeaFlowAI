# Quality Checklist

This checklist comes from the real iteration process of a "solo company" PPT deck. Every item was distilled after hitting the problem firsthand, ordered by importance.

Read through once before generating the PPT; after generating, self-check item by item.

---

## 🔴 P0 · Mistakes you must never make

### 0. Class-name validation you must pass before generating (most important)

**Symptom**: Pasting the layouts.md skeleton straight into a new HTML file causes all styling to be lost — big headlines turn into sans-serif, big-number stat cards shrink to body-text size, multi-page pipelines squash into a single blob, images pile up at the bottom of the browser.

**Root cause**: If `template.html`'s `<style>` block doesn't define these classes, the browser falls back to default styling.

**How to handle it**:
- **Before generating the PPT, you must `Read` `assets/template.html`** and confirm every class used in layouts.md is already defined
- Most commonly missing classes: `h-hero / h-xl / h-sub / h-md / lead / meta-row / stat-card / stat-label / stat-nb / stat-unit / stat-note / pipeline-section / pipeline-label / pipeline / step / step-nb / step-title / step-desc / grid-2-7-5 / grid-2-6-6 / grid-2-8-4 / grid-3-3 / frame / img-cap / callout-src`
- If a class really is missing, **add it inside `template.html`'s `<style>` block** — don't rewrite it inline on every page
- After generating, open it in the browser. If the big headline looks sans-serif or pipeline steps are crammed onto one line, it's almost always this issue

### 1. Don't use emoji as icons

**Symptom**: Using emoji (🎯 💡 ✅) in a Chinese-magazine-style layout instantly breaks the tone.

**How to handle it**: Use the Lucide icon library, loaded via CDN:

```html
<script src="https://unpkg.com/lucide@latest/dist/umd/lucide.min.js"></script>
...
<i data-lucide="target" class="ico-md"></i>
...
<script>lucide.createIcons();</script>
```

Commonly used icon names: `target / palette / search-check / compass / share-2 / crown / check-circle / x-circle / plus / arrow-right / grid-2x2 / network`

### 2. Images may only be cropped at the bottom — never crop the left, right, or top

**Symptom**: Using `aspect-ratio` to size images causes grids to stack or crop out key image content (e.g. the title bar at the top of a screenshot) when the parent container is too small.

**How to handle it**: Give the image container a **fixed height + overflow hidden**, and let the image use `object-fit:cover + object-position:top`:

```html
<figure class="frame-img" style="height:26vh">
  <img src="screenshot.png">
</figure>
```

The CSS already presets `.frame-img img` with `object-position:top`, so only the bottom gets cropped.

**Never write it like this** (it will blow out the container inside a grid):

```html
<!-- Bad example -->
<figure class="frame-img" style="aspect-ratio: 16/9">...</figure>
```

**Exception**: a single hero visual (not inside a grid) can use `aspect-ratio + max-height`, since the parent container provides a fallback.

### 2b. A light page with a dark WebGL background = a grayed-out mess (theme switch didn't take effect)

**Symptom**: every light-theme page's background looks like it has a gray film over it — even the light hero looks gray.

**Root cause**: JS switches the opacity of two canvases based on the slide's theme. If the deck opens on hero dark and nothing ever switches the background to light, `body` never gets the `light-bg` class, and `canvas#bg-dark` stays on top forever.

**How to handle it**:
- The template's `go()` function now infers the theme from `classList` (`light` / `dark`), so **every slide must explicitly carry a `light` or `dark` class**. Don't skip it, and don't invent other custom theme names
- Hero pages use `hero light` / `hero dark`; body pages use `light` / `dark`. Writing just `hero` with no theme color is broken
- A deck must contain at least one **non-hero light page**, to guarantee `body` gets a chance to receive `light-bg`

### 2b-2. The whole deck is all light, with no rhythm

**Symptom**: aside from the `hero dark` cover, every other page defaults to `light` — visually flat, no breathing room, a sea of white.

**Root cause**: the layouts.md skeleton defaults everything to `light`; if you just paste the skeleton without adjusting the theme, the whole deck ends up light.

**How to handle it**:
- **Draw a "theme rhythm table" before generating**: write down which of `hero dark` / `hero light` / `light` / `dark` each page uses, align it, then write the code
- **Hard rule**: 3+ consecutive pages of the same theme = not allowed; decks with 8+ pages must have ≥1 `hero dark` + ≥1 `hero light`; you can't have all `light` body pages — there must be at least one `dark` body page
- **Choose theme by layout** (see "Theme Rhythm Planning" at the top of layouts.md for details):
  - Text-left/image-right (Layout 4), big quote (Layout 8), mixed text-image (Layout 10) → **alternate `light` / `dark`**
  - Big-number stat cards, image grids, pipelines, comparison pages → `light` (screenshots/numbers/flows need a light background)
  - Cover, problem statement pages → `hero dark`
  - Section dividers → alternate `hero dark` and `hero light`
- **Self-check after generating**: `grep 'class="slide' index.html`, visually confirm the rhythm alternates

### 2c. Don't say the same thing in chrome and kicker

**Symptom**: the top-left `.chrome` says "Design First · Kickoff", and on the same page `.kicker` says "Phase 01 · Design Stage" — a synonymous restatement of the same idea, which reeks of AI-generated copy.

**How to handle it**:
- **chrome = magazine page header / nav tab**: can stay the same across multiple pages (e.g. "Act II · Workflow", "Data · Result", "lukew.com · 2026.04")
- **kicker = a lead-in line unique to this page**: short, has a hook, functions as a "mini-prefix" to the big headline (e.g. "BUT", "One person, did what.", "The Question")
- One describes the section, the other describes this specific page — they should never restate each other

### 3. Headline font size must not exceed screen width / character count

**Symptom**: setting the Chinese headline font size too large (e.g. 13vw) results in only 1 character fitting per line, forcing ugly line breaks.

**How to handle it**:
- `h-hero` (largest): 10vw, **and the title must be ≤ 5 characters**
- `h-xl` (second largest): 6vw-7vw
- For long titles, manually break lines with `<br>` — don't rely on automatic wrapping
- Add `white-space:nowrap` when needed

**Example**: "I'm not a programmer." (short) uses `h-xl` at 7.2vw + nowrap, fitting on one line.

### 4. Font role split: serif for headlines, sans-serif for body text

**How to handle it**:
- Big headlines, key quotes, big-number stats → **serif fonts** (Noto Serif SC + Playfair Display + Source Serif)
- Body text, descriptions, pipeline step names → **sans-serif fonts** (Noto Sans SC + Inter)
- Metadata, code, labels → **monospace fonts** (IBM Plex Mono + JetBrains Mono)

All fonts are loaded via Google Fonts CDN and already preset in the template.

### 4b. Don't use `align-self:end` to pin images to the bottom

**Symptom**: in a text-left/image-right layout, to align the right-column image with the bottom of the left-column callout, someone adds `align-self:end` to the `<figure>`. Result:
- If the parent container isn't a grid (e.g. the class name isn't defined), `align-self` has no effect at all, and the image falls to the bottom of the document flow, getting covered by the browser's bottom bar
- Even inside a grid, the image sticks to the bottom of its cell, and on short screens it still gets covered by the `.foot` bar and the `#nav` dots

**How to handle it**:
- Mixed text-image layouts **must use `.frame.grid-2-7-5`** (or `.grid-2-6-6`/`.grid-2-8-4`)
- The right-column `<figure class="frame-img">` should use a **standard ratio, 16/10 or 4/3 + max-height:56vh**, and align naturally to the top
- To make the left-column callout look "pinned to the bottom," give the **left column** flex column + `justify-content:space-between` — don't touch the right column

### 4c. Don't use the original image's odd aspect ratio

**Symptom**: an `aspect-ratio: 2592/1798` copied straight from the source image creates odd blank space or overflow on different screens.

**How to handle it**: no matter what ratio the original image is, the placeholder should always use a standard ratio: **16/10 / 4/3 / 3/2 / 1/1 / 16/9**. The image auto-fits with `object-fit:cover + object-position:top` — the top is never cropped, and a slight bottom crop is harmless.

### 5. Don't add heavy borders / shadows to images

**Symptom**: adding a strong shadow or black border for a "premium" look instantly turns it into a corporate PowerPoint.

**How to handle it**: at most 1-4px of subtle rounding + **very faint background noise** (already in the template). Don't add `box-shadow`, don't add `border` (unless it's a 1px very-light gray).

---

## 🟡 P1 · Layout rhythm

### 6. Hero pages and non-hero pages should alternate

**Recommended rhythm** (25-30 pages):
```
Hero Cover → Act Divider (hero) → 3-4 pages non-hero → Act Divider (hero)
→ 4-5 pages non-hero → Hero Question → ... → Hero Close
```

2+ consecutive hero pages will tire the audience; 4+ consecutive non-hero pages will kill the rhythm.

### 7. Big-stat pages and dense pages should alternate

Big-stat pages (big numbers / hero questions) and dense pages (pipeline / image grid) should alternate so the audience's eyes don't get tired.

### 8. Keep terminology consistent for the same concept

**Symptom**: sometimes writing "Skills", sometimes "Capabilities", sometimes "thin carrier, thick skills" — inconsistent throughout the deck.

**How to handle it**:
- Prefer **English words** for terminology (Skills / Harness / Pipeline / Workflow) — these are familiar terms within the field
- **Don't force a translation** — a forced translation reads awkwardly
- Use exactly one spelling/form for the same term throughout the whole deck

### 9. Keep the bottom chrome's page numbers consistent

Use the format `XX / total pages` (e.g. `05 / 27`). **Don't add a dynamic page number in the top-right corner** (it would duplicate `.chrome`).

---

## 🟢 P2 · Visual polish

### 10. WebGL background overlay opacity

**Dark hero**: overlay 12-15% (WebGL clearly shows through)
**Light hero**: overlay 16-20% (WebGL faintly visible, doesn't compete with text)
**Regular light/dark pages**: overlay 92-95% (almost opaque)

If a page has very little text (hero question), the overlay can be thinner; if the body text is dense, the overlay must be thicker to ensure readability.

### 11. Light hero shaders must not have a strong central focal point

**Symptom**: Spiral Vortex or radial ripple effects are too eye-catching on a light theme, looking like a Windows 98 screensaver.

**How to handle it**: for light heroes, use FBM-domain-warp-driven centerless flow, keep the base color silver/paper-toned (close to #F0F0F0 / #FBF8F3), and keep rainbow color shift subtle (below 0.05).

### 12. Dark hero can carry more visual impact

Dark heroes can use shaders with a central structure, like Holographic Dispersion (titanium color dispersion), since a black background can hold more visual information.

### 13. Alignment for text-left/image-right layouts

- The left-column text group uses `justify-content:space-between`: heading pinned to top, callout box pinned to bottom
- The right-column image uses `align-self:end`: aligned with the left column's bottom element
- The grid overall uses `align-items:start` (not `center` / `end`)

### 14. Subtle rounded corners on images

All `.frame-img` and `.frame-img img` get `border-radius:4px` — visually "soft" but not mushy. **Don't exceed 8px**, or it starts to look like a consumer-app UI.

---

## 🔵 P3 · Operational details

### 15. Use relative paths for images

Put images in the `images/` folder and reference them in HTML with relative paths like `images/xxx.png` — don't use absolute paths.

### 16. Page numbers are hardcoded inside `.chrome`

JS dynamically computes the total page count and expands the bottom paging dots, but the `XX / N` inside `.chrome` is hardcoded. When adding or removing pages, update N by hand.

### 17. Keep the paging navigation intact

The template supports by default: ← → / scroll wheel / touch swipe / bottom dots / Home·End. Don't remove the navigation logic from the JS.

### 18. Don't hardcode `height:100vh` — use `min-height:80vh`

`100vh` makes content fit exactly to the screen, but the browser's toolbar and tab bar eat into the available height, causing content to overflow. `min-height:80vh + align-content:center` is more reliable.

---

## 🧪 Final self-check list

After generating the PPT, go through this checklist item by item (check each one off):

```
Pre-check (before generating)
  □ Read through template.html's <style> and confirmed all needed classes exist
  □ Decided which Layout (1-10) to use for each page
  □ Drew out a "theme rhythm table": each page explicitly marked hero dark / hero light / light / dark
  □ The rhythm table satisfies the hard rules: no 3 consecutive pages of the same theme / has ≥1 hero dark + ≥1 hero light (for 8+ pages) / has at least 1 dark body page
  □ `<title>` has been changed to the actual deck title (grep "[required]" should return no results)

Content
  □ Each act's page count ratio is reasonable (not front-heavy or back-heavy)
  □ No emoji used as icons
  □ Terminology like Skills / Harness is used consistently
  □ Each page's kicker + headline + body form a clear three-tier information hierarchy

Layout
  □ No headline wraps to 1 character per line
  □ Image grids use height:Nvh rather than aspect-ratio
  □ Images are only cropped at the bottom — top, left, and right stay intact
  □ Serif/sans-serif font role split follows the template
  □ Clear separation between multiple pipeline groups

Visual
  □ Hero pages and non-hero pages alternate
  □ WebGL background is visible on hero pages
  □ Images have a subtle rounded corner
  □ No heavy shadows or borders

Interaction
  □ ← → paging works correctly
  □ Bottom dot count matches total page count
  □ Page number in chrome matches the actual page number
  □ ESC key triggers the index view (if kept)
```

Only once everything is checked off is the PPT considered done.
