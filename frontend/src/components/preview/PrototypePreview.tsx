"use client";

import { useState, useEffect } from "react";
import { Layout, ExternalLink, RefreshCw } from "lucide-react";

interface PrototypePreviewProps {
  content?: string;
  isStreaming?: boolean;
  onRevise?: (instruction: string) => void;
}

/**
 * Renders the prototype HTML in a browser-chrome mockup.
 *
 * Navigation fix: uses a Blob URL instead of srcdoc so the iframe gets a
 * null origin. With sandbox="allow-scripts allow-same-origin", the iframe
 * can read/write window.location.hash (enabling hash routing) but cannot
 * access the parent's localStorage (JWT is safe — null origin ≠ localhost).
 */
export function PrototypePreview({ content, isStreaming, onRevise }: PrototypePreviewProps) {
  const [revisionText, setRevisionText] = useState("");
  const [blobUrl, setBlobUrl] = useState<string | null>(null);

  // Build a Blob URL from the HTML content.
  // Blob URLs have a null origin — allow-same-origin gives the iframe
  // same-origin access to itself (null === null) but NOT to the parent
  // (parent is localhost:3000, iframe is null origin — cross-origin).
  // This makes window.location.hash writable and hashchange events fire,
  // enabling the SPA hash router in the generated prototype HTML.
  useEffect(() => {
    if (!content) {
      setBlobUrl(null);
      return;
    }

    let htmlContent = content.trim();

    // Strip markdown code fences
    if (htmlContent.startsWith("```")) {
      htmlContent = htmlContent.replace(/^```(?:html)?\s*\n?/, "").replace(/\n?```\s*$/, "");
    }

    // Robust HTML check — handles leading whitespace, comments, or BOM
    // Search the FULL string (not just first 500 chars) — the LLM may output
    // a preamble sentence before <!DOCTYPE html>
    const isHtml = /<!DOCTYPE\s+html|<html[\s>]/i.test(htmlContent);
    if (!isHtml) {
      setBlobUrl(null);
      return;
    }

    const blob = new Blob([htmlContent], { type: "text/html" });
    const url = URL.createObjectURL(blob);
    setBlobUrl(url);

    return () => {
      URL.revokeObjectURL(url);
    };
  }, [content]);

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

  // If blobUrl is null, content is not HTML — show raw text fallback
  if (!blobUrl) {
    // Check if content looks like it could be HTML (still processing in useEffect)
    // Search full string — preamble prose may appear before <!DOCTYPE>
    const mightBeHtml = content && /<!DOCTYPE\s+html|<html[\s>]/i.test(content);
    if (mightBeHtml) {
      // useEffect hasn't fired yet — show loading briefly
      return (
        <div className="flex h-full flex-col items-center justify-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-gray-100 border border-gray-200 animate-pulse">
            <Layout className="h-6 w-6 text-gray-400" />
          </div>
          <p className="text-[11px] text-gray-500 font-medium">Loading preview...</p>
        </div>
      );
    }
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
    window.open(blobUrl, "_blank");
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

      {/* Prototype iframe — Blob URL with null origin.
          allow-same-origin: lets the iframe's JS use window.location.hash
            (null === null, so same-origin to itself).
            Parent is localhost:3000 — different from null origin,
            so the iframe cannot access parent localStorage or JWT.
          allow-scripts: enables the SPA router and all interactivity. */}
      <div className="flex-1 min-h-0">
        <iframe
          key={blobUrl}
          src={blobUrl}
          className="w-full h-full border-0"
          sandbox="allow-scripts allow-same-origin"
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
