# Page Layout Library (Layouts)

This document collects the 10 most commonly used page layout skeletons. Each is a complete, paste-ready `<section class="slide ...">...</section>` code block — just swap in your own copy/images.

---

## ⚠️ Read Before Generating (Pre-flight)

### A. Class names must come from template.html

Every class used in layouts.md (`h-hero` / `h-xl` / `h-sub` / `h-md` / `lead` / `meta-row` / `stat-card` / `stat-label` / `stat-nb` / `stat-unit` / `stat-note` / `pipeline-section` / `pipeline-label` / `pipeline` / `step` / `step-nb` / `step-title` / `step-desc` / `grid-2-7-5` / `grid-2-6-6` / `grid-2-8-4` / `grid-3-3` / `grid-6` / `grid-3` / `grid-4` / `frame` / `frame-img` / `img-cap` / `callout` / `callout-src` / `kicker`) is predefined in the `<style>` block of `assets/template.html`.

**Do not invent new class names**. If you need custom styling, write it inline via `style="..."`. If unsure whether a class exists before generating, grep template.html to confirm.

### B. Image aspect-ratio rules (very important)

**Always use a standard ratio** — never the source image's raw ratio like `aspect-ratio: 2592/1798`:

| Scenario | Recommended ratio | Usage |
|------|---------|------|
| Left text / right image, main image | 16:10 or 4:3 | `aspect-ratio:16/10; max-height:54vh` |
| Image grid (multi-image comparison) | Uniform | **Fixed `height:26vh`, no aspect-ratio** |
| Small image left + text right | 1:1 or 3:2 | `aspect-ratio:1/1; max-width:40vw` |
| Full-screen hero visual | 16:9 | `aspect-ratio:16/9; max-height:64vh` |
| Small inline illustration | 3:2 | `aspect-ratio:3/2; max-width:30vw` |

Images must be wrapped in `<figure class="frame-img">`; the `<img>` inside automatically gets `object-fit:cover + object-position:top center`, cropping only the bottom, never the top/left/right.

### C. Image positioning rules (avoid images piling up at the very bottom, hidden behind the browser toolbar)

