"use client";

import { useMemo } from "react";
import { Layout, ExternalLink } from "lucide-react";

interface PrototypePreviewProps {
  content?: string;
  isStreaming?: boolean;
}

/**
 * Renders the prototype as a live HTML preview in an iframe.
 * The prototype pipeline generates a complete standalone HTML file
 * that is rendered directly in a sandboxed iframe.
 */
export function PrototypePreview({ content, isStreaming }: PrototypePreviewProps) {
  if (!content) {
    return (
      <div className="flex h-full flex-col items-center justify-center px-6">
        <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-[#f0eee6] border border-[#e8e6dc] mb-4">
          <Layout className="h-7 w-7 text-[#87867f]" />
        </div>
        <p className="text-sm font-medium text-[#5e5d59] mb-1">No Prototype Yet</p>
        <p className="text-xs text-[#87867f] text-center max-w-[200px]">
          Prototype content will appear here once generation begins.
        </p>
      </div>
    );
  }

  if (isStreaming) {
    return (
      <div className="flex h-full flex-col items-center justify-center px-6">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#f0eee6] border border-[#e8e6dc] mb-3 animate-pulse">
          <Layout className="h-5 w-5 text-[#87867f]" />
        </div>
        <p className="text-xs text-[#87867f]">Generating prototype...</p>
      </div>
    );
  }

  // Check if content is HTML (starts with <!DOCTYPE or <html)
  // Also handle case where HTML is wrapped in markdown code fences
  let htmlContent = content.trim();
  
  // Strip markdown code fences if present
  if (htmlContent.startsWith("```")) {
    htmlContent = htmlContent.replace(/^```(?:html)?\s*\n?/, "").replace(/\n?```\s*$/, "");
  }
  
  const isHtml = htmlContent.startsWith("<!DOCTYPE") || htmlContent.startsWith("<html") || htmlContent.startsWith("<!");
  
  if (!isHtml) {
    // Fallback: render as markdown/text if not HTML
    return (
      <div className="p-4">
        <div className="rounded-xl border border-[#e8e6dc] bg-white p-4">
          <p className="text-xs text-[#87867f] mb-2">Prototype output (text format):</p>
          <pre className="text-[11px] text-[#141413] whitespace-pre-wrap leading-relaxed overflow-auto max-h-[500px]">
            {content}
          </pre>
        </div>
      </div>
    );
  }

  // Render HTML in a sandboxed iframe
  const iframeSrcDoc = htmlContent;

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-[#e8e6dc] bg-white flex-shrink-0">
        <div className="flex items-center gap-2">
          <Layout className="h-3.5 w-3.5 text-[#87867f]" />
          <span className="text-[11px] font-medium text-[#5e5d59]">Live Preview</span>
        </div>
        <button
          onClick={() => {
            const blob = new Blob([htmlContent], { type: "text/html" });
            const url = URL.createObjectURL(blob);
            window.open(url, "_blank");
            setTimeout(() => URL.revokeObjectURL(url), 1000);
          }}
          className="flex items-center gap-1 text-[10px] text-[#87867f] hover:text-[#141413] transition-colors"
          title="Open in new tab"
        >
          <ExternalLink className="h-3 w-3" />
          Open in new tab
        </button>
      </div>

      {/* Iframe */}
      <div className="flex-1 min-h-0 bg-white">
        <iframe
          srcDoc={iframeSrcDoc}
          className="w-full h-full border-0"
          sandbox="allow-scripts allow-same-origin"
          title="Prototype Preview"
        />
      </div>
    </div>
  );
}
