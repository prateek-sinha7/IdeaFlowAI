# presenter-mode-reveal · Presenter Mode Template

A full-deck template built specifically for **technical talks with a real speaker script**. The core selling point is a genuinely usable **magnetic card-based presenter view**: current-slide iframe preview + next-slide iframe preview + large-type speaker script + timer, all as 4 freely draggable/resizable cards, entirely self-contained inside `runtime.js`, zero dependencies.

## Use cases

- Technical talks (30-60 min)
- Product launch keynotes
- Course lectures
- Any **formal talk where you need to speak from notes but can't sound like you're reading a script**

## Quick start

```bash
cp -r templates/full-decks/presenter-mode-reveal examples/my-talk
open examples/my-talk/index.html
```

## Keyboard shortcuts

| Key | Action |
|---|---|
| `S` | Open the presenter window (pops a new window, audience page stays untouched) |
| `T` | Switch theme (5 presets) |
| `←` `→` | Navigate slides |
| `Space` / `PgDn` | Next slide |
| `F` | Fullscreen |
| `O` | Overview / thumbnail grid |
| `R` | Reset timer (presenter view only) |
| `Esc` | Close all overlays |

## Theme switching

The template ships with 5 presenter-friendly themes preset in the `<html data-themes="...">` attribute:

```html
<html lang="en" data-themes="tokyo-night,dracula,catppuccin-mocha,nord,corporate-clean">
```

Press `T` to cycle through them. You can swap in any theme from `assets/themes/*.css`.

## Speaker-script conventions

**Write 150–300 words inside `<aside class="notes">` on every slide.** Three iron rules:

1. **Not a script — prompt signals** — bold the core points, give transition lines their own paragraph, spell out data clearly
2. **150–300 words per slide** — paced for roughly 2–3 minutes per slide
3. **Write it in spoken language** — "therefore" → "so"; "the aforementioned approach" → "this approach"; read it out loud, it should sound natural

Example:
```html
<aside class="notes">
  <p>Hey everyone, today I want to talk about <strong>something a lot of people overlook</strong>——...</p>
  <p>Let me open with a claim: <em>building a deck and delivering a talk are two different things</em>.</p>
  <p>I'll prove this with 3 examples...</p>
</aside>
```

Supported inline tags:
- `<strong>` — highlight (orange)
- `<em>` — italic emphasis (blue)
- `<code>` — monospace
- `<p>` — paragraph break (recommended: 30-60 seconds of content per paragraph)

## File structure

```
presenter-mode-reveal/
├── index.html       # 6 example slides, each with a full speaker script
├── style.css         # scoped .tpl-presenter-mode-reveal styles
└── README.md          # this file
```

## Modifying / extending

- **Add a slide**: duplicate any `<section class="slide">` block and edit its content and `<aside class="notes">`
- **Change theme**: edit the `data-themes` list, or directly change `<link id="theme-link" href="...">`
- **Change styling**: only touch `style.css` — don't touch the root `assets/base.css`
- **Add motion**: add `data-anim="fade-up"` etc. to elements (see `references/animations.md`)

## The 4 cards in the presenter window

Pressing `S` pops open a window containing:

- 🔵 **CURRENT** — current-slide iframe preview (loaded via `?preview=N` mode, pixel-perfect, sharing the same CSS/theme/fonts as the audience view)
- 🟣 **NEXT** — next-slide preview, to help you prep transitions
- 🟠 **SPEAKER SCRIPT** — large-type speaker script, scrollable
- 🟢 **TIMER** — elapsed time + slide count + Prev/Next/Reset buttons

Card behavior:
- **Drag the card header** (the colored dot + title bar at the top) → move the card
- **Drag the bottom-right corner** → resize
- Position + size auto-save to localStorage and restore on next open
- The "Reset Layout" button at the bottom restores the default card arrangement

Slide navigation is seamless: the iframe loads once, and subsequent navigation switches the internal slide via `postMessage` — **no reload, no flicker**. The two windows stay in sync in both directions via `BroadcastChannel`.

## Notes

- **The audience never sees `.notes` content** — CSS defaults it to `display:none`, visible only in presenter view
- **Don't write anything meant only for yourself directly on the slide body** — all prompts belong inside `<aside class="notes">`
- **Dual-screen presenting**: open `index.html`, press S to pop the presenter window, drag the audience window to the projector/external display and press F for fullscreen, and keep the presenter window on your own screen
