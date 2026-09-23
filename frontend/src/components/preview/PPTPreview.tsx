"use client";

import { useState } from "react";
import { Presentation, RefreshCw } from "lucide-react";
import { authedFetch, getToken } from "@/lib/api";
import { ENV } from "@/lib/env";
import { stripStaticPreviewFallback } from "@/lib/deckHtml";

interface PPTPreviewProps {
  content?: string;
  isStreaming?: boolean;
  /** Agent 3's raw PptxGenJS code — enables reliable server-side export (ppt pipeline only) */
  pptxCode?: string;
  /** Callback to trigger a revision pipeline run */
  onRevise?: (instruction: string) => void;
  /** @deprecated Every ppt run is now the HTML-deck pipeline; kept only so
   * existing callers don't need an edit. No longer read. */
  pipelineType?: string;
  /** The run on screen. Without it the export falls back to "most recent
   *  type=ppt run", which is the wrong run for a reopened deck and no run at
   *  all for `ppt_v2` (spec 017). */
  runId?: string | null;
}

export function PPTPreview({ content, isStreaming, pptxCode, runId, onRevise }: PPTPreviewProps) {
  const [iframeKey] = useState(0);
  const [isDownloading, setIsDownloading] = useState(false);
  const [revisionText, setRevisionText] = useState("");

  // Every ppt run produces an HTML deck now (the legacy PptxGenJS pipeline is
  // retired — see backend/agents/registry.py); this component always uses the
  // scaled-iframe HTML render path.
  const isOdPpt = true;

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
      let workflowId = runId ?? "";
      if (!workflowId) {
        try {
          const res = await authedFetch(`${ENV.API_URL}/api/runs?type=ppt&limit=20`, {
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
      }

      // FR-015: authedFetch, not bare fetch — Blob response, so request() is
      // not an option; a 401 previously threw a plain "Export failed" with no
      // session-expiry redirect.
      const response = await authedFetch(`${ENV.API_URL}/api/runs/export-pptx`, {
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

  // For all ppt decks: extract HTML from artifact tags or find the HTML start.
  // The validator LLM sometimes emits a checklist preamble (✓ lines, VERDICT text)
  // before <!DOCTYPE html>, even inside the artifact tags. Always slice to the
  // actual HTML start to strip any such preamble — this is safe for all ppt types.
  {
    // Try artifact tags first
    const artifactMatch = htmlContent.match(/<artifact[^>]*>\s*([\s\S]*?)\s*<\/artifact>/i);
    if (artifactMatch) {
      htmlContent = artifactMatch[1].trim();
    }
    // Strip any text before the deck's HTML document. The Deck QA agent prepends a
    // markdown validation report that itself QUOTES "<!DOCTYPE html>" inline (e.g.
    // "✓ Single complete HTML file starting with `<!DOCTYPE html>`"), so a plain
    // search lands on that quoted mention and the whole report leaks into the deck
    // iframe (rendering faintly behind the slides). Anchor the doctype / `<html>`
    // match to the START OF A LINE first — the real deck opens a line; the report's
    // mention is mid-sentence. Fall back to a loose match if none is line-anchored.
    let htmlStart = htmlContent.search(/^[ \t]*<!DOCTYPE\s+html|^[ \t]*<html[\s>]/im);
    if (htmlStart < 0) htmlStart = htmlContent.search(/<!DOCTYPE\s+html|<html[\s>]/i);
    if (htmlStart > 0) {
      htmlContent = htmlContent.slice(htmlStart);
    }
    // …and drop any trailing text AFTER the deck's closing </html>, in case the
    // report (or a verdict) is appended after the deck too. Only the deck document
    // should reach the iframe.
    const htmlEndIdx = htmlContent.toLowerCase().lastIndexOf("</html>");
    if (htmlEndIdx >= 0) {
      htmlContent = htmlContent.slice(0, htmlEndIdx + "</html>".length);
    }
  }

  // Strip any download/export buttons baked into the HTML (we handle download externally)
  htmlContent = htmlContent.replace(/<button[^>]*class="dl-btn"[^>]*>[^<]*<\/button>/gi, "");
  htmlContent = htmlContent.replace(/<button[^>]*onclick="generatePresentation\(\)"[^>]*>[^<]*<\/button>/gi, "");
  htmlContent = htmlContent.replace(/<button[^>]*>[^<]*(?:download|export)\s*pptx[^<]*<\/button>/gi, "");

  // The deck's own nav script is disabled by the template's static-preview
  // fallback CSS unless that block is removed — see lib/deckHtml.
  htmlContent = stripStaticPreviewFallback(htmlContent);

  // od_ppt decks are scaled from outside the iframe using ResizeObserver +
  // CSS transform (see the iframe container below). No in-body injection needed.

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
      {/* ── Iframe — scaled to fit the container at 16:9 design size ── */}
      {/* The deck's HTML uses 100vw/100vh at 1280×720. We give the iframe its
          full design resolution (1280×720) and use CSS transform to scale it
          down to fill the available container — this way vw/vh inside the
          iframe resolve correctly and the whole slide is visible. */}
      <div className="flex-1 min-h-0 overflow-hidden relative" ref={(el) => {
        if (!el || !isOdPpt) return;
        const resize = () => {
          const iframe = el.querySelector('iframe') as HTMLIFrameElement | null;
          if (!iframe) return;
          const cw = el.clientWidth;
          const ch = el.clientHeight;
          const scaleW = cw / 1280;
          const scaleH = ch / 720;
          const scale = Math.min(scaleW, scaleH);
          // Position iframe at top-left, scale from top-left, then center the result
          iframe.style.width = '1280px';
          iframe.style.height = '720px';
          iframe.style.transform = `scale(${scale})`;
          iframe.style.transformOrigin = '0 0';
          iframe.style.position = 'absolute';
          // Center horizontally
          const scaledW = 1280 * scale;
          const scaledH = 720 * scale;
          iframe.style.left = Math.max(0, (cw - scaledW) / 2) + 'px';
          iframe.style.top = Math.max(0, (ch - scaledH) / 2) + 'px';
        };
        const ro = new ResizeObserver(resize);
        ro.observe(el);
        resize();
      }}>
        <iframe
          key={iframeKey}
          srcDoc={htmlContent}
          title="Slide Deck Preview"
          sandbox={isOdPpt ? "allow-scripts allow-same-origin" : "allow-scripts"}
          style={isOdPpt ? {
            width: '1280px',
            height: '720px',
            border: 'none',
            display: 'block',
            position: 'absolute',
          } : undefined}
          className={isOdPpt ? undefined : "w-full h-full border-0"}
        />
      </div>

      {/* Revision bar — request changes to the presentation */}
      {onRevise && (
        <div className="flex-shrink-0 border-t border-gray-200 bg-white px-4 py-3 flex items-center gap-3">
          <input
            type="text"
            aria-label="Revision instructions"
            name="ppt-revision"
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