**Wrong approach** (already bitten by this, don't repeat):
- Using `align-self:end` outside a flex/grid container: `align-self` does nothing outside flex/grid, and the image drops to the end of the document flow
- Using `position:absolute + bottom:0` to "pin" the image to the bottom: it gets covered by the bottom `.foot` bar and the `#nav` dots
- Setting only `height:Nvh` on a single image without `max-height`: it overflows the viewport on short screens

**Correct approach**:
- Text-and-image layouts **must use the grid structure of `.frame.grid-2-7-5`** (or `.grid-2-6-6` / `.grid-2-8-4`)
- The grid container defaults to `align-items:start` (already set in the template), so the image naturally sits at the top of its cell
- If you need "image bottom-aligned with a callout in the left column": **make the left column a flex column with `justify-content:space-between`** (so the callout naturally sits at the bottom of the left column), **the right column's figure should just keep `align-items:start`** — do not add `align-self:end`
- It's recommended to add inline `style="padding-top:6vh"` to all grid parent containers, to give the heading area breathing room

### D. Theme color and theme pacing

- Pick the theme color from one of the 5 presets in `references/themes.md` — custom hex values are not allowed
- Theme pacing (which of light / dark / hero light / hero dark to use per page) has hard rules in the "Theme Pacing Plan" section below — read it before generating
- Both decisions must be made before picking a layout, to avoid rework

---

## 0. Base structure (identical across all slides)

```html
<section class="slide [light|dark|hero light|hero dark]">
  <div class="chrome">
    <div>Context label · Sub-label</div>
    <div>ACT · Page / Total pages</div>
  </div>
  <!-- Main content -->
  <div class="foot">
    <div>Page description · Page Description</div>
    <div>— · —</div>
  </div>
</section>
```

- Non-hero pages should carry `light` or `dark`; hero pages carry `hero light` or `hero dark` (this participates in WebGL theme interpolation)
- `chrome` and `foot` are optional but recommended — they're the four corner metadata elements
- **Hero pages are used for section covers/opens/closes/transitions**, non-hero pages are used for body content

### ⚠️ Don't put the same line in both chrome and kicker

This is the most common content-duplication mistake. The two operate on entirely different semantic dimensions:

| Position | Role | Content nature | Example |
|------|------|---------|------|
| `.chrome` top-left | **Magazine masthead / nav metadata** | A stable "section name" or "chapter category" — can repeat across pages | "Act II · Workflow" / "Data · Result" / "lukew.com · 2026.04" |
| `.chrome` top-right | **Page number + act number** | Fixed format | "Act II · 15 / 25" |
| `.kicker` | **This page's one-of-a-kind hook line** | The "small prefix" above the big headline, like a line above a magazine's main title — should differ on every page | "BUT" / "One person did this." / "Phase 01 · Design Phase" |

**Bad example** (already bitten by this): chrome says "Design First · Design First", kicker says "Phase 01 · Design Phase" — meaning duplicated, reads as obviously AI-generated at a glance.

**Correct approach**: chrome is the **section label** (stable, reusable across pages), kicker is **this page's hook** (short, dramatic) — the two complement each other, never restate each other.

### ⚠️ Theme pacing plan (must read · must do before generating)

**Core mechanism**: every `<section>` must carry one of `light` / `dark` / `hero light` / `hero dark`. JS infers the theme from the class and decides whether to add `light-bg` to body, which switches which of the two dark/light WebGL canvases is in front. No theme, or a custom class name = fallback error.

#### Default theme by layout

| Layout | Default theme | Reason |
|---|---|---|
| 1. Opening cover | `hero dark` | Ceremonial opening; dark background hits harder |
| 2. Act divider | `hero dark` and `hero light` **must alternate** | Breathing rhythm |
| 3. Big-number poster (data) | `light` | Numbers need a paper-white background; can sprinkle in `dark` for a run of pages |
| 4. Text-left / image-right | **Alternate `light` / `dark`** | Main body-copy pacing |
| 5. Image grid | `light` | Screenshots need a bright background |
| 6. Pipeline | `light` | Flow diagrams need clarity |
| 7. Question page | `hero dark` | Default is strong visual impact |
| 8. Big quote | **`dark` preferred**, occasional `light` | The dark background gives the quote ceremony |
| 9. Comparison page | `light` | Two columns need clarity |
| 10. Text-and-image mix | **Alternate `light` / `dark`** | Pacing |

#### Hard pacing rules (grep-check after generating)

- ❌ **Forbidden**: 3+ consecutive pages with the same theme (light-stacking or dark-stacking both count)
- ❌ **Forbidden**: a deck of 8+ pages with no `hero dark` and no `hero light`
- ❌ **Forbidden**: a whole deck of only `light` body pages with no `dark` body page at all — feels flat, no breathing room
- ✅ **Recommended**: insert 1 hero page (cover/divider/question/quote) every 3-4 pages

#### 8-page pacing template (directly reusable)

| Page | Theme | Layout | Note |
|---|---|---|---|
| 1 | `hero dark` | Cover | Opening |
| 2 | `light` | Big-number poster | Throw out the data |
| 3 | `dark` | Text-left / image-right | Contrast/story |
| 4 | `light` | Pipeline | Process |
| 5 | `hero light` | Act divider | Breathing room |
| 6 | `dark` | Text-left / image-right or big quote | |
| 7 | `hero dark` | Question page | Suspenseful close |
| 8 | `light` | Big quote / ending | Wrap-up |

**Sketch this table first before writing any slides**. Skipping the plan and pasting skeletons directly = everything ends up `light`.

---

## Layout 1: Opening Cover (Hero Cover)

```html
<section class="slide hero dark">
  <div class="chrome">
    <div>A Talk · 2026.04.22</div>
    <div>Vol.01</div>
  </div>
  <div class="frame" style="display:grid; gap:4vh; align-content:center; min-height:80vh">
    <div class="kicker">Private Gathering · Li Jigang</div>
    <h1 class="h-hero">One-Person Company</h1>
    <h2 class="h-sub">Organizations Folded by AI</h2>
    <p class="lead" style="max-width:60vw">
      An AI creator — in 64 days, wrote 110,000 lines of code and shipped continuously across 9 platforms, all without disrupting daily life.
    </p>
    <div class="meta-row">
      <span>Guizang</span><span>·</span><span>Independent Creator / Author of CodePilot</span>
    </div>
  </div>
  <div class="foot">
    <div>A talk on AI · Organizations · Individuals</div>
    <div>— 2026 —</div>
  </div>
</section>
```

**Key points**:
- Use `hero dark` so the WebGL background shows through most of the page
- `h-hero` is the largest font size (10vw), used here as the main headline
- Use `min-height:80vh + align-content:center` to vertically center the whole content block
- No need to put a page number in `.chrome` — the cover stands on its own

---

## Layout 2: Act Divider

```html
<section class="slide hero light">
  <div class="chrome">
    <div>Act I · Hard Data</div>
    <div>Act I · 01 / 25</div>
  </div>
  <div class="frame" style="display:grid; gap:6vh; align-content:center; min-height:80vh">
    <div class="kicker">Act I</div>
    <h1 class="h-hero" style="font-size:8.5vw">Hard Data</h1>
    <p class="lead" style="max-width:55vw">
      Look at the numbers first, then talk method.
    </p>
  </div>
  <div class="foot">
    <div>Act I Prologue</div>
    <div>— · —</div>
  </div>
</section>
```

**Key points**:
- Keep it minimal — just kicker + big headline + one line of copy
- Alternate `hero light` / `hero dark` between act dividers to build rhythm
- `h-hero` font size can be tuned from 10vw down to 8.5vw to fit shorter/longer titles

---

## Layout 3: Big-Number Poster (Big Numbers Grid)

```html
<section class="slide light">
  <div class="chrome">
    <div>The Past 64 Days · Dev Chapter</div>
    <div>Act I / Dev · 02 / 25</div>
  </div>
  <div class="frame" style="padding-top:6vh">
    <div class="kicker">What one person built.</div>
    <h2 class="h-xl">The Past 64 Days</h2>
    <p class="lead" style="margin-bottom:5vh">From zero to open-source CodePilot.</p>

    <div class="grid-6" style="margin-top:6vh">
      <div class="stat-card">
        <div class="stat-label">Duration</div>
        <div class="stat-nb">64 <span class="stat-unit">days</span></div>
        <div class="stat-note">From zero to now</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Lines of Code</div>
        <div class="stat-nb">110K+</div>
        <div class="stat-note">Written line by line, past 110K</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">GitHub Stars</div>
        <div class="stat-nb">5,166</div>
        <div class="stat-note">One open-source repo</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Downloads</div>
        <div class="stat-nb">41K+</div>
        <div class="stat-note">Installed on tens of thousands of machines</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">AI Providers</div>
        <div class="stat-nb">19</div>
        <div class="stat-note">Cross-platform integrations</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Commits</div>
        <div class="stat-nb">608+</div>
        <div class="stat-note">No collaborators</div>
      </div>
    </div>
  </div>
  <div class="foot">
    <div>Project · CodePilot | github.com/codepilot</div>
    <div>Act I · Dev Numbers</div>
  </div>
</section>
```

**Key points**:
- A 3×2 or 4×2 grid is the most stable choice (see `.grid-6`)
- Each `stat-card` has a fixed structure: label (small English text) → nb (large number) → note (annotation)
- Numbers should be 2-3 characters long (longer overflows) — use K / M abbreviations
- Leave at least 5vh of top buffer so the heading area grabs attention first

---

## Layout 4: Text-Left / Image-Right (Quote + Image)

```html
<section class="slide light">
  <div class="chrome">
    <div>Identity Contrast · The Twist</div>
    <div>03 / 25</div>
  </div>
  <div class="frame grid-2-7-5" style="padding-top:6vh">
    <!-- Left column: heading + body + callout; flex column keeps the callout pinned to the bottom -->
    <div style="display:flex; flex-direction:column; justify-content:space-between; gap:3vh">
      <div>
        <div class="kicker">BUT</div>
        <h2 class="h-xl" style="white-space:nowrap; font-size:7.2vw">
          I'm not a programmer.
        </h2>
        <p class="lead" style="margin-top:3vh">
          Never wrote a line of code again after graduating college. The past ten years were spent on UI design and AI visual effects.
        </p>
      </div>
      <div class="callout">
        "Three years ago, this thing<br>
        would have needed a ten-person team, one year."
        <div class="callout-src">— an observer's judgment</div>
      </div>
    </div>
    <!-- Right column: image at a standard 16/10 ratio + max-height, no align-self:end -->
    <figure class="frame-img" style="aspect-ratio:16/10; max-height:56vh">
      <img src="images/codepilot.png" alt="CodePilot product screenshot">
      <figcaption class="img-cap">CodePilot · Product Screenshot</figcaption>
    </figure>
  </div>
  <div class="foot">
    <div>Page 03 · I'm Not a Programmer</div>
    <div>— · —</div>
  </div>
</section>
```

**Key points**:
- Use `grid-2-7-5` (7 parts left, 5 parts right); `align-items:start` is already preset in the template
- **Left column**: use flex column + `justify-content:space-between` — heading pinned to top, callout naturally sits at the bottom
- **Right-column image**: **do not add `align-self:end`**. It will slide the image to the bottom of the cell, where it gets covered by the browser toolbar on short screens
- Images must use a **standard ratio like 16/10 or 4/3 + `max-height:56vh`**, never the raw source ratio (things like `2592/1798`)

---

## Layout 5: Image Grid (Multi-Image Comparison)

```html
<section class="slide light">
  <div class="chrome">
    <div>Platform Follower Proof</div>
    <div>Act I / Ops · 05 / 27</div>
  </div>
  <div class="frame" style="padding-top:5vh">
    <div class="kicker">Proof · Follower Evidence</div>
    <h2 class="h-xl">10 Platforms · 6 Screenshots</h2>

    <div class="grid-3-3" style="margin-top:4vh">
      <figure class="frame-img" style="height:26vh">
        <img src="images/weibo.png" alt="Weibo 289K">
        <figcaption class="img-cap">Weibo · 289K</figcaption>
      </figure>
      <figure class="frame-img" style="height:26vh">
        <img src="images/twitter.png" alt="Twitter 137K">
        <figcaption class="img-cap">Twitter · 137K</figcaption>
      </figure>
      <figure class="frame-img" style="height:26vh">
        <img src="images/wechat.png" alt="WeChat Official Account 96K">
        <figcaption class="img-cap">WeChat · 96K</figcaption>
      </figure>
      <figure class="frame-img" style="height:26vh">
        <img src="images/jike.png" alt="Jike 26K">
        <figcaption class="img-cap">Jike · 26K</figcaption>
      </figure>
      <figure class="frame-img" style="height:26vh">
        <img src="images/xhs.png" alt="Xiaohongshu 19K">
        <figcaption class="img-cap">Xiaohongshu · 19K</figcaption>
      </figure>
      <figure class="frame-img" style="height:26vh">
        <img src="images/douyin.png" alt="Douyin 10K">
        <figcaption class="img-cap">Douyin · 10K</figcaption>
      </figure>
    </div>
  </div>
  <div class="foot">
    <div>Screenshot date · 2026.04</div>
    <div>Page 05 · Follower Proof</div>
  </div>
</section>
```

**Key points**:
- Key rule: every `frame-img` must have a fixed `height:NNvh` (not `aspect-ratio`), otherwise the grid breaks
- Images automatically get `object-fit:cover + object-position:top`, cropping only the bottom
- Use `.grid-3-3` (3×2) or `.grid-3` (3×1) as the container

---

## Layout 6: Two-Column Pipeline

```html
<section class="slide light">
  <div class="chrome">
    <div>My Workflow</div>
    <div>Act II · 15 / 27</div>
  </div>
  <div class="frame">
    <div class="kicker">Pipeline</div>
    <h2 class="h-xl">Two Pipelines</h2>

    <!-- First group: text side -->
    <div class="pipeline-section">
      <div class="pipeline-label">Text Pipeline</div>
      <div class="pipeline">
        <div class="step">
          <div class="step-nb">01</div>
          <div class="step-title">Draft</div>
          <div class="step-desc">AI drafts the first version</div>
        </div>
        <div class="step">
          <div class="step-nb">02</div>
          <div class="step-title">Polish</div>
          <div class="step-desc">AI polishes out the "AI feel"</div>
        </div>
        <div class="step">
          <div class="step-nb">03</div>
          <div class="step-title">Morph</div>
          <div class="step-desc">AI reshapes it for Twitter / Xiaohongshu</div>
        </div>
        <div class="step">
          <div class="step-nb">04</div>
          <div class="step-title">Illustrate</div>
          <div class="step-desc">AI generates an infographic</div>
        </div>
        <div class="step">
          <div class="step-nb">05</div>
          <div class="step-title">Distribute</div>
          <div class="step-desc">One click distributes to 9 platforms</div>
        </div>
      </div>
    </div>

    <!-- Second group: video side -->
    <div class="pipeline-section">
      <div class="pipeline-label">Visual · Video Pipeline</div>
      <div class="pipeline">
        <div class="step">
          <div class="step-nb">06</div>
          <div class="step-title">Cut</div>
          <div class="step-desc">AI helps me edit</div>
        </div>
        <div class="step">
          <div class="step-nb">07</div>
          <div class="step-title">Wrap</div>
          <div class="step-desc">AI helps me package it</div>
        </div>
        <div class="step">
          <div class="step-nb">08</div>
          <div class="step-title">Cover</div>
          <div class="step-desc">AI generates the cover art</div>
        </div>
      </div>
    </div>
  </div>
  <div class="foot">
    <div>Page 15 · My Content Factory</div>
    <div>Workflow</div>
  </div>
</section>
```

**Key points**:
- Use `.pipeline-section` to group steps, `.pipeline-label` for the group title
- The two groups are separated by a 3.6vh gap + a thin top divider line (already preset in CSS)
- Each step has a fixed structure: nb → title → desc
- No hard limit on step count, but keep each row to ≤5 steps — otherwise move overflow to the second pipeline

---

## Layout 7: Suspenseful Close / Question Page (Hero Question)

```html
<section class="slide hero dark">
  <div class="chrome">
    <div>A Question for You</div>
    <div>24 / 27</div>
  </div>
  <div class="frame" style="display:grid; gap:8vh; align-content:center; min-height:80vh">
    <div class="kicker">The Question</div>
    <h1 class="h-hero" style="font-size:7vw; line-height:1.15">
      In your company,<br>
      which roles<br>
      were never meant for a human?
    </h1>
    <p class="lead" style="max-width:50vw">
      This question isn't a technical one — it's an architectural one.
    </p>
  </div>
  <div class="foot">
    <div>Page 24 · The Question</div>
    <div>— · —</div>
  </div>
</section>
```

**Key points**:
- The more whitespace on a hero page, the better — put just one question
- Adjust `h-hero` font size to fit line length (7vw suits 3 lines, 10vw suits 1 line)
- Break lines manually with `<br>`, at semantically natural points
- Optionally add one more `lead` line at the end to drive the point home

---

## Layout 8: Big Quote Page (Big Quote · Serif Punchline)

```html
<section class="slide light">
  <div class="chrome">
    <div>The Takeaway</div>
    <div>18 / 25</div>
  </div>
  <div class="frame" style="display:grid; gap:5vh; align-content:center; min-height:80vh">
    <div class="kicker">Quote</div>
    <blockquote style="font-family:var(--serif-zh); font-weight:700; font-size:5.8vw; line-height:1.2; letter-spacing:-.01em; max-width:72vw">
      "No handoffs —<br>everyone is building."
    </blockquote>
    <p class="lead" style="max-width:55vw; opacity:.65">
      Without the handoff, everyone builds.<br>
      And that makes all the difference.
    </p>
    <div class="meta-row">
      <span>— Luke Wroblewski</span><span>·</span><span>2026.04.16</span>
    </div>
  </div>
  <div class="foot">
    <div>Page 18 · Quote</div>
    <div>— · —</div>
  </div>
</section>
```

**Key points**:
- Full-page whitespace, showing just one big quote + attribution
- Size the `<blockquote>` with inline style (5-6vw) — don't use `h-hero` (that's reserved for page-level headlines)
- Follow with the English original as a `lead` (opacity:.65) to create hierarchy
- Use `meta-row` for source · date

