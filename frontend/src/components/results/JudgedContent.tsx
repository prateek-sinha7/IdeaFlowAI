"use client";

/**
 * JudgedContent — the one renderer for anything a person is asked to READ.
 *
 * Ported from `impeccable-redesign`, minus its `ScrollShade` chrome (that
 * component does not exist on this branch). The rule it carries is the point:
 * the KIND is decided by `classifyContent`, from the text's own shape (SC-001),
 * never by which panel is drawing it — so the same output reads the same way
 * in the Steps drill-down as it does in the workspace file view.
 *
 *   code      — scrolls sideways, keeps every character, drops nothing
 *   markdown  — headings, lists, tables
 *   plain     — prose, wrapped, newlines kept
 *
 * `plain` is not a fallback nobody hits: an agent's streamed reply is usually
 * prose with hard newlines, and running that through a markdown renderer eats
 * the newlines and reflows it into one run-together paragraph.
 */

import { useState } from "react";
import { Check, Copy, FileCode2 } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { classifyContent } from "@/lib/contentKind";
import { MermaidBlock, isMermaidFence } from "./MermaidBlock";

function CopyButton({ value }: { value: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={() => {
        void navigator.clipboard?.writeText(value);
        setCopied(true);
        window.setTimeout(() => setCopied(false), 1500);
      }}
      aria-label={copied ? "Copied" : "Copy to clipboard"}
      className="inline-flex items-center gap-1 rounded-[5px] px-1.5 py-0.5 text-[10.5px] text-ink-500 transition-colors hover:bg-surface-white hover:text-ink-800"
    >
      {copied ? <Check className="h-3 w-3" aria-hidden /> : <Copy className="h-3 w-3" aria-hidden />}
      {copied ? "Copied" : "Copy"}
    </button>
  );
}

export interface JudgedContentProps {
  value: string;
  /** Scroll cap in px. 0 removes the cap. */
  maxHeight?: number;
  /** Draw prose and markdown inside the warm content well. */
  framed?: boolean;
  className?: string;
  "data-testid"?: string;
}

const WELL = "rounded-[12px] border border-line-border bg-surface-warm px-4 py-3.5";

/**
 * The only override the markdown branch needs: a ```mermaid fence is a picture,
 * and showing its source instead spends a screen saying nothing. Everything
 * else keeps `markdown-content`'s own styling.
 */
const MD_COMPONENTS = {
  code: ({ className, children, ...rest }: { className?: string; children?: React.ReactNode }) => {
    if (isMermaidFence(className)) return <MermaidBlock chart={String(children ?? "")} />;
    return (
      <code className={className} {...rest}>
        {children}
      </code>
    );
  },
};

export function JudgedContent({
  value,
  maxHeight = 420,
  framed = false,
  className = "",
  "data-testid": testId,
}: JudgedContentProps) {
  const { kind, language, body } = classifyContent(value);
  const cap = maxHeight > 0 ? { maxHeight } : undefined;
  const well = framed ? WELL : "";

  // `data-content-kind` is deliberately part of the DOM: which branch ran is
  // the thing worth asserting about this component, in tests and by eye.
  const rootProps = { "data-testid": testId, "data-content-kind": kind };

  if (kind === "code") {
    return (
      <div
        {...rootProps}
        className={`overflow-hidden rounded-[12px] border border-line-border bg-surface-warm ${className}`}
      >
        <div className="flex items-center gap-2 border-b border-line-border px-3.5 py-2">
          <FileCode2 className="h-3 w-3 flex-none text-ink-400" aria-hidden />
          <span className="font-mono text-[10.5px] uppercase tracking-[0.08em] text-ink-500">
            {language ?? "text"}
          </span>
          <span className="flex-1" />
          <CopyButton value={body} />
        </div>
        {/* whitespace-pre, not pre-wrap: code is scrolled, never rewrapped.
            That is the whole reason this is a separate branch from prose. */}
        <div
          style={cap}
          className="overflow-auto whitespace-pre px-3.5 py-2.5 font-mono text-[11.5px] leading-[1.55] text-ink-700"
        >
          {body}
        </div>
      </div>
    );
  }

  if (kind === "markdown") {
    return (
      <div
        {...rootProps}
        style={cap}
        className={`markdown-content min-w-0 overflow-y-auto font-serif text-[13.5px] leading-[1.65] ${well} ${className}`}
      >
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={MD_COMPONENTS}>
          {body}
        </ReactMarkdown>
      </div>
    );
  }

  return (
    <div
      {...rootProps}
      style={cap}
      className={`min-w-0 overflow-y-auto whitespace-pre-wrap font-serif text-[13.5px] leading-[1.65] text-ink-700 ${well} ${className}`}
    >
      {body}
    </div>
  );
}
