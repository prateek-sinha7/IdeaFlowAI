import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";

import { MarkdownPreview } from "./MarkdownPreview";

// ─── WR-03 (18 review) — raw-HTML escaping is a SECURITY invariant ────────────
// MarkdownPreview is the generic deliverable `text/markdown` render path. It MUST
// escape embedded raw HTML (no rehype-raw) so a custom workflow that mis-declares
// `text/markdown` for an HTML payload — or embeds `<script>` in a markdown
// deliverable — cannot get an UNsandboxed HTML render that defeats the iframe
// sandbox the `text/html` path enforces (T-18-05). This locks that invariant.
describe("MarkdownPreview — raw HTML is escaped, never executed (WR-03)", () => {
  it("does NOT inject a raw <script> element from markdown content", () => {
    const { container } = render(
      <MarkdownPreview content={"# Title\n\n<script>window.__pwned = true;</script>\n"} />,
    );
    // react-markdown's default (no rehype-raw) escapes the tag to text — no live
    // <script> node is parsed into the DOM.
    expect(container.querySelector("script")).toBeNull();
  });

  it("does NOT render a raw <iframe>/<img onerror> as a live element", () => {
    const { container } = render(
      <MarkdownPreview
        content={'<iframe src="javascript:alert(1)"></iframe>\n<img src=x onerror="alert(1)">'}
      />,
    );
    expect(container.querySelector("iframe")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
  });
});