---

## Layout 9: Side-by-Side Comparison (A vs B · Old vs New)

```html
<section class="slide light">
  <div class="chrome">
    <div>Old vs New · The Shift</div>
    <div>12 / 25</div>
  </div>
  <div class="frame" style="padding-top:5vh">
    <div class="kicker">Before / After · A Paradigm Shift</div>
    <h2 class="h-xl" style="margin-bottom:4vh">From Handoff to Co-Building</h2>

    <div class="grid-2-6-6" style="gap:5vw 4vh">
      <!-- Left column: old -->
      <div style="padding:3vh 2vw; border-left:3px solid currentColor; opacity:.55">
        <div class="kicker" style="opacity:.9">Before · Old Model</div>
        <h3 class="h-md" style="margin-top:2vh">Design → Develop → Handoff</h3>
        <ul style="margin-top:3vh; padding-left:1.2em; display:flex; flex-direction:column; gap:1.4vh; font-family:var(--sans-zh); font-size:max(14px,1.1vw); line-height:1.55">
          <li>Designer works in Figma</li>
          <li>Developer stares at files, translating pixels</li>
          <li>Repeated PR back-and-forth to align</li>
          <li>Non-technical people can't touch the code</li>
        </ul>
      </div>
      <!-- Right column: new -->
      <div style="padding:3vh 2vw; border-left:3px solid currentColor">
        <div class="kicker" style="opacity:.9">After · New Model</div>
        <h3 class="h-md" style="margin-top:2vh">Same Tool · Parallel · Co-Building</h3>
        <ul style="margin-top:3vh; padding-left:1.2em; display:flex; flex-direction:column; gap:1.4vh; font-family:var(--sans-zh); font-size:max(14px,1.1vw); line-height:1.55">
          <li>All three roles work in Intent at once</li>
          <li>agents.md serves as shared context</li>
          <li>Agents handle alignment / conflicts / animation</li>
          <li>Anyone can safely contribute code</li>
        </ul>
      </div>
    </div>
  </div>
  <div class="foot">
    <div>Page 12 · A Paradigm Shift</div>
    <div>Before / After</div>
  </div>
</section>
```

