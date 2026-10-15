/**
 * The one place that decides how agent-authored HTML is framed or opened
 * (ISS-1067).
 *
 * Agents write this HTML from prompts and uploaded documents, so it is untrusted,
 * and it must never run on the app origin, where `auth_token` sits in
 * localStorage:
 *
 * - `allow-scripts` with `allow-same-origin` on same-origin content lets the
 *   script read the origin's storage and lift its own sandbox. srcdoc content is
 *   same-origin, and so is a `blob:` URL: a blob carries its creator's origin.
 *   Commit 5db19e6db removed the token; 77228e567 and d2970ff7f put it back.
 * - `window.open(blob:)` gives a top-level document on the app origin with no
 *   sandbox at all, and a `<meta>` CSP sandbox is ignored there.
 *
 * Measured in Chrome: evidence/qa-kb-125/analysis-1..4.
 */

/** The only sandbox agent HTML gets. Never add `allow-same-origin`. */
export const AGENT_HTML_SANDBOX = "allow-scripts";

const SRCDOC_BASE = '<base href="about:srcdoc">';

/**
 * Agent HTML ready for `<iframe srcDoc sandbox={AGENT_HTML_SANDBOX}>`.
 *
 * A srcdoc document resolves URLs against the parent's URL, so `<a href="#x">`
 * loads the app into the frame and `history.replaceState` throws. A base of
 * `about:srcdoc`, first in `<head>`, keeps fragment links, `location.hash`,
 * `hashchange` and the History API inside the document (ISS-1162). Relative and
 * protocol-relative URLs stop resolving, as they did in the blob frame.
 */
export function frameableAgentHtml(html: string): string {
  if (html.includes(SRCDOC_BASE)) return html;
  const m =
    /<head(?:\s[^>]*)?>/i.exec(html) ??
    /<html(?:\s[^>]*)?>/i.exec(html) ??
    /<!doctype[^>]*>/i.exec(html);
  if (!m) return SRCDOC_BASE + html;
  const at = m.index + m[0].length;
  return html.slice(0, at) + SRCDOC_BASE + html.slice(at);
}

/**
 * Open agent HTML in a new tab without the app origin: a script-free wrapper
 * page whose only content is the sandboxed srcdoc frame, opened `noopener`
 * (evidence/qa-kb-125/analysis-3, variant G2).
 */
export function openAgentHtmlInNewTab(html: string): void {
  const srcdoc = frameableAgentHtml(html).replace(/&/g, "&amp;").replace(/"/g, "&quot;");
  const page =
    '<!DOCTYPE html><html><head><meta charset="utf-8"><title>Preview</title>' +
    "<style>html,body{margin:0;height:100%}iframe{display:block;border:0;width:100%;height:100%}</style>" +
    `</head><body><iframe sandbox="${AGENT_HTML_SANDBOX}" srcdoc="${srcdoc}"></iframe></body></html>`;
  const url = URL.createObjectURL(new Blob([page], { type: "text/html" }));
  window.open(url, "_blank", "noopener,noreferrer");
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}
