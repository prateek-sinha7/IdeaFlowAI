# Presenter Mode Guide

This document explains how to build a **presentation deck with a full speaker script (presenter mode)** using the html-ppt skill.

## When to use presenter mode

**Prefer presenter mode** when the user's request touches on any of the following:

- Mentions "**presentation**", "**talk**", "**speaker script**", "**verbatim script**", "**speaker notes**"
- Mentions "**presenter view**", "**presenter view**", "**presenter mode**"
- Needs a "**30-minute / 45-minute / 1-hour**" talk
- Says "I need to present xxx to my team", "I'm doing a tech talk", "I'm doing a roadshow pitch"
- Emphasizes "**don't want to forget my lines**", "**afraid of stumbling**", "**need a teleprompter**"

If the user only wants a "**static, good-looking deck**" (e.g. Xiaohongshu (RED) style image-and-text posts, a product lookbook, or report slides they won't be presenting live themselves), presenter mode is **not needed**.

## Two approaches

### Recommended: use the `presenter-mode-reveal` template directly

```bash
cp -r templates/full-decks/presenter-mode-reveal examples/my-talk
```

This template already has every required element preconfigured:
- Supports pressing `S` to toggle presenter view
- 5 themes available, cycled with the `T` key (tokyo-night / dracula / catppuccin-mocha / nord / corporate-clean)
- Left/right arrow keys to navigate slides
- Every slide has a sample 150–300 word speaker script
- A key-hint bar at the bottom

Just edit the content directly.

### Advanced: add presenter mode to any existing template

html-ppt's **`S`-key presenter view is built into `runtime.js`, and every full-deck template supports it automatically**. You only need to do two things:

1. **Add an `<aside class="notes">`** (or `<div class="notes">`) at the end of each slide, containing the speaker script
2. **Confirm the HTML imports `assets/runtime.js`**

```html
<section class="slide">
  <h2>Your Title</h2>
  <p>Content...</p>
  <aside class="notes">
    <p>This is what you say while presenting, 150-300 words...</p>
  </aside>
</section>
```

## The three iron rules of writing a speaker script

This is the core of the whole methodology. When the AI writes a speaker script for a user, it must follow these rules:

### Rule 1: It's not a script to read aloud, it's a "prompt signal"

**Wrong** (reads like reciting a script):
```
Hello everyone, welcome to today's presentation. Today I'm going to walk you through the work our team has done over the past three months.
First, let's look at the background. Over the past three months, we ran into the following problems...
```

**Right** (prompt signal + bolded core points):
```
<p>Welcome! Today I'll share our team's work from <strong>the past 3 months</strong>.</p>
<p>Let's start with <em>the background</em>—three months ago we ran into <strong>three core problems</strong>:
high latency, exploding costs, poor stability.</p>
<p>Now let's go through how we solved each one.</p>
```

**The difference**: the correct version bolds the key words and gives transition sentences their own paragraph, so you can pick it up at a glance.

### Rule 2: 150–300 words per slide

- **Fewer than 150 words**: not enough of a prompt, you'll get stuck halfway through
- **More than 300 words**: you won't have time to scan it all
- **2–3 minutes per slide** is the most comfortable pace

### Rule 3: Use conversational language, not written/formal language

| Formal | Conversational |
|---|---|
| "Therefore" | "So" |
| "This approach" | "This" |
| "However" | "But" |
| "Optimize the solution" | "Tune it up a bit" |
| "We will proceed to" | "We'll / Next" |
| "In summary" | "So basically" |

**How to check**: read it out loud after writing it — it should sound like talking, not reading.

## Required HTML structure

```html
<!DOCTYPE html>
<html lang="en" data-themes="tokyo-night,dracula,corporate-clean">
<head>
  <meta charset="utf-8">
  <title>...</title>
  <link rel="stylesheet" href="../../../assets/fonts.css">
  <link rel="stylesheet" href="../../../assets/base.css">
  <link rel="stylesheet" id="theme-link" href="../../../assets/themes/tokyo-night.css">
  <link rel="stylesheet" href="../../../assets/animations/animations.css">
  <link rel="stylesheet" href="style.css">
</head>
<body>
<div class="deck">

  <section class="slide" data-title="Cover">
    <h1>Your Title</h1>
    <p>Subtitle</p>
    <aside class="notes">
      <p>Script paragraph 1 (with <strong>bolded keywords</strong>).</p>
      <p>Script paragraph 2 (transition sentence gets its own paragraph).</p>
      <p>Script paragraph 3 (natural wrap-up, leads into the next slide).</p>
    </aside>
  </section>

  <!-- more slides ... -->

</div>
<script src="../../../assets/runtime.js"></script>
</body>
</html>
```

## What presenter view shows

Pressing `S` **pops up a separate presenter window** (the original page keeps showing the audience view unchanged). The presenter window has **4 independent, dockable cards**:

```
 Audience window (original page)   Presenter window (dockable cards)
┌─────────────────┐   ┌─────────────────────┬──────────────────┐
│                 │   │ 🔵 CURRENT         │ 🟣 NEXT            │
│  Normal slide   │   │ ━━━━━━━━━━━━━━━━ │ ━━━━━━━━━━━━━ │
│  fullscreen     │◄►│                   │  iframe preview   │
│                 │   │  iframe preview   │  (next slide)     │
│                 │   │  (current slide)  ├──────────────────┤
│                 │   │                   │ 🟠 SPEAKER SCRIPT  │
│                 │   │                   │ ━━━━━━━━━━━━━ │
│                 │   ├─────────────────────┤  [large-print script] │
│                 │   │ 🟢 TIMER           │  [scrollable]     │
│                 │   │ ⏱ 12:34   3 / 8 │                   │
│                 │   │ [← Prev][Next →]  │                   │
└─────────────────┘   └─────────────────────┴──────────────────┘
       ↑ BroadcastChannel keeps navigation synced both ways ↑
```

Card interaction rules:
- **Drag a card's header** (the top bar with the colored dot and title) → move the card
- **Drag the triangular handle in the card's bottom-right corner** → resize the card
- **Position/size is auto-saved to localStorage**, restored next time you open it
- The "Reset Layout" button at the bottom restores the default arrangement

Card contents:
- 🔵 **CURRENT** — a **pixel-perfect preview** of the current slide (an iframe loading the original HTML file in `?preview=N` mode, so color mismatches are impossible)
- 🟣 **NEXT** — a preview of the next slide, equally pixel-perfect
- 🟠 **SPEAKER SCRIPT** — the script text, 18px font, supports inline styles like `<strong>` (bold orange), `<em>` (blue emphasis), `<code>`, etc.
- 🟢 **TIMER** — a timer that never loses focus, with page-navigation buttons

Syncing between windows: pressing ← → in either window navigates, and the other window automatically syncs (via BroadcastChannel).

Smooth navigation: the iframe loads only once; subsequent page changes use `postMessage` to switch the visible slide, **no reload, no flicker**.

## Keyboard shortcuts (presenter mode)

| Key | Action |
|---|---|
| `S` | Open presenter window (pops up a new window, original page stays in audience view) |
| `←` `→` / Space / PgDn | Navigate slides (works even while in presenter view) |
| `T` | Switch theme |
| `R` | Reset timer (presenter view only) |
| `F` | Fullscreen |
| `O` | Overview |
| `Esc` | Close all overlays |

## Standard workflow for a dual-screen presentation

1. Open `index.html`, press `S` → the presenter window pops up
2. Drag the **audience window** (original page) to the projector / external display, press `F` for fullscreen
3. Keep the **presenter window** (popup) on the screen in front of you
4. Press ← → in either window to navigate; both sides stay in sync automatically
5. Use the presenter window to read the script + preview the next slide + track the timer

> **Why the preview is pixel-perfect**: each preview is an `<iframe>` loading the exact same deck HTML file, just with a `?preview=N` parameter added to the URL. When `runtime.js` detects this parameter, it renders only slide N and hides all chrome. **The iframe uses exactly the same CSS, theme, fonts, and viewport as the audience view**, guaranteeing consistent colors and layout. The outer wrapper uses CSS `transform: scale()` to scale the 1920×1080 canvas down to the card's width/height, preserving aspect ratio without distortion.

> **Why there's no flicker**: once the iframe loads, it stays resident; on page change the presenter window sends `postMessage({type:'preview-goto', idx:N})` to tell the iframe to switch to slide N. The `runtime.js` inside the iframe just toggles the `.is-active` class, **no reload, no white flash**.

## Common mistakes

### Writing the speaker script somewhere visible on the slide

```html
<!-- Wrong: the audience will see this text -->
<p style="font-size:12px;color:gray">
  Talk about xxx here, then yyy...
</p>
```

Correct:
```html
<aside class="notes">
  <p>Talk about xxx here, then yyy...</p>
</aside>
```

The `.notes` class defaults to `display:none`, visible only in presenter view.

### Forgetting to import runtime.js

Without `<script src="../../../assets/runtime.js"></script>`, there's no `S` key, no presenter view, no page navigation.

### Writing the script in formal/written language

Read aloud, it sounds like a robot. **Always read it back after writing it.**

### 50 words per slide

Not enough of a prompt — you'll still forget your lines.

### 500 words per slide

Your eyes simply can't scan it fast enough — it's as good as not having a script.

## Standard prompt for generating a speaker script with AI

> "Write a **150-300 word** speaker script for each slide, placed inside `<aside class="notes">`.
> Requirements:
> 1. Use **conversational language**, not formal/written language ("so"/"but"/"next", not "therefore"/"however"/"in summary")
> 2. Bold the **key terms** using `<strong>`
> 3. Give transition sentences their own paragraph (1-3 sentences per paragraph)
> 4. It should read like talking, not like reciting a script
> 5. End with a natural transition that leads into the next slide"

## Recommended pairings

- **Theme**: `tokyo-night` (dark, best for tech talks), `corporate-clean` (light, for business reports), `dracula` (dark alternative)
- **Fonts**: default Noto Sans SC + JetBrains Mono, no changes needed
- **Animation**: use sparingly — `fade-up` / `rise-in` feel most natural; avoid flashy ones like `glitch-in` / `confetti-burst`
- **Slide count**: 30-minute talk = 8–12 slides; 45-minute = 12–16 slides; 1 hour = 16–22 slides
