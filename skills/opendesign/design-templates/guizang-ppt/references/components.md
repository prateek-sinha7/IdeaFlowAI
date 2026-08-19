# Component Reference · Components

This is the component manual for the `magazine-web-ppt` skill. template.html already defines all the styles — this doc only covers "what this component looks like and how to use it."

## Table of Contents

- [Basic Slide Shell](#basic-slide-shell)
- [Typography](#typography)
- [Chrome & Foot](#chrome--foot)
- [Callout Quote Box](#callout-quote-box)
- [Stat Number Grid](#stat-number-grid)
- [Platform Card](#platform-card)
- [Rowline Table Row](#rowline-table-row)
- [Pillar Card](#pillar-card)
- [Tag & Kicker](#tag--kicker)
- [Figure Image Frame](#figure-image-frame)
- [Icons](#icons)
- [Ghost Giant Background Text](#ghost-giant-background-text)
- [Highlight Marker](#highlight-marker)

---

## Basic Slide Shell

Every page is a `<section class="slide ...">`. It must include a `data-theme` attribute (`light` or `dark`) — the page-turn JS switches the background based on this attribute.

```html
<section class="slide light" data-theme="light">   <!-- Light page -->
<section class="slide dark" data-theme="dark">     <!-- Dark page -->
<section class="slide light hero" data-theme="light">  <!-- Hero page: light + thin overlay revealing WebGL -->
<section class="slide dark hero" data-theme="dark">    <!-- Hero page: dark + thin overlay -->
```

**Using light vs dark: alternate between them.** Switch themes every 2-3 pages, and avoid more than 3 consecutive pages of the same color. When paging, the WebGL background automatically transitions between the two shaders.

**Using the `hero` class**: only add it to visually dominant pages (cover, key-quote pages, chapter transitions, ending). With `hero` added, the overlay drops to 12-16% and the WebGL background shows through much more strongly, so don't put too much text on hero pages.

---

## Typography

Font assignment is the single most important rule in this template — never mix fonts.

| Class | Purpose | Font |
|---|---|---|
| `.display` | Extra-large English text (Hero pages) | Playfair Display 700, 11vw |
| `.display-zh` | Extra-large heading (CJK) | Noto Serif SC 700, 7.8vw |
| `.h1-zh` | Page main heading | Noto Serif SC 700, 4.6vw |
| `.h2-zh` | Subheading | Noto Serif SC 600, 3.2vw |
| `.h3-zh` | Pipeline step heading | Noto Serif SC 500, 1.9vw |
| `.lead` | Lead paragraph (larger than body) | Noto Serif SC 400, 1.9vw |
| `.body-zh` | **Body text/description (sans-serif)** | Noto Sans SC 400, 1.22vw |
| `.body-serif` | Body text (serif) | Noto Serif SC 400, 1.3vw |
| `.kicker` | Section hint (above heading) | IBM Plex Mono, 12px uppercase |
| `.meta` | Metadata label | IBM Plex Mono, 0.88vw uppercase |
| `.big-num` | Giant number | Playfair Display 800, 10vw |
| `.mid-num` | Medium number | Playfair Display 700, 5.5vw |

**Core rules**:
- **Serif** (`serif-zh` / `serif-en`): headings, key quotes, numbers — used for "visual emphasis"
- **Sans-serif** (`sans-zh`): body descriptions, long-form reading content — used for "information density"
- **Monospace** (`mono`): kicker, meta, English labels in the foot — used for "decorative rhythm"

**Emphasis techniques**:
- `<em class="en">English word</em>` — renders the English word in Playfair Display italic (looks great)
- `<em style="opacity:.65">phrase</em>` — fades out the second half of a heading, creating rhythm

---

## Chrome & Foot

The metadata bar at the top and bottom of each page. Almost every page should have one.

```html
<div class="chrome">
  <div class="left">
    <span>Act I · Hard Data</span>
    <span class="sep"></span>
    <span>Act I</span>
  </div>
  <div class="right"><span>02 / 27</span></div>
</div>

<!-- ... page body ... -->

<div class="foot">
  <div class="title">Project Name · CodePilot | github.com/codepilot</div>
  <div>Act I · Dev Numbers</div>
</div>
```

**Rules**:
- `chrome.right` always holds the page number, `NN / TOTAL` (TOTAL is the total page count)
- `foot.title` is a native-language caption, `foot.right` is the English act marker
- chrome and foot together form the "header/footer" that gives the deck its magazine feel

---

## Callout Quote Box

Used to display a key quote, a key point, or someone else's words.

```html
<div class="callout" style="max-width:80vw">
  <div class="q-big">"Three years ago, this would have<br>taken a ten-person team a year."</div>
  <span class="cite">— an observer's judgment</span>
</div>
```

Variants:
- Without a citation: just omit the `<span class="cite">`
- With an English quote: `<em class="en">"Thin Harness, Fat Skills."</em>`
- On a hero page: add `style="position:relative;z-index:2"` on the outer element (to avoid being covered by the background overlay)

---

## Stat Number Grid

Displays data metrics, usually paired with `.grid-6` / `.grid-4`.

```html
<div class="grid-6">
  <div class="stat">
    <span class="m">Duration</span>
    <span class="n">64<em style="font-size:.4em;opacity:.5;font-style:normal"> days</em></span>
    <span class="l">From 0 to now</span>
  </div>
  <!-- ... more stats ... -->
</div>
```

Three-part structure: `.m` monospace small label → `.n` giant number → `.l` descriptive caption. The unit after the number is shrunk to 0.4em using `<em>`, with opacity 0.5.

**Common layout containers**:
- `.grid-6` — 3×2 grid (most common, 6 stats)
- `.grid-4` — 2×2 grid (4 stats)
- `.grid-3` — 3-column single row (3 stats / pillars)

---

## Platform Card

Displays a social platform / channel + follower count.

```html
<div class="plat">
  <div class="sub">Weibo</div>
  <div class="name">Weibo</div>
  <div class="nb">289K</div>
</div>
```

Optional fourth line (supplementary note):
```html
<div class="body-zh" style="font-size:max(11px,.8vw);opacity:.5;margin-top:.6vh">
  Includes cross-posting to Xiaolvshu
</div>
```

**"Also On" variant** (additional platforms):
```html
<div class="plat" style="border-top-style:dashed;opacity:.72">
  <div class="sub">Also On</div>
  <div class="body-zh" style="font-weight:600;margin-top:.8vh">
    Bilibili · Zhihu
  </div>
</div>
```

---

## Rowline Table Row

List-style content, one entry per row.

```html
<div class="rowline">
  <div class="k">CLAUDE.md</div>
  <div class="v">How you're supposed to work — behavioral rules + work preferences + prohibited actions</div>
  <div class="m">EMPLOYEE · HANDBOOK</div>
</div>
```

Three-column structure: `.k` serif keyword · `.v` body description · `.m` monospace label (right-aligned). The first and last rowline automatically get top/bottom borders.

**Variant: 2 columns**: `style="grid-template-columns:1fr 3fr"` to drop the `.m` column.

---

## Pillar Card

A three-pillar structure, commonly used for "parallel concepts" style pages.

```html
<div class="grid-3">
  <div class="pillar">
    <div class="ic">01</div>
    <div class="t">Three-layer<br>documentation system</div>
    <div class="d">CLAUDE.md<br>+ project knowledge base<br>+ guardrail files</div>
  </div>
  <!-- ... more pillars ... -->
</div>
```

**Pillar with icon (for emphasis pages)**:
```html
<div class="pillar" style="padding:4vh 2vw;border:1px solid currentColor;border-color:rgba(10,10,11,.2)">
  <div class="ic"><i data-lucide="compass" class="ico-lg"></i></div>
  <div class="t">Judgment</div>
  <div class="d">The authority behind decisions and direction.<br>Tradeoffs, taste, sense of direction.</div>
</div>
```

`.ic` can be a number (`01 / 02 / 03` or `A. / B. / C.`), or a Lucide icon.

---

## Tag & Kicker

**Kicker** is the small hint text above a heading (monospace, all caps, small size):
```html
<div class="kicker">Past 64 days · Development</div>
<div class="h1-zh">One person. Here's what got done.</div>
```

**Tag** is a standalone pill-shaped label (with a border):
```html
<div style="display:flex;gap:1.6vw;flex-wrap:wrap">
  <div class="tag">Wakes up at 10am</div>
  <div class="tag">Gym Tue/Thu afternoons</div>
  <div class="tag">Still watches shows and games at night</div>
</div>
```

---

## Figure Image Frame

**This is the trickiest component in the template — follow these rules carefully.**

### Basic structure

```html
<figure class="tile">
  <div class="frame-img" style="height:26vh">
    <img src="images/xxx.png" alt="caption">
  </div>
  <figcaption class="frame-cap">
    <span class="pf">Twitter</span>
    <span class="nb">137K</span>
  </figcaption>
</figure>
```

### Key constraints (learned the hard way — do not violate)

1. **Always use a fixed `height:Nvh`**, never `aspect-ratio`.
   - Reason: using aspect-ratio in a grid will blow out the parent container, causing images to stack.
   - Recommended sizes: `height:18vh` (compact strip) / `22vh` (standard grid) / `26vh` (featured display) / `28vh` (large image).

2. **`object-position:top center` (already set in the CSS)** only allows cropping from the bottom.
   - Never crop the left, right, or top — that's where the image's core identifying content is.

3. **When multiple images are in a grid, use an inline grid instead of `grid-3`**:
   ```html
   <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:1vh 1.2vw">
     <figure class="tile">...</figure>
     <figure class="tile">...</figure>
     <figure class="tile">...</figure>
   </div>
   ```

4. **To align an image with the rest of the layout**: add `align-self:end` to the figure to pin the image to the bottom.

### Frame Caption variants

```html
<!-- Standard: figure name on the left, number on the right -->
<figcaption class="frame-cap">
  <span class="pf">Twitter</span>
  <span class="nb">137K</span>
</figcaption>

<!-- With index number -->
<figcaption class="frame-cap">
  <span class="idx">01</span>
  <span class="pf">AI Polish</span>
  <span>Polish</span>
</figcaption>
```

### Image placeholder (design-stage placeholder)

When an image isn't ready yet, use a dashed placeholder box:
```html
<div class="img-slot r-4x3">  <!-- r-4x3 / r-16x9(default) / r-3x2 / r-1x1 -->
  <span class="plus">+</span>
  <span class="label">GitHub screenshot goes here</span>
</div>
```

---

## Icons

**Never use emoji.** Use Lucide via CDN (already included in template.html).

```html
<i data-lucide="compass" class="ico-lg"></i>     <!-- Large icon (used in pillars) -->
<i data-lucide="target" class="ico-md"></i>      <!-- Medium icon (used in list items) -->
<i data-lucide="check-circle" class="ico-sm"></i>  <!-- Small icon (used inline) -->
```

**Commonly used Lucide icon names** (grouped by meaning):

- Judgment: `compass`, `target`, `crosshair`, `search-check`
- Relationships: `share-2`, `users`, `network`, `link`, `handshake`
- Brand: `crown`, `gem`, `award`, `star`, `badge-check`
- Process: `workflow`, `route`, `arrow-right-left`, `repeat`
- Data: `grid-2x2`, `bar-chart-3`, `trending-up`, `activity`
- Aesthetics: `palette`, `brush`, `eye`, `sparkles`
- Right/wrong: `check-circle`, `x-circle`, `check`, `x`
- Direction: `arrow-right`, `arrow-up-right`, `corner-down-right`

**Combining icon and text inline**:
```html
<div class="h3-zh" style="display:flex;align-items:center;gap:.8em">
  <i data-lucide="target" class="ico-md"></i>
  Judgment — what's worth writing
</div>
```

---

## Ghost Giant Background Text

Used as "decorative background text," extremely low opacity, to create a magazine feel.

```html
<div class="ghost" style="right:-6vw;top:-8vh">BUT</div>
<div class="ghost" style="left:-8vw;bottom:-18vh;font-style:italic">Harness</div>
```

- Font size 34vw, opacity 0.06
- Common positioning: `right:-6vw;top:-8vh` (overflowing top-right) / `left:-8vw;bottom:-18vh` (overflowing bottom-left)
- Content: English words or numbers (chapter numbers 01/02/03, keywords like BUT/NOW/HERE)

**Note**: on pages using ghost, other content should have `position:relative;z-index:2` added to avoid being pushed underneath it.

---

## Highlight Marker

A "highlighter" effect for inline phrases:

```html
<span class="hi">not</span>
<span class="hi">a one-time burst</span>
```

Generates a semi-transparent highlight bar at the bottom of the text. Dark theme uses a bright bar, light theme uses a dark bar (already handled in CSS).

**Best used for**: only 1-3 key words at a time — don't overuse it across large blocks of text.
