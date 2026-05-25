"use client";

import { useEffect, useMemo, useState } from "react";
import { X, Check, Maximize2, Minimize2, ExternalLink } from "lucide-react";
import {
  getDesignSystem,
  getDesignSystemPreviewUrl,
  type DesignSystemListItem,
  type DesignSystemDetail,
} from "@/lib/prototype-api";
import { getToken } from "@/lib/api";
import { generateDesignSystemPreviewHtml } from "@/lib/design-system-preview";
import { DesignSpecView } from "./DesignSpecView";

interface DesignSystemDetailModalProps {
  system: DesignSystemListItem;
  isSelected: boolean;
  onSelect: (id: string) => void;
  onClose: () => void;
}

/**
 * Split-panel modal for design system preview.
 *
 * Left  — live iframe: components.html (17 systems) OR a generated token
 *         showcase built from the DESIGN.md body (all others).
 * Right — DESIGN.md rendered as syntax-coloured spec view (DesignSpecView).
 *
 * Mirrors open-design's DesignSystemPreviewModal layout.
 */
export function DesignSystemDetailModal({
  system,
  isSelected,
  onSelect,
  onClose,
}: DesignSystemDetailModalProps) {
  const [detail, setDetail] = useState<DesignSystemDetail | null | undefined>(undefined);
  const [iframeLoaded, setIframeLoaded] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);

  // Fetch the full DESIGN.md body
  useEffect(() => {
    const token = getToken();
    if (!token) return;
    let cancelled = false;
    setDetail(undefined);
    setIframeLoaded(false);
    getDesignSystem(token, system.id)
      .then((d) => { if (!cancelled) setDetail(d); })
      .catch(() => { if (!cancelled) setDetail(null); });
    return () => { cancelled = true; };
  }, [system.id]);

  // For systems without components.html, generate a Blob URL from DESIGN.md
  const generatedPreviewUrl = useMemo(() => {
    if (system.has_preview) return null; // use the real endpoint instead
    if (!detail?.body) return null;
    const html = generateDesignSystemPreviewHtml(detail.body);
    const blob = new Blob([html], { type: "text/html" });
    return URL.createObjectURL(blob);
  }, [system.has_preview, detail?.body]);

  // Revoke blob URL on unmount or when it changes
  useEffect(() => {
    return () => {
      if (generatedPreviewUrl) URL.revokeObjectURL(generatedPreviewUrl);
    };
  }, [generatedPreviewUrl]);

  // Escape closes (or exits fullscreen first)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      if (fullscreen) { setFullscreen(false); return; }
      onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose, fullscreen]);

  // Lock body scroll
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = prev; };
  }, []);

  // The iframe src: real endpoint for systems with components.html, blob for others
  const previewSrc = system.has_preview
    ? getDesignSystemPreviewUrl(system.id)
    : generatedPreviewUrl;

  const openInNewTab = () => {
    if (previewSrc) window.open(previewSrc, "_blank");
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label={`${system.name} design system`}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div
        className={`flex flex-col bg-[#111318] shadow-2xl ${
          fullscreen
            ? "fixed inset-0 rounded-none"
            : "relative h-[90vh] w-[95vw] max-w-[1300px] rounded-2xl overflow-hidden"
        }`}
      >
        {/* ── Header ─────────────────────────────────────────────────── */}
        <header className="flex flex-shrink-0 items-center justify-between gap-3 border-b border-white/[0.08] bg-[#0d0f14] px-5 py-3">
          <div className="flex min-w-0 flex-col">
            <div className="flex items-center gap-2">
              <span className="truncate text-[14px] font-semibold text-white">
                {system.name}
              </span>
              <span className="rounded-full border border-white/[0.12] bg-white/[0.06] px-2 py-0.5 text-[10px] font-medium text-gray-400 flex-shrink-0">
                {system.category}
              </span>
              {system.has_preview && (
                <span className="rounded-full bg-emerald-500/15 border border-emerald-500/25 px-2 py-0.5 text-[9px] font-semibold text-emerald-400 flex-shrink-0">
                  components
                </span>
              )}
            </div>
            {system.description && (
              <span className="text-[11px] text-gray-500 mt-0.5 truncate max-w-[500px]">
                {system.description}
              </span>
            )}
          </div>

          <div className="flex flex-shrink-0 items-center gap-1.5">
            {/* Select */}
            <button
              type="button"
              onClick={() => { onSelect(system.id); onClose(); }}
              className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[12px] font-semibold transition-all ${
                isSelected
                  ? "bg-emerald-600/20 text-emerald-400 border border-emerald-500/30"
                  : "bg-[#1B2A4A] text-white hover:bg-[#243660]"
              }`}
            >
              {isSelected && <Check className="h-3 w-3" strokeWidth={3} />}
              {isSelected ? "Selected" : "Use this system"}
            </button>

            {/* Open in new tab */}
            {previewSrc && (
              <button
                type="button"
                onClick={openInNewTab}
                title="Open preview in new tab"
                className="flex items-center justify-center rounded-lg border border-white/[0.1] bg-white/[0.05] p-1.5 text-gray-400 transition-colors hover:text-gray-200"
              >
                <ExternalLink className="h-3.5 w-3.5" />
              </button>
            )}

            {/* Fullscreen */}
            <button
              type="button"
              onClick={() => setFullscreen((v) => !v)}
              title={fullscreen ? "Exit fullscreen" : "Fullscreen"}
              className="flex items-center justify-center rounded-lg border border-white/[0.1] bg-white/[0.05] p-1.5 text-gray-400 transition-colors hover:text-gray-200"
            >
              {fullscreen ? <Minimize2 className="h-3.5 w-3.5" /> : <Maximize2 className="h-3.5 w-3.5" />}
            </button>

            {/* Close */}
            <button
              type="button"
              onClick={onClose}
              className="flex items-center justify-center rounded-lg border border-white/[0.1] bg-white/[0.05] p-1.5 text-gray-400 transition-colors hover:text-white"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        </header>

        {/* ── Split stage ─────────────────────────────────────────────── */}
        <div className="flex flex-1 min-h-0 overflow-hidden">

          {/* ── Left: preview iframe ──────────────────────────────────── */}
          <div className="relative flex-1 min-w-0 bg-white">
            {/* Loading spinner — shown until iframe loads or body arrives */}
            {(!previewSrc || !iframeLoaded) && (
              <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-white z-10">
                {detail === undefined ? (
                  <>
                    <div className="h-7 w-7 animate-spin rounded-full border-2 border-gray-200 border-t-gray-500" />
                    <span className="text-[11px] text-gray-400">Loading preview…</span>
                  </>
                ) : detail === null ? (
                  <span className="text-[12px] text-gray-400">Preview unavailable</span>
                ) : !previewSrc ? (
                  <>
                    <div className="h-7 w-7 animate-spin rounded-full border-2 border-gray-200 border-t-gray-500" />
                    <span className="text-[11px] text-gray-400">Generating preview…</span>
                  </>
                ) : null}
              </div>
            )}

            {previewSrc && (
              <iframe
                key={previewSrc}
                src={previewSrc}
                title={`${system.name} preview`}
                sandbox="allow-scripts allow-same-origin"
                onLoad={() => setIframeLoaded(true)}
                className="h-full w-full border-0"
                style={{
                  opacity: iframeLoaded ? 1 : 0,
                  transition: "opacity 300ms ease-out",
                }}
              />
            )}
          </div>

          {/* ── Right: DESIGN.md spec view ────────────────────────────── */}
          <aside className="flex w-[380px] flex-shrink-0 flex-col border-l border-white/[0.08] bg-[#0d0f14]">
            {/* Panel header */}
            <div className="flex flex-shrink-0 items-center justify-between border-b border-white/[0.08] px-4 py-2.5">
              <span className="text-[11px] font-semibold text-gray-300">DESIGN.md</span>
              <span className="text-[10px] text-gray-600">{system.id}</span>
            </div>

            {/* Spec content */}
            <div className="flex-1 min-h-0 overflow-hidden">
              {detail === undefined ? (
                <div className="flex h-full items-center justify-center gap-3">
                  <div className="h-5 w-5 animate-spin rounded-full border-2 border-gray-700 border-t-gray-400" />
                  <span className="text-[11px] text-gray-500">Loading DESIGN.md…</span>
                </div>
              ) : detail === null ? (
                <div className="flex h-full items-center justify-center px-6 text-center">
                  <p className="text-[12px] text-gray-500">Couldn't load DESIGN.md.</p>
                </div>
              ) : (
                <DesignSpecView source={detail.body} />
              )}
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
}
