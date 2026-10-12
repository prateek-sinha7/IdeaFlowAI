"use client";

/**
 * MermaidBlock — a ```mermaid fence, drawn.
 *
 * A design document's most useful pages are the ones that are shapes rather
 * than sentences: which screen leads to which, what a screen's states are. In
 * markdown those are mermaid fences, and a markdown renderer with no mermaid in
 * it shows the SOURCE — `flowchart TD` and a list of arrows — which is strictly
 * worse than no diagram at all, because it takes a screen's worth of space to
 * say nothing.
 *
 * The library is loaded on demand: it is large, most files carry no diagram,
 * and nothing here should cost anything on a run that never opens one.
 *
 * A diagram that fails to parse renders as its own source in a code block. An
 * agent writing a design document is the author here, and an author's typo
 * must be visible and fixable, never swallowed into a blank box.
 */

import { useEffect, useRef, useState } from "react";

/** One id per rendered diagram — mermaid uses it for its internal <defs>. */
let seq = 0;

export function MermaidBlock({ chart }: { chart: string }) {
  const host = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const dark = document.documentElement.getAttribute("data-theme") === "dark";

    seq += 1;
    const id = `mermaid-${seq}`;

    void (async () => {
      try {
        const mermaid = (await import("mermaid")).default;
        mermaid.initialize({
          startOnLoad: false,
          securityLevel: "strict",
          // `neutral` reads as part of the product in light mode; `dark` is the
          // only built-in that keeps its own labels legible on a dark ground.
          theme: dark ? "dark" : "neutral",
          fontFamily: "var(--font-sans, system-ui), sans-serif",
        });
        const { svg } = await mermaid.render(id, chart.trim());
        if (cancelled || !host.current) return;
        host.current.innerHTML = svg;
        setError(null);
      } catch (e) {
        // A failed render leaves mermaid's "Syntax error in text" graphic in a
        // container it appended to <body> (`d<id>`) and never removes. In an SPA
        // those pile up above every later page — remove them; the error box
        // below is what this block shows instead.
        document.getElementById(`d${id}`)?.remove();
        document.getElementById(id)?.remove();
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [chart]);

  if (error) {
    return (
      <div
        data-testid="mermaid-error"
        className="my-3 overflow-hidden rounded-[10px] border border-line-border bg-surface-warm"
      >
        <p className="border-b border-line-border px-3 py-1.5 font-mono text-[10.5px] uppercase tracking-[0.08em] text-ink-500">
          mermaid — could not be drawn
        </p>
        <pre className="overflow-auto whitespace-pre px-3 py-2 font-mono text-[11.5px] leading-[1.55] text-ink-700">
          {chart}
        </pre>
      </div>
    );
  }

  return (
    <div
      ref={host}
      data-testid="mermaid-diagram"
      // Wide graphs scroll rather than shrinking their own labels to nothing.
      className="my-3 overflow-x-auto rounded-[10px] border border-line-border bg-surface-warm px-3 py-3 [&_svg]:mx-auto [&_svg]:h-auto [&_svg]:max-w-none"
    />
  );
}

/** `language-mermaid` on a fenced block, as react-markdown hands it over. */
export function isMermaidFence(className?: string): boolean {
  return /(^|\s)language-mermaid(\s|$)/.test(className ?? "");
}
