"use client";

import { useState } from "react";
import { Presentation, ExternalLink, Download } from "lucide-react";

interface PPTPreviewProps {
  content?: string;
  isStreaming?: boolean;
}

/**
 * PPT Preview — renders Claude's generated HTML slide deck.
 * Claude controls all presentation content, styling, and PPTX export.
 * Our app just renders it in an iframe.
 */
export function PPTPreview({ content, isStreaming }: PPTPreviewProps) {
  const [iframeKey] = useState(0);

  if (!content) {
    return (
      <div className="flex h-full flex-col items-center justify-center px-6">
        <div className="flex h-14 w-14 items-center justify-center rounded-lg bg-gray-100 border border-gray-200 mb-4">
          <Presentation className="h-7 w-7 text-gray-400" />
        </div>
        <p className="text-sm font-medium text-gray-600 mb-1">No Slides Yet</p>
        <p className="text-xs text-gray-400 text-center max-w-[200px]">
          Run the pipeline to generate your presentation.
        </p>
      </div>
    );
  }

  if (isStreaming) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3">
        <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-gray-100 border border-gray-200 animate-pulse">
          <Presentation className="h-6 w-6 text-gray-400" />
        </div>
        <p className="text-[11px] text-gray-500 font-medium">Generating slides...</p>
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
      <div className="flex h-full items-center justify-center p-4">
        <div className="rounded-xl border border-red-200 bg-red-50 p-5 text-center max-w-sm">
          <Presentation className="h-7 w-7 text-red-400 mx-auto mb-3" />
          <p className="text-xs font-semibold text-red-800">Invalid presentation output</p>
          <p className="text-[10px] text-red-600 mt-2">The output is not valid HTML. Try running the pipeline again.</p>
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

  const handleDownloadHtml = () => {
    const blob = new Blob([htmlContent], { type: "text/html" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "presentation.html";
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="h-full flex flex-col">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-3 py-1.5 border-b border-gray-200 bg-white flex-shrink-0">
        <span className="text-[10px] text-gray-400">Use navigation inside the slide viewer · Click PPTX button to download</span>
        <div className="flex items-center gap-2">
          <button
            onClick={handleDownloadHtml}
            className="flex items-center gap-1 text-[10px] text-gray-500 hover:text-gray-900 bg-gray-100 hover:bg-gray-200 rounded-md px-2 py-1 transition-colors"
          >
            <Download className="h-3 w-3" /> HTML
          </button>
          <button
            onClick={handleOpenInNewTab}
            className="flex items-center gap-1 text-[10px] text-gray-500 hover:text-gray-900 bg-gray-100 hover:bg-gray-200 rounded-md px-2 py-1 transition-colors"
          >
            <ExternalLink className="h-3 w-3" /> Full Screen
          </button>
        </div>
      </div>

      {/* Iframe — Claude's HTML rendered as-is */}
      <div className="flex-1 min-h-0">
        <iframe
          key={iframeKey}
          srcDoc={htmlContent}
          className="w-full h-full border-0"
          title="Slide Deck Preview"
        />
      </div>
    </div>
  );
}