**Key points**:
- Use `.grid-2-6-6` (1:1) to split left and right
- Left column at `opacity:.55` visually mutes the "old"; right column at full brightness highlights the "new"
- Both columns use `border-left:3px solid` + `padding-left` for a quote-block feel
- Each column has a consistent structure: `kicker` → `h-md` → `<ul>` bullet points, matching rhythm

---

## Layout 10: Text-and-Image Mix (Lead Image + Side Text)

```html
<section class="slide light">
  <div class="chrome">
    <div>Design First</div>
    <div>08 / 16</div>
  </div>
  <div class="frame grid-2-8-4" style="padding-top:6vh">
    <!-- Left column: long-form body copy + quote -->
    <div>
      <div class="kicker">Phase 01 · Design Phase</div>
      <h2 class="h-xl" style="margin-top:1vh; margin-bottom:3vh">Design First · 2 Weeks</h2>

      <p class="lead" style="margin-bottom:3vh">
        Completed visual exploration and the design system in Figma — grid / typography / color variables / reusable components — with several rounds of feedback on desktop and mobile drafts.
      </p>

      <p style="font-family:var(--sans-zh); font-size:max(14px,1.15vw); line-height:1.75; opacity:.78; margin-bottom:2.4vh">
        Within two weeks, the visual style, rough structure, and directional content were all settled. This is a solid, traditional design process — nothing new here yet.
      </p>

      <div class="callout" style="margin-top:3vh">
        "This phase was pretty standard.<br>Just a solid Web design process."
        <div class="callout-src">— Luke Wroblewski</div>
      </div>
    </div>
    <!-- Right column: supporting image · portrait or square -->
    <figure class="frame-img" style="aspect-ratio:3/4; max-height:60vh">
      <img src="images/figma.png" alt="Figma design system">
      <figcaption class="img-cap">Figma · Design System</figcaption>
    </figure>
  </div>
  <div class="foot">
    <div>Page 08 · Design First</div>
    <div>~2 weeks</div>
  </div>
</section>
```

