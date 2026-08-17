"use client";

import { useState, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { FileText, Copy, Check, ChevronRight, ChevronDown, RefreshCw } from "lucide-react";

// ─── WR-03 (18 review) — raw-HTML escaping is a SECURITY invariant ────────────
// MarkdownPreview is the generic deliverable `text/markdown` render path
// (PreviewPanel.GenericDeliverablePreview + the history reopen surface). It MUST
// NOT execute embedded raw HTML: a custom workflow could mis-declare
// `text/markdown` for an HTML payload (or embed `<script>` in a markdown
// deliverable), and an UNsandboxed HTML render here would defeat the iframe
// sandbox (T-18-05) the `text/html` path enforces. This is upheld structurally
// by react-markdown's DEFAULT behavior: NO `rehype-raw` (and no rehypePlugins of
// any kind) is configured below, so raw HTML is escaped to literal text rather
// than parsed into live DOM. DO NOT add `rehype-raw` here without routing the
// result through the same `sandbox="allow-scripts"` iframe the HTML path uses.
interface MarkdownPreviewProps {
  content?: string;
  onRevise?: (instruction: string) => void;
}

export function MarkdownPreview({ content, onRevise }: MarkdownPreviewProps) {
  const [copied, setCopied] = useState(false);
  const [collapsedSections, setCollapsedSections] = useState<Set<string>>(new Set());
  const [revisionText, setRevisionText] = useState("");

  const toggleSection = useCallback((id: string) => {
    setCollapsedSections((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }, []);

  if (!content) {
    return (
      <div className="flex h-full flex-col items-center justify-center px-6">
        <div className="flex h-14 w-14 items-center justify-center rounded-lg bg-surface-warm border border-line-control mb-4">
          <FileText className="h-7 w-7 text-ink-400" />
        </div>
        <p className="text-sm font-medium text-ink-600">No Output Yet</p>
        <p className="text-[11px] text-ink-400 mt-1">Run the pipeline to generate output</p>
      </div>
    );
  }

  const handleCopyAll = () => {
    navigator.clipboard.writeText(content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-line-divider bg-surface-white flex-shrink-0">
        <div className="flex items-center gap-2">
          <FileText className="h-3.5 w-3.5 text-brand" />
          <span className="text-[11px] font-semibold text-ink-900">Output</span>
        </div>
        <button onClick={handleCopyAll} className="flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-[10px] font-medium text-ink-500 hover:text-ink-900 hover:bg-surface-warm border border-line-control transition-all">
          {copied ? <><Check className="h-3 w-3 text-status-done" /><span className="text-status-done">Copied!</span></> : <><Copy className="h-3 w-3" /><span>Copy All</span></>}
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-6 py-5">        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            h1: ({ children }) => {
              const id = String(children).slice(0, 30);
              const isCollapsed = collapsedSections.has(id);
              return (
                <div className="mt-6 first:mt-0">
                  <button onClick={() => toggleSection(id)} className="flex items-center gap-2 w-full text-left group">
                    {isCollapsed ? <ChevronRight className="h-4 w-4 text-ink-400 group-hover:text-brand" /> : <ChevronDown className="h-4 w-4 text-ink-400 group-hover:text-brand" />}
                    <h1 className="text-[17px] font-bold text-ink-900 pb-1 border-b-2 border-brand-border flex-1">{children}</h1>
                  </button>
                </div>
              );
            },
            h2: ({ children }) => (
              <h2 className="text-[14px] font-bold text-ink-900 mt-5 mb-2 pb-1 border-b border-line-divider">{children}</h2>
            ),
            h3: ({ children }) => (
              <h3 className="text-[13px] font-semibold text-ink-900 mt-4 mb-1">{children}</h3>
            ),
            p: ({ children }) => (
              <p className="text-[12.5px] text-ink-700 leading-[1.6] mb-2">{children}</p>
            ),
            ul: ({ children }) => <ul className="my-1 pl-4 space-y-0.5">{children}</ul>,
            ol: ({ children }) => <ol className="my-1 pl-4 space-y-0.5 list-decimal">{children}</ol>,
            li: ({ children }) => (
              <li className="text-[12.5px] text-ink-700 leading-[1.6] marker:text-brand">{children}</li>
            ),
            code: ({ className, children, ...props }) => {
              const isBlock = className?.includes("language-") || String(children).includes("\n");
              if (isBlock) {
                const lang = className?.replace("language-", "") || "";
                const codeStr = String(children).replace(/\n$/, "");
                return <CodeBlock code={codeStr} language={lang} />;
              }
              return (
                <code className="text-[12px] bg-brand-fill text-brand px-1.5 py-0.5 rounded font-mono border border-brand-border" {...props}>{children}</code>
              );
            },
            pre: ({ children }) => <>{children}</>,
            table: ({ children }) => (
              <div className="overflow-x-auto my-3 rounded-lg border border-line-divider">
                <table className="w-full text-[12px] border-collapse">{children}</table>
              </div>
            ),
            thead: ({ children }) => <thead className="bg-surface-warm">{children}</thead>,
            th: ({ children }) => <th className="px-3 py-2 text-left font-semibold text-ink-900 border-b border-line-divider">{children}</th>,
            td: ({ children }) => <td className="px-3 py-2 text-ink-700 border-b border-line-faint-row">{children}</td>,
            tr: ({ children }) => <tr className="hover:bg-surface-warm transition-colors">{children}</tr>,
            hr: () => <hr className="my-4 border-line-divider" />,
            strong: ({ children }) => <strong className="font-semibold text-ink-900">{children}</strong>,
            em: ({ children }) => <em className="italic text-ink-600">{children}</em>,
            blockquote: ({ children }) => (
              <blockquote className="border-l-[3px] border-brand pl-3 my-2 text-ink-600 italic">{children}</blockquote>
            ),
            a: ({ href, children }) => (
              <a href={href} target="_blank" rel="noopener noreferrer" className="text-brand underline hover:text-brand-pressed">{children}</a>
            ),
          }}
        >
          {content}
        </ReactMarkdown>
      </div>

      {/* Revision bar */}
      {onRevise && (
        <div className="flex-shrink-0 border-t border-line-divider bg-surface-white px-4 py-3 flex items-center gap-3">
          <input
            type="text"
            value={revisionText}
            onChange={(e) => setRevisionText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && revisionText.trim()) {
                onRevise(revisionText.trim());
                setRevisionText("");
              }
            }}
            placeholder='Request changes, e.g. "Add Stripe payment integration" or "Add a user roles system"'
            className="flex-1 text-[12px] text-ink-700 placeholder-ink-400 bg-surface-warm border border-line-control rounded-lg px-3 py-2 focus:outline-none focus:border-ink-400 transition-colors"
          />
          <button
            onClick={() => {
              if (revisionText.trim()) {
                onRevise(revisionText.trim());
                setRevisionText("");
              }
            }}
            disabled={!revisionText.trim()}
            className="flex items-center gap-1.5 text-[11px] font-medium text-white bg-brand hover:bg-brand-pressed disabled:opacity-40 rounded-lg px-3 py-2 transition-colors flex-shrink-0"
          >
            <RefreshCw className="h-3.5 w-3.5" /> Revise
          </button>
        </div>
      )}
    </div>
  );
}

/* --- Code Block Component with Copy --- */
function CodeBlock({ code, language }: { code: string; language: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Detect if it's a filename-style header
  const isFilename = language.includes("/") || language.includes(".");

  return (
    <div className="my-2 rounded-lg border border-[#3d4450] overflow-hidden group">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-1.5 bg-[#21252b] border-b border-[#3d4450]">
        <span className="text-[11px] font-mono text-[#9da5b4]">
          {isFilename ? `📄 ${language}` : language || "code"}
        </span>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1 text-[10px] text-[#9da5b4] hover:text-white opacity-0 group-hover:opacity-100 transition-opacity"
        >
          {copied ? <><Check className="h-3 w-3 text-emerald-400" /> Copied</> : <><Copy className="h-3 w-3" /> Copy</>}
        </button>
      </div>
      {/* Code */}
      <pre className="px-4 py-3 overflow-x-auto bg-[#282c34] m-0 border-0">
        <code className="text-[13px] leading-[1.4] font-mono text-[#abb2bf] whitespace-pre">{code}</code>
      </pre>
    </div>
  );
}
