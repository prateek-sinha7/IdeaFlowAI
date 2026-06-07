"use client";

import { useState } from "react";
import { Presentation, RefreshCw } from "lucide-react";
import { getToken } from "@/lib/api";
import { ENV } from "@/lib/env";

interface PPTPreviewProps {
  content?: string;
  isStreaming?: boolean;
  /** Agent 3's raw PptxGenJS code — enables reliable server-side export (ppt pipeline only) */
  pptxCode?: string;
  /** Callback to trigger a revision pipeline run */
  onRevise?: (instruction: string) => void;
  /** Pipeline type — od_ppt shows HTML download instead of PPTX */
  pipelineType?: string;
}

export function PPTPreview({ content, isStreaming, pptxCode, onRevise, pipelineType }: PPTPreviewProps) {
  const [iframeKey] = useState(0);
  const [isDownloading, setIsDownloading] = useState(false);
  const [revisionText, setRevisionText] = useState("");

  const isOdPpt = pipelineType === "od_ppt";

  const handleDownloadHtml = () => {
    if (!content) return;
    let html = content.trim();
    if (html.startsWith("```")) {
      html = html.replace(/^```(?:html)?\s*\n?/, "").replace(/\n?```\s*$/, "");
    }
    const blob = new Blob([html], { type: "text/html" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "presentation.html";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const handleDownloadPptx = async () => {
    setIsDownloading(true);
    try {
      const token = getToken();

      // Extract title from HTML
      let pptTitle = "Presentation";
      if (content) {
        const h1 = content.match(/<h1[^>]*>([^<]+)<\/h1>/i);
        const title = content.match(/<title>([^<]+)<\/title>/i);
        if (title && title[1] !== "Presentation") pptTitle = title[1].trim();
        else if (h1) pptTitle = h1[1].trim();
      }

      // Find matching workflow for Agent 3 code
      let workflowId = "";
      try {
        const res = await fetch(`${ENV.API_URL}/api/runs?type=ppt&limit=20`, {
          headers: { "Authorization": `Bearer ${token}` },
        });
        if (res.ok) {
          const runs = await res.json();
          const h1 = content?.match(/<h1[^>]*>([^<]+)<\/h1>/i);
          if (h1) {
            const match = runs.find((r: { output?: string }) => r.output?.includes(h1[1]));
            if (match) workflowId = match.id;
          }
          if (!workflowId && runs.length > 0) workflowId = runs[0].id;
        }
      } catch {}

      const response = await fetch(`${ENV.API_URL}/api/runs/export-pptx`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}` },
        body: JSON.stringify({
          js_code: pptxCode || "",
          html: content || "",
          workflow_id: workflowId,
          title: pptTitle,
        }),
      });

      if (!response.ok) {
        const detail = await response.text();
        throw new Error(`Export failed: ${detail}`);
      }

      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${pptTitle.replace(/[^a-zA-Z0-9\s-]/g, "").trim().replace(/\s+/g, "_") || "Presentation"}.pptx`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error("PPTX download failed:", err);
      alert("Download failed. Please try again.");
    } finally {
      setIsDownloading(false);
    }
  };

  if (!content && !pptxCode) {
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

  if (!content) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3">
        <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-gray-100 border border-gray-200 animate-pulse">
          <Presentation className="h-6 w-6 text-gray-400" />
        </div>
        <p className="text-[11px] text-gray-500 font-medium">Generating slides...</p>
      </div>
    );
  }

  let htmlContent = content!.trim();
  if (htmlContent.startsWith("```")) {
    htmlContent = htmlContent.replace(/^```(?:html)?\s*\n?/, "").replace(/\n?```\s*$/, "");
  }

  // For od_ppt: extract HTML from artifact tags or find the HTML start
  // (LLM may output a preamble sentence before <!DOCTYPE html>)
  if (isOdPpt) {
    // Try artifact tags first
    const artifactMatch = htmlContent.match(/<artifact[^>]*>\s*([\s\S]*?)\s*<\/artifact>/i);
    if (artifactMatch) {
      htmlContent = artifactMatch[1].trim();
    } else {
      // Find HTML start anywhere in the string
      const htmlStart = htmlContent.search(/<!DOCTYPE\s+html|<html[\s>]/i);
      if (htmlStart > 0) {
        htmlContent = htmlContent.slice(htmlStart);
      }
    }
  }

  // Strip any download/export buttons baked into the HTML (we handle download externally)
  htmlContent = htmlContent.replace(/<button[^>]*class="dl-btn"[^>]*>[^<]*<\/button>/gi, "");
  htmlContent = htmlContent.replace(/<button[^>]*onclick="generatePresentation\(\)"[^>]*>[^<]*<\/button>/gi, "");
  htmlContent = htmlContent.replace(/<button[^>]*>[^<]*(?:download|export)\s*pptx[^<]*<\/button>/gi, "");

  // Inject CSS to fix iframe internal height when revision bar is present
  if (onRevise) {
    // Override the internal html/body height to use 100% of iframe container, not 100vh
    const heightFix = `<style>html,body{height:100%!important;overflow:hidden!important}</style>`;
    if (htmlContent.includes('</head>')) {
      htmlContent = htmlContent.replace('</head>', `${heightFix}</head>`);
    } else {
      htmlContent = heightFix + htmlContent;
    }
  }

  const isHtml = /<!DOCTYPE\s+html|<html[\s>]/i.test(htmlContent);

  if (!isHtml) {
    return (
      <div className="flex h-full items-center justify-center p-4">
        <div className="rounded-xl border border-red-200 bg-red-50 p-5 text-center max-w-sm">
          <Presentation className="h-7 w-7 text-red-400 mx-auto mb-3" />
          <p className="text-xs font-semibold text-red-800">Invalid presentation output</p>
          <p className="text-[10px] text-red-600 mt-2">Try running the pipeline again.</p>
        </div>
      </div>
    );
  }

  const handleOpenFullScreen = () => {
    const blob = new Blob([htmlContent], { type: "text/html" });
    const url = URL.createObjectURL(blob);
    window.open(url, "_blank");
    setTimeout(() => URL.revokeObjectURL(url), 5000);
  };

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* ── Iframe — full height, buttons are in PreviewPanel tab bar ── */}
      <div className="flex-1 min-h-0 overflow-hidden">
        <iframe
          key={iframeKey}
          srcDoc={htmlContent}
          className="w-full h-full border-0"
          title="Slide Deck Preview"
          sandbox={isOdPpt ? "allow-scripts allow-same-origin" : "allow-scripts"}
        />
      </div>

      {/* Revision bar — request changes to the presentation */}
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
            placeholder='Request changes, e.g. "Make slide 3 title bigger" or "Add a slide about ROI"'
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
