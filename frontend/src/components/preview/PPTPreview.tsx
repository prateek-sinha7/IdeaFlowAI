"use client";

import { useState } from "react";
import { Presentation } from "lucide-react";

interface PPTPreviewProps {
  content?: string;
  isStreaming?: boolean;
}

/**
 * PPT Preview — renders the generated HTML slide deck.
 * 
 * The pipeline generates a self-contained HTML file that includes:
 * - Slide previews (white bg, black text, navy blue accents)
 * - Built-in navigation (arrows in top bar)
 * - PptxGenJS-powered "Download PPTX" button (inside the HTML)
 * 
 * We render it full-bleed in an iframe — the HTML handles everything.
 * We only add a minimal floating action bar for external actions (open in new tab).
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

  return (
    <div className="h-full flex flex-col">
      {/* Full-bleed iframe — the HTML handles navigation, download, and full screen */}
      <div className="flex-1 min-h-0">
        <iframe
          key={iframeKey}
          srcDoc={htmlContent}
          className="w-full h-full border-0"
          title="Slide Deck Preview"
          sandbox="allow-scripts allow-same-origin allow-downloads allow-popups allow-popups-to-escape-sandbox"
        />
      </div>
    </div>
  );
}
