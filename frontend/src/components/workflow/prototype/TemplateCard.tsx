"use client";

import { useEffect, useRef, useState } from "react";
import { Check } from "lucide-react";
import { getTemplatePreviewUrl, type PrototypeTemplate } from "@/lib/prototype-api";
import { Pill } from "@/components/ui/Pill";

interface TemplateCardProps {
  template: PrototypeTemplate;
  selected: boolean;
  onSelect: (id: string) => void;
  /** Called when the card is clicked — opens the detail modal */
  onOpenDetail: (id: string) => void;
}

/**
 * One card in the gallery.
 *
 * The example.html preview is rendered in a sandboxed iframe at full natural
 * size (~1280px) and CSS-scaled down to fit the card. This gives a true
 * miniature of the rendered template — no server-side screenshotting needed.
 *
 * The iframe is only mounted once the card scrolls near the viewport
 * (IntersectionObserver), so the 43-card gallery doesn't spawn 43 iframes at
 * page load.
 *
 * `pointer-events: none` keeps clicks within the iframe from being swallowed
 * — the entire card is the click target.
 */
export function TemplateCard({ template, selected, onSelect, onOpenDetail }: TemplateCardProps) {
  const cardRef = useRef<HTMLButtonElement | null>(null);
  const [shouldMount, setShouldMount] = useState(false);
  const [previewLoaded, setPreviewLoaded] = useState(false);

  useEffect(() => {
    const node = cardRef.current;
    if (!node) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setShouldMount(true);
          observer.disconnect();
        }
      },
      { rootMargin: "200px" },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  const previewUrl = template.has_preview ? getTemplatePreviewUrl(template.id) : null;

  return (
    <button
      ref={cardRef}
      type="button"
      onClick={() => onOpenDetail(template.id)}
      className={`group relative flex flex-col overflow-hidden rounded-[var(--radius-card)] border bg-surface-white text-left transition-all hover:shadow-md focus:outline-none ${
        selected
          ? "border-brand ring-2 ring-brand/15 shadow-md"
          : "border-line-border hover:border-line-control"
      }`}
    >
      {/* Selected indicator */}
      {selected && (
        <div className="absolute right-2 top-2 z-10 flex h-6 w-6 items-center justify-center rounded-full bg-brand text-white">
          <Check className="h-3.5 w-3.5" strokeWidth={3} />
        </div>
      )}

      {/* "Click to preview" hint on hover */}
      <div className="absolute inset-0 z-10 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none">
        <span className="rounded-full bg-surface-ink-black/60 px-3 py-1 text-[10px] font-semibold text-white backdrop-blur-sm">
          Click to preview
        </span>
      </div>

      {/* Preview surface */}
      <div className="relative h-44 overflow-hidden bg-surface-warm">
        {previewUrl && shouldMount ? (
          <>
            {!previewLoaded && (
              <div className="absolute inset-0 animate-pulse bg-gradient-to-br from-line-faint-row to-line-divider" />
            )}
            <iframe
              src={previewUrl}
              title={`${template.name} preview`}
              sandbox="allow-scripts"
              loading="lazy"
              onLoad={() => setPreviewLoaded(true)}
              // Render the iframe at 4x the visible size and CSS-scale it down.
              // 1280x720 source → 320x180 visible (matches card width @ scale 0.25).
              style={{
                width: "1280px",
                height: "720px",
                transform: "scale(0.25)",
                transformOrigin: "top left",
                border: 0,
                pointerEvents: "none",
                opacity: previewLoaded ? 1 : 0,
                transition: "opacity 250ms ease-out",
              }}
            />
          </>
        ) : (
          <div className="flex h-full items-center justify-center text-[10px] uppercase tracking-wider text-ink-400">
            {previewUrl ? "Loading preview…" : "No preview available"}
          </div>
        )}
      </div>

      {/* Meta */}
      <div className="flex flex-col gap-1 px-3.5 py-3">
        <div className="flex items-center justify-between gap-2">
          <span className="truncate text-[13px] font-semibold text-ink-900">
            {template.name}
          </span>
          {template.platform && (
            <Pill className="flex-shrink-0 px-1.5 text-[9px] uppercase tracking-wide">
              {template.platform}
            </Pill>
          )}
        </div>
        <p className="line-clamp-2 text-[11px] leading-snug text-ink-500">
          {template.description}
        </p>
      </div>
    </button>
  );
}
