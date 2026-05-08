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
        <div className="flex h-14 w-14 items-center justify-center rounded-lg bg-gray-100 border border-gray-200 mb-4">
          <FileText className="h-7 w-7 text-gray-400" />
        </div>
        <p className="text-sm font-medium text-gray-600">No Output Yet</p>
        <p className="text-[11px] text-gray-400 mt-1">Run the pipeline to generate output</p>
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
      <div className="flex items-center justify-between px-4 py-2 border-b border-gray-200 bg-white flex-shrink-0">
        <div className="flex items-center gap-2">
          <FileText className="h-3.5 w-3.5 text-blue-600" />
          <span className="text-[11px] font-semibold text-gray-900">Output</span>
        </div>
        <button onClick={handleCopyAll} className="flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-[10px] font-medium text-gray-500 hover:text-gray-900 hover:bg-gray-100 border border-gray-200 transition-all">
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
                    {isCollapsed ? <ChevronRight className="h-4 w-4 text-gray-400 group-hover:text-blue-600" /> : <ChevronDown className="h-4 w-4 text-gray-400 group-hover:text-blue-600" />}
                    <h1 className="text-[17px] font-bold text-gray-900 pb-1 border-b-2 border-blue-200 flex-1">{children}</h1>
                  </button>
                </div>
              );
            },
            h2: ({ children }) => (
              <h2 className="text-[14px] font-bold text-gray-900 mt-5 mb-2 pb-1 border-b border-gray-200">{children}</h2>
            ),
            h3: ({ children }) => (
              <h3 className="text-[13px] font-semibold text-gray-900 mt-4 mb-1">{children}</h3>
            ),
            p: ({ children }) => (
              <p className="text-[12.5px] text-gray-700 leading-[1.6] mb-2">{children}</p>
            ),
            ul: ({ children }) => <ul className="my-1 pl-4 space-y-0.5">{children}</ul>,
            ol: ({ children }) => <ol className="my-1 pl-4 space-y-0.5 list-decimal">{children}</ol>,
            li: ({ children }) => (
              <li className="text-[12.5px] text-gray-700 leading-[1.6] marker:text-blue-500">{children}</li>
            ),
            code: ({ className, children, ...props }) => {
              const isBlock = className?.includes("language-") || String(children).includes("\n");
              if (isBlock) {
                const lang = className?.replace("language-", "") || "";
                const codeStr = String(children).replace(/\n$/, "");
                return <CodeBlock code={codeStr} language={lang} />;
              }
              return (
                <code className="text-[12px] bg-blue-50 text-blue-700 px-1.5 py-0.5 rounded font-mono border border-blue-100" {...props}>{children}</code>
              );
            },
            pre: ({ children }) => <>{children}</>,
            table: ({ children }) => (
              <div className="overflow-x-auto my-3 rounded-lg border border-gray-200">
                <table className="w-full text-[12px] border-collapse">{children}</table>
              </div>
            ),
            thead: ({ children }) => <thead className="bg-gray-50">{children}</thead>,
            th: ({ children }) => <th className="px-3 py-2 text-left font-semibold text-gray-900 border-b border-gray-200">{children}</th>,
            td: ({ children }) => <td className="px-3 py-2 text-gray-700 border-b border-gray-100">{children}</td>,
            tr: ({ children }) => <tr className="hover:bg-gray-50 transition-colors">{children}</tr>,
            hr: () => <hr className="my-4 border-gray-200" />,
            strong: ({ children }) => <strong className="font-semibold text-gray-900">{children}</strong>,
            em: ({ children }) => <em className="italic text-gray-600">{children}</em>,
            blockquote: ({ children }) => (
              <blockquote className="border-l-[3px] border-blue-500 pl-3 my-2 text-gray-600 italic">{children}</blockquote>
            ),
            a: ({ href, children }) => (
              <a href={href} target="_blank" rel="noopener noreferrer" className="text-blue-600 underline hover:text-blue-700">{children}</a>
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