**Key points**:
- `.grid-2-8-4` (8:4) lets the body copy dominate, with the image as support
- The left column has multiple information layers: kicker → big headline → lead → body paragraph → callout (quote)
- The right-column image should be **portrait 3:4** or square 1:1, so it doesn't compete for attention with the left-column text
- This layout suits **pages with a larger amount of information** (unlike Layout 4, which is just one punchline)

---

## Appendix: Common Grid Templates

| Class | Ratio | Use |
|---|---|---|
| `.grid-2-6-6` | 6:6 (1:1) | Even split |
| `.grid-2-7-5` | 7:5 | Text-dominant + supporting image |
| `.grid-2-8-4` | 8:4 (2:1) | Long-form text + small image/data |
| `.grid-3` | 1:1:1 | 3 items side by side (case studies/screenshots) |
| `.grid-3-3` | 3×2 | 6-image matrix |
| `.grid-6` | 3×2 | 6 data cards |

All grids default to `gap: 3vw 4vh` (3vw horizontal, 4vh vertical), overridable individually.

---

## Recommended Page Pacing

For a 25-30 page talk, the following pacing is recommended:

1. **Hero Cover** (page 1)
2. **Act Divider** (Act I opening, hero light or hero dark)
3. **Big Numbers** (throw out hard data for impact)
4. **Quote + Image** (identity contrast/hook)
5. **Image Grid** (supporting evidence)
6. **Hero Question** (act close, leave suspense)
7. ... Acts II, III follow the same pacing ...
8. **Hero Close** (final page, a question or thanks)

Hero pages and non-hero pages should interleave at roughly a **2-3 : 1 ratio** — never more than 3 consecutive non-hero pages, and never more than 2 consecutive hero pages.
