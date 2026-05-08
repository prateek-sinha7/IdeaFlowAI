"use client";

import { useState, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { FileText, Copy, Check, ChevronRight, ChevronDown } from "lucide-react";

interface MarkdownPreviewProps {
  content?: string;
}

export function MarkdownPreview({ content }: MarkdownPreviewProps) {
  const [copied, setCopied] = useState(false);
  const [collapsedSections, setCollapsedSections] = useState<Set<string>>(new Set());

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
        <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-[#f0eee6] to-[#e8e6dc] border border-[#e8e6dc] mb-4">
          <FileText className="h-7 w-7 text-[#87867f]" />
        </div>
        <p className="text-sm font-medium text-[#5e5d59]">No Output Yet</p>
        <p className="text-[11px] text-[#87867f] mt-1">Run the pipeline to generate output</p>
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
      <div className="flex items-center justify-between px-4 py-2 border-b border-[#e8e6dc] bg-white flex-shrink-0">
        <div className="flex items-center gap-2">
          <FileText className="h-3.5 w-3.5 text-[#c96442]" />
          <span className="text-[11px] font-semibold text-[#141413]">Output</span>
        </div>
        <button onClick={handleCopyAll} className="flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-[10px] font-medium text-[#5e5d59] hover:text-[#141413] hover:bg-[#f0eee6] border border-[#e8e6dc] transition-all">
          {copied ? <><Check className="h-3 w-3 text-emerald-600" /><span className="text-emerald-600">Copied!</span></> : <><Copy className="h-3 w-3" /><span>Copy All</span></>}
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-6 py-5">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            h1: ({ children }) => {
              const id = String(children).slice(0, 30);
              const isCollapsed = collapsedSections.has(id);
              return (
                <div className="mt-6 first:mt-0">
                  <button onClick={() => toggleSection(id)} className="flex items-center gap-2 w-full text-left group">
                    {isCollapsed ? <ChevronRight className="h-4 w-4 text-[#87867f] group-hover:text-[#c96442]" /> : <ChevronDown className="h-4 w-4 text-[#87867f] group-hover:text-[#c96442]" />}
                    <h1 className="text-[17px] font-bold text-[#141413] pb-1 border-b-2 border-[#c96442]/20 flex-1">{children}</h1>
                  </button>
                </div>
              );
            },
            h2: ({ children }) => (
              <h2 className="text-[14px] font-bold text-[#141413] mt-5 mb-2 pb-1 border-b border-[#e8e6dc]">{children}</h2>
            ),
            h3: ({ children }) => (
              <h3 className="text-[13px] font-semibold text-[#141413] mt-4 mb-1">{children}</h3>
            ),
            p: ({ children }) => (
              <p className="text-[12.5px] text-[#3d3d3a] leading-[1.6] mb-2">{children}</p>
            ),
            ul: ({ children }) => <ul className="my-1 pl-4 space-y-0.5">{children}</ul>,
            ol: ({ children }) => <ol className="my-1 pl-4 space-y-0.5 list-decimal">{children}</ol>,
            li: ({ children }) => (
              <li className="text-[12.5px] text-[#3d3d3a] leading-[1.6] marker:text-[#c96442]">{children}</li>
            ),
            code: ({ className, children, ...props }) => {
              const isBlock = className?.includes("language-") || String(children).includes("\n");
              if (isBlock) {
                const lang = className?.replace("language-", "") || "";
                const codeStr = String(children).replace(/\n$/, "");
                return <CodeBlock code={codeStr} language={lang} />;
              }
              return (
                <code className="text-[12px] bg-[#eff1f3] text-[#c96442] px-1.5 py-0.5 rounded font-mono" {...props}>{children}</code>
              );
            },
            pre: ({ children }) => <>{children}</>,
            table: ({ children }) => (
              <div className="overflow-x-auto my-3 rounded-lg border border-[#d1d5db]">
                <table className="w-full text-[12px] border-collapse">{children}</table>
              </div>
            ),
            thead: ({ children }) => <thead className="bg-[#f6f8fa]">{children}</thead>,
            th: ({ children }) => <th className="px-3 py-2 text-left font-semibold text-[#1f2328] border-b border-[#d1d5db]">{children}</th>,
            td: ({ children }) => <td className="px-3 py-2 text-[#3d3d3a] border-b border-[#e8e6dc]">{children}</td>,
            tr: ({ children }) => <tr className="hover:bg-[#f6f8fa] transition-colors">{children}</tr>,
            hr: () => <hr className="my-4 border-[#e8e6dc]" />,
            strong: ({ children }) => <strong className="font-semibold text-[#141413]">{children}</strong>,
            em: ({ children }) => <em className="italic text-[#5e5d59]">{children}</em>,
            blockquote: ({ children }) => (
              <blockquote className="border-l-3 border-[#c96442] pl-3 my-2 text-[#5e5d59] italic">{children}</blockquote>
            ),
            a: ({ href, children }) => (
              <a href={href} target="_blank" rel="noopener noreferrer" className="text-[#c96442] underline hover:text-[#b5573a]">{children}</a>
            ),
          }}
        >
          {content}
        </ReactMarkdown>
      </div>
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
