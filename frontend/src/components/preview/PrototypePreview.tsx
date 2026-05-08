"use client";

import { Layout } from "lucide-react";

interface PrototypePreviewProps {
  content?: string;
  isStreaming?: boolean;
}

/**
 * Renders HTML content in a full-size iframe.
 * Used for Prototype and PPT (both generate self-contained HTML).
 */
export function PrototypePreview({ content, isStreaming }: PrototypePreviewProps) {
  if (!content) {
    return (
      <div className="flex h-full flex-col items-center justify-center px-6">
        <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-[#f0eee6] border border-[#e8e6dc] mb-4">
          <Layout className="h-7 w-7 text-[#87867f]" />
        </div>
        <p className="text-sm font-medium text-[#5e5d59] mb-1">No Preview Yet</p>
        <p className="text-xs text-[#87867f] text-center max-w-[200px]">
          Run the pipeline to generate output.
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
        <p className="text-xs text-[#87867f]">Generating...</p>
      </div>
    );
  }

  // Strip markdown code fences if present
  let htmlContent = content.trim();
  if (htmlContent.startsWith("```")) {
    htmlContent = htmlContent.replace(/^```(?:html)?\s*\n?/, "").replace(/\n?```\s*$/, "");
  }

  // Check if content is HTML
  const isHtml = htmlContent.startsWith("<!DOCTYPE") || htmlContent.startsWith("<html") || htmlContent.startsWith("<!");

  if (!isHtml) {
    return (
      <div className="p-4 h-full overflow-auto">
        <div className="rounded-xl border border-[#e8e6dc] bg-white p-4">
          <p className="text-xs text-[#87867f] mb-2">Output (text format):</p>
          <pre className="text-[11px] text-[#141413] whitespace-pre-wrap leading-relaxed overflow-auto max-h-[500px]">
            {content}
          </pre>
        </div>
      </div>
    );
  }

  // Render HTML in iframe — takes full available space
  return (
    <div className="h-full w-full">
      <iframe
        srcDoc={htmlContent}
        className="w-full h-full border-0"
        sandbox="allow-scripts allow-same-origin"
        title="Prototype Preview"
      />
    </div>
  );
}
