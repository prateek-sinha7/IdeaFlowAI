---
name: html-deck-to-pptx
description: Turn a finished HTML slide deck into a real, editable PowerPoint file with PptxGenJS — the layout contract, the five rules that break the build, and the geometry the verifier enforces.
---

# HTML deck → PowerPoint

You are transcribing a finished HTML deck into a `.pptx` a person can open and
**edit**. Live text boxes, not pictures of slides.

`render_pptx` builds the file **and verifies it**. You do not get `ok` for a deck
with overlapping text, text that does not fit its box, or shapes off the canvas —
you get the violations, and you fix them and call it again. Everything below is
how to pass that on the first try instead of the fourth.

## The canvas — decide it, state it, respect it

**The HTML deck has no pixel size.** It is authored in viewport units — every
slide is `100vw × 100vh` and every font size is a `vw` fraction. There is no
1280 × 720 to divide by 96, and there is nothing to measure. A previous version
of this file claimed otherwise and it is the reason decks came out with every
headline three times too tall for its box.

So you choose the canvas, and then everything is relative to it:

```js
pres.defineLayout({ name: "DECK", width: 13.333, height: 7.5 });
pres.layout = "DECK";              // BEFORE the first addSlide()
```

**Set the layout before you add any slide.** PptxGenJS applies the layout at slide
creation, so a `defineLayout` afterwards silently does nothing and you get the
default `LAYOUT_16x9` — **10" × 5.625"** — while your coordinates assume something
else. Content then lands off the canvas, written to the file but never displayed.

Both 13.333 × 7.5 and 10 × 5.625 are 16:9 and both are fine. What is not fine is
building for one and declaring the other.

Convert the HTML's proportions, not its numbers: a heading that fills a third of
the slide's height is `0.33 × canvas height`, whatever the canvas is.

## Text has to FIT — this is what actually fails

The verifier measures the real font at the real size and word-wraps at the real
box width. A box is not "big enough" because the text looks fine in the HTML.

- **Give a heading the height its lines need.** Four wrapped lines of 48pt text
  need roughly `4 × 56pt ≈ 3.1"`, not `1.2"`. PowerPoint does not clip the
  overflow — it prints it over whatever is underneath.
- **Never set `lineSpacing` below the font size.** `fontSize: 48` with
  `lineSpacing: 28` makes consecutive lines print through each other. This is the
  single most common cause of "the pptx has overlapping text". If you want tight
  leading, `lineSpacing: fontSize * 0.95` is as far as it goes.
- **This applies across paragraphs too.** A title stacked as three one-line
  paragraphs — `Bespoke` / `Social` / `Platform` at 72pt on 38pt leading — is the
  same collision: what overlaps is the frame's lines, not one paragraph's. Either
  give the frame leading its font can live with, or make it three separate boxes
  positioned where you want them.
- **Shorten the text or enlarge the box — never leave content cut off.** Reducing
  the font size is the third option, not the first.
- **Prefer fonts whose width is predictable:** Arial, Calibri, Verdana, Tahoma,
  Times New Roman. Georgia, Cambria, Garamond and Trebuchet render wider than
  they measure, so give anything set in them ~10% extra room.

## MAP the fonts — never copy the names

The HTML deck loads its type from Google Fonts. A `.pptx` stores a font NAME and
nothing else, so writing `DM Sans` into it produces a file that looks right on
exactly one machine — yours. On the client's PowerPoint the name is missing,
something else is substituted, and every line rewraps.

Read the deck's `@import` / `font-family` and translate to the nearest family
that ships with Office:

| The deck's font | What goes in the pptx |
|---|---|
| DM Sans, Inter, Poppins, Montserrat, Work Sans, Lato, Open Sans, Roboto | **Arial** or **Calibri** |
| Space Grotesk, Archivo, Barlow, Manrope | **Segoe UI** or **Arial** |
| Playfair Display, Cormorant Garamond, Lora, Merriweather, Spectral | **Georgia** or **Cambria** |
| EB Garamond, Libre Baskerville | **Garamond** or **Times New Roman** |
| Courier Prime, JetBrains Mono, IBM Plex Mono, Space Mono, Fira Code | **Courier New** or **Consolas** |

Anything not on this list: pick by category — sans → Arial, serif → Georgia,
mono → Courier New. The full safe set is Arial, Arial Black, Calibri, Cambria,
Candara, Consolas, Constantia, Corbel, Courier New, Garamond, Georgia, Impact,
Palatino Linotype, Segoe UI, Tahoma, Times New Roman, Trebuchet MS, Verdana.

The verifier fails any font outside it, once per family, naming how many shapes
use it. Losing the exact typeface is the cost of a file the client can open and
edit — say so in your final message rather than implying the type carried over.

## Five rules that break the build

1. **`pres` is the variable name.** The runner looks for it.
2. **End with `return pres.write("nodebuffer");`** — nothing else counts as output.
3. **No `require`, no `import`.** PptxGenJS is already in scope.
4. **Hex colours carry no `#` and no alpha.** `"1B1B1B"`. `"#1B1B1B"` or an
   8-digit value corrupts the file.
5. **Never reuse an options object across two `add*` calls.** PptxGenJS mutates it
   in place during EMU conversion, so the second call gets the first one's
   converted numbers.

Two more that corrupt quietly:

- **Shadow offsets must be non-negative.** Use `angle` for an upward shadow.
- **Lists need `bullet: true` on each item and `breakLine: true` on all but the
  last.** Never type a literal `•`.

## Units

- Positions and sizes: **inches**, relative to the canvas you declared.
- Font sizes: **points**. A `vw` size becomes a point size by proportion —
  `3vw` of a 13.333" canvas is `0.03 × 13.333 × 72 ≈ 29pt`.
- Keep content clear of the footer band at the bottom of the canvas; the verifier
  enforces a content rail there.

## Charts

Rebuild them from the numbers printed on the slide. Never measure the bars in the
HTML — you will transcribe a rounding error as data.

## What the verifier will tell you

Each violation names the slide, the shape and the measurement:

```
slide 3  shape 'Text 5' line spacing is 28.0pt (exact) but 48pt text needs 56.0pt
         — consecutive lines will print through each other
slide 3  shape 'Text 5' text needs 1.56" but the box is 1.10" tall
slide 10 shape 'Text 8' bottom 5.750" exceeds canvas 5.625"
```

Fix exactly what it names. `extract_pptx_shapes()` dumps the real positions inside
the built file when a violation does not match what you believe you wrote — the
file is the truth, your source is the intention.

`screenshot_pptx()` renders the deck and reports whether it opens at all and how
many slides came out. Reach for it when the numbers look right and you still
doubt the result: a deck no renderer will load is corrupt whatever the geometry
says. Every verdict, every rendered slide and the exact source of each attempt
are written to `.verify/` in the workspace, so a human can see what the gate saw.

## Transitions do not survive

The HTML deck's CSS transitions and animations have no equivalent: PptxGenJS has
no slide-transition API. Transcribe the content and the design; say plainly that
motion did not carry over rather than implying the pptx matches the HTML exactly.
