"use client";

import { useEffect, useRef, useState } from "react";
import { X, ExternalLink, Check, Maximize2, Minimize2 } from "lucide-react";
import { getTemplatePreviewUrl, type PrototypeTemplate } from "@/lib/prototype-api";

interface TemplateDetailModalProps {
  template: PrototypeTemplate;
  isSelected: boolean;
  onClose: () => void;
  onSelect: (templateId: string) => void;
}

/**
 * Template preview modal — shows only the live iframe preview.
 * No design system panel. Clean and focused.
 */
export function TemplateDetailModal({
  template,
  isSelected,
  onClose,
  onSelect,
}: TemplateDetailModalProps) {
  const [fullscreen, setFullscreen] = useState(false);
  const [iframeLoaded, setIframeLoaded] = useState(false);
  const stageRef = useRef<HTMLDivElement>(null);
  const previewUrl = template.has_preview ? getTemplatePreviewUrl(template.id) : null;

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

  const enterFullscreen = () => {
    stageRef.current?.requestFullscreen?.().catch(() => setFullscreen(true));
    setFullscreen(true);
  };
  const exitFullscreen = () => {
    if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
    setFullscreen(false);
  };
  useEffect(() => {
    const fn = () => { if (!document.fullscreenElement) setFullscreen(false); };
    document.addEventListener("fullscreenchange", fn);
    return () => document.removeEventListener("fullscreenchange", fn);
  }, []);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-[var(--scrim)] backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label={`${template.name} preview`}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div
        ref={stageRef}
        className={`flex flex-col bg-surface-near-black shadow-[var(--elevation-modal)] ${
          fullscreen
            ? "fixed inset-0 rounded-none"
            : "relative h-[90vh] w-[95vw] max-w-[1300px] rounded-[var(--radius-card)] overflow-hidden"
        }`}
      >
        {/* ── Header ─────────────────────────────────────────────────── */}
        <header className="flex flex-shrink-0 items-center justify-between gap-3 border-b border-white/10 bg-surface-ink-black px-5 py-3">
          <div className="flex min-w-0 flex-col">
            <span className="truncate text-[14px] font-semibold text-white">
              {template.name}
            </span>
            <div className="flex items-center gap-2 mt-0.5">
              {template.platform && (
                <span className="text-[10px] font-medium text-white/60 uppercase tracking-wide">
                  {template.platform}
                </span>
              )}
              {template.scenario && (
                <span className="text-[10px] text-white/40 capitalize">{template.scenario}</span>
              )}
            </div>
          </div>

          <div className="flex flex-shrink-0 items-center gap-1.5">
            {/* Select button */}
            <button
              type="button"
              onClick={() => { onSelect(template.id); onClose(); }}
              className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[12px] font-semibold transition-all ${
                isSelected
                  ? "bg-status-done/20 text-status-done border border-status-done/40"
                  : "bg-brand text-white hover:bg-brand-pressed"
              }`}
            >
              {isSelected && <Check className="h-3 w-3" strokeWidth={3} />}
              {isSelected ? "Selected" : "Use this template"}
            </button>

            {/* Open in new tab */}
            {previewUrl && (
              <button
                type="button"
                onClick={() => window.open(previewUrl, "_blank")}
                title="Open in new tab"
                className="flex items-center justify-center rounded-lg border border-white/10 bg-white/5 p-1.5 text-white/60 transition-colors hover:text-white"
              >
                <ExternalLink className="h-3.5 w-3.5" />
              </button>
            )}

            {/* Fullscreen */}
            <button
              type="button"
              onClick={fullscreen ? exitFullscreen : enterFullscreen}
              title={fullscreen ? "Exit fullscreen" : "Fullscreen"}
              className="flex items-center justify-center rounded-lg border border-white/10 bg-white/5 p-1.5 text-white/60 transition-colors hover:text-white"
            >
              {fullscreen ? <Minimize2 className="h-3.5 w-3.5" /> : <Maximize2 className="h-3.5 w-3.5" />}
            </button>

            {/* Close */}
            <button
              type="button"
              onClick={onClose}
              title="Close"
              className="flex items-center justify-center rounded-lg border border-white/10 bg-white/5 p-1.5 text-white/60 transition-colors hover:text-white"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        </header>

        {/* ── Preview ─────────────────────────────────────────────────── */}
        <div className="relative flex-1 min-h-0 bg-surface-ink-black">
          {previewUrl ? (
            <>
              {!iframeLoaded && (
                <div className="absolute inset-0 flex items-center justify-center">
                  <div className="flex flex-col items-center gap-3">
                    <div className="h-8 w-8 animate-spin rounded-full border-2 border-white/20 border-t-white/50" />
                    <span className="text-[11px] text-white/50">Loading preview…</span>
                  </div>
                </div>
              )}
              <iframe
                src={previewUrl}
                title={`${template.name} preview`}
                sandbox="allow-scripts"
                onLoad={() => setIframeLoaded(true)}
                className="h-full w-full border-0"
                style={{ opacity: iframeLoaded ? 1 : 0, transition: "opacity 300ms ease-out" }}
              />
            </>
          ) : (
            <div className="flex h-full items-center justify-center">
              <p className="text-[13px] text-white/50">No preview available for this template.</p>
            </div>
          )}

          {/* Meta badges — bottom left overlay */}
          <div className="absolute bottom-3 left-3 flex items-center gap-1.5 pointer-events-none">
            {template.platform && (
              <span className="rounded-full bg-surface-ink-black/60 px-2 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-white/70 backdrop-blur-sm border border-white/10">
                {template.platform}
              </span>
            )}
            {template.scenario && (
              <span className="rounded-full bg-surface-ink-black/60 px-2 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-white/60 backdrop-blur-sm border border-white/10">
                {template.scenario}
              </span>
            )}
          </div>
        </div>

        {/* ── Footer: description + craft rules ──────────────────────── */}
        {(template.description || (template.craft_required && template.craft_required.length > 0)) && (
          <footer className="flex-shrink-0 border-t border-white/10 bg-surface-ink-black px-5 py-2.5">
            {template.description && (
              <p className="text-[11px] leading-relaxed text-white/50 line-clamp-1">
                {template.description}
              </p>
            )}
            {template.craft_required && template.craft_required.length > 0 && (
              <div className="mt-1 flex flex-wrap gap-1">
                {template.craft_required.map((rule) => (
                  <span
                    key={rule}
                    className="rounded-full bg-white/5 border border-white/10 px-2 py-0.5 text-[9px] font-medium text-white/60"
                  >
                    {rule}
                  </span>
                ))}
              </div>
            )}
          </footer>
        )}
      </div>
    </div>
  );
}
