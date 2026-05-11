"use client";

import { useState } from "react";
import { Layout, ExternalLink, RefreshCw } from "lucide-react";

interface PrototypePreviewProps {
  content?: string;
  isStreaming?: boolean;
  onRevise?: (instruction: string) => void;
}

/**
 * Renders the prototype HTML in a browser-chrome mockup.
 * Gives the preview a professional "live app" feel.
 */
export function PrototypePreview({ content, isStreaming, onRevise }: PrototypePreviewProps) {
  const [iframeKey] = useState(0);
  const [revisionText, setRevisionText] = useState("");

  if (!content) {
    return (
      <div className="flex h-full flex-col items-center justify-center px-6">
        <div className="flex h-14 w-14 items-center justify-center rounded-lg bg-gray-100 border border-gray-200 mb-4">
          <Layout className="h-7 w-7 text-gray-400" />
        </div>
        <p className="text-sm font-medium text-gray-600 mb-1">No Preview Yet</p>
        <p className="text-xs text-gray-400 text-center max-w-[200px]">
          Run the pipeline to generate your prototype.
        </p>
      </div>
    );
  }

  if (isStreaming) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3">
        <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-gray-100 border border-gray-200 animate-pulse">
          <Layout className="h-6 w-6 text-gray-400" />
        </div>
        <p className="text-[11px] text-gray-500 font-medium">Building prototype...</p>
      </div>
    );
  }

  // Strip markdown code fences if present
  let htmlContent = content.trim();
  if (htmlContent.startsWith("```")) {
    htmlContent = htmlContent.replace(/^```(?:html)?\s*\n?/, "").replace(/\n?```\s*$/, "");
  }

  const isHtml = htmlContent.startsWith("<!DOCTYPE") || htmlContent.startsWith("<html") || htmlContent.startsWith("<!");

  if (!isHtml) {
    return (
      <div className="p-4 h-full overflow-auto">
        <div className="rounded-lg border border-gray-200 bg-white p-4">
          <p className="text-xs text-gray-400 mb-2">Output (text format):</p>
          <pre className="text-[11px] text-gray-900 whitespace-pre-wrap leading-relaxed overflow-auto max-h-[500px]">
            {content}
          </pre>
        </div>
      </div>
    );
  }

  const handleOpenInNewTab = () => {
    const blob = new Blob([htmlContent], { type: "text/html" });
    const url = URL.createObjectURL(blob);
    window.open(url, "_blank");
    setTimeout(() => URL.revokeObjectURL(url), 5000);
  };

  return (
    <div className="h-full flex flex-col" style={{ background: "#f5f5f0" }}>
      {/* Browser chrome */}
      <div className="flex-shrink-0 bg-white border-b border-gray-200 px-4 py-2.5 flex items-center gap-3">
        {/* Traffic lights */}
        <div className="flex items-center gap-1.5">
          <div className="w-3 h-3 rounded-full bg-gray-200" />
          <div className="w-3 h-3 rounded-full bg-gray-200" />
          <div className="w-3 h-3 rounded-full bg-gray-200" />
        </div>
        {/* URL bar */}
        <div className="flex-1 flex items-center gap-2 bg-gray-100 rounded-md px-3 py-1.5 max-w-sm">
          <div className="w-2 h-2 rounded-full bg-emerald-400 flex-shrink-0" />
          <span className="text-[11px] text-gray-500 font-mono truncate">localhost:3000 / dashboard</span>
        </div>
        {/* Open in new tab */}
        <button
          onClick={handleOpenInNewTab}
          className="flex items-center gap-1.5 text-[10px] text-gray-400 hover:text-gray-700 transition-colors ml-auto"
          title="Open in new tab"
        >
          <ExternalLink className="h-3.5 w-3.5" />
          <span>Open</span>
        </button>
      </div>

      {/* Prototype iframe */}
      <div className="flex-1 min-h-0">
        <iframe
          key={iframeKey}
          srcDoc={htmlContent}
          className="w-full h-full border-0"
          /* `allow-same-origin` + `allow-scripts` neuters the sandbox; the
             iframe could read parent localStorage (incl. JWT) and call
             same-origin APIs. The prototype HTML is LLM-generated and
             must be treated as untrusted. allow-scripts alone keeps
             the prototype interactive (button clicks, form state) without
             leaking origin authority. */
          sandbox="allow-scripts"
          title="Prototype Preview"
        />
      </div>

      {/* Revision bar */}
      {onRevise && (
        <div className="flex-shrink-0 border-t border-gray-200 bg-white px-4 py-3 flex items-center gap-3">
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
            placeholder='Request changes, e.g. "Add a Reports page" or "Change the dashboard stats"'
            className="flex-1 text-[12px] text-gray-700 placeholder-gray-400 bg-gray-50 border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:border-gray-400 transition-colors"
          />
          <button
            onClick={() => {
              if (revisionText.trim()) {
                onRevise(revisionText.trim());
                setRevisionText("");
              }
            }}
            disabled={!revisionText.trim()}
            className="flex items-center gap-1.5 text-[11px] font-medium text-white bg-[#1B2A4A] hover:bg-[#2a3d5e] disabled:opacity-40 rounded-lg px-3 py-2 transition-colors flex-shrink-0"
          >
            <RefreshCw className="h-3.5 w-3.5" /> Revise
          </button>
        </div>
      )}
    </div>
  );
}
