/**
 * The static-preview fallback strip.
 *
 * Verified against the real artifact of run 8c0d5fe7 in a live Chrome: with the
 * block present the document is 8640px tall (12 slides stacked), ArrowRight
 * ArrowRight leaves the active slide at y=1440 — off screen — while the cover
 * still fills the viewport and the counter reads 3/12. With it stripped the
 * document is 720px and the active slide is at y=0.
 */

import { describe, expect, it } from "vitest";
import { hasDeckRuntime, stripStaticPreviewFallback } from "./deckHtml";

const FALLBACK = `<style>
/* Static-preview fallback (runtime.js is absent — keep every slide visible) */
.deck{height:auto;min-height:100vh;overflow:visible}
.slide{position:relative;inset:auto;opacity:1;pointer-events:auto;transform:none;height:100vh}
</style>`;

const DECK_CSS = `<style>
.slide{position:absolute;inset:0;opacity:0}
.slide.is-active{opacity:1;z-index:2}
</style>`;

const NAV = `<script>
function go(n){ slides.forEach((s,i)=>s.classList.toggle('is-active', i===n)); }
</script>`;

describe("stripStaticPreviewFallback", () => {
  it("removes the block when the deck ships a nav runtime", () => {
    const out = stripStaticPreviewFallback(`<head>${DECK_CSS}${FALLBACK}</head><body>${NAV}</body>`);
    expect(out).not.toContain("Static-preview fallback");
    // The deck's own positioning survives — that is the whole point.
    expect(out).toContain("position:absolute");
    expect(out).toContain(".slide.is-active{opacity:1");
  });

  it("KEEPS the block when there is no runtime", () => {
    // A template example.html is a static file. Stripping its fallback would
    // hide every slide but the first, with nothing able to change which.
    const html = `<head>${DECK_CSS}${FALLBACK}</head><body><section class="slide"></section></body>`;
    expect(stripStaticPreviewFallback(html)).toBe(html);
  });

  it("stops at the first </style> and leaves later blocks alone", () => {
    const after = `<style>.later{color:red}</style>`;
    const out = stripStaticPreviewFallback(`${FALLBACK}${after}${NAV}`);
    expect(out).toContain(".later{color:red}");
    expect(out).not.toContain("min-height:100vh");
  });

  it("does not treat a script-free deck as having a runtime", () => {
    expect(hasDeckRuntime(`<style>.slide.is-active{opacity:1}</style>`)).toBe(false);
    expect(hasDeckRuntime(NAV)).toBe(true);
  });
});
