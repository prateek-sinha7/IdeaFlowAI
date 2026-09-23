/**
 * One fix-up every HTML deck needs before it is rendered in an iframe.
 *
 * Every `design-templates/html-ppt-*` example.html ends its `<head>` with a
 * style block commented "Static-preview fallback (runtime.js is absent — keep
 * every slide visible)", which sets:
 *
 *     .deck  { height:auto; min-height:100vh; overflow:visible }
 *     .slide { position:relative; inset:auto; opacity:1; transform:none; height:100vh }
 *
 * For an example.html — a static file with no script — that is correct. A
 * GENERATED deck inlines the template's CSS *and* a navigation script, and then
 * the block wins on source order at equal specificity: every slide sits in the
 * document flow at full opacity, so toggling `.is-active` moves nothing. `go()`
 * still runs and still rewrites `.slide-number` — which is exactly how the bug
 * was reported: the counter advances and the deck does not.
 *
 * Removal is conditional on a runtime actually being present, so a genuinely
 * static deck keeps its fallback rather than collapsing to slide one.
 *
 * The upstream fix is in `ppt-composer`'s prompt, which is now told to drop the
 * block. This is the deterministic backstop, and it repairs the decks already
 * written to disk.
 */

/** True when the deck carries its own slide-navigation script. */
export function hasDeckRuntime(html: string): boolean {
  return /<script[^>]*>[\s\S]*?is-active[\s\S]*?<\/script>/i.test(html);
}

/** Drop the static-preview fallback style block — only when a runtime is present. */
export function stripStaticPreviewFallback(html: string): string {
  if (!hasDeckRuntime(html)) return html;
  return html.replace(
    /<style[^>]*>\s*\/\*\s*Static-preview fallback[\s\S]*?<\/style>/gi,
    "",
  );
}
