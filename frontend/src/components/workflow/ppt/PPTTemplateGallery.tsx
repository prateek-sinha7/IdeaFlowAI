"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Search, Check, Upload, X, ExternalLink, Presentation } from "lucide-react";
import { getPPTTemplatePreviewUrl, getPPTTemplateThumbnailUrl, type PPTTemplate } from "@/lib/ppt-api";
import {
  CustomTemplateModal,
  loadCustomTemplates,
  deleteCustomTemplate,
  type CustomTemplate,
} from "@/components/workflow/prototype/CustomTemplateModal";

interface PPTTemplateGalleryProps {
  templates: PPTTemplate[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onSelectCustomTemplate?: (ct: CustomTemplate | null) => void;
  selectedCustomTemplateId?: string | null;
}

function getPPTBucket(template: PPTTemplate): string {
  const name = template.name.toLowerCase();
  const scenario = (template.scenario ?? "").toLowerCase();
  if (name.includes("pitch") || name.includes("investor") || name.includes("ib-pitch") || name.includes("fundrais")) return "Pitch Deck";
  if (name.includes("tech") || name.includes("code") || name.includes("terminal") || name.includes("engineering")) return "Tech";
  if (name.includes("editorial") || name.includes("magazine") || name.includes("kami") || name.includes("guizang")) return "Editorial";
  if (name.includes("weekly") || name.includes("report") || name.includes("quarterly") || name.includes("course") || name.includes("training")) return "Business";
  if (name.includes("minimal") || name.includes("simple") || name.includes("clean") || name.includes("dir-key")) return "Minimal";
  if (["design", "creative", "artistic", "creator"].includes(scenario)) return "Creative";
  if (name.includes("replit") || name.includes("open-design") || name.includes("landing")) return "Creative";
  return "All";
}

const CATEGORIES = ["All", "Pitch Deck", "Business", "Tech", "Editorial", "Creative", "Minimal", "Custom"];

export function PPTTemplateGallery({
  templates, selectedId, onSelect, onSelectCustomTemplate, selectedCustomTemplateId,
}: PPTTemplateGalleryProps) {
  const [query, setQuery] = useState("");
  const [activeCategory, setActiveCategory] = useState("All");
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [savedCustomTemplates, setSavedCustomTemplates] = useState<CustomTemplate[]>([]);
  const [detailTemplateId, setDetailTemplateId] = useState<string | null>(null);

  const detailTemplate = useMemo(
    () => templates.find((t) => t.id === detailTemplateId) ?? null,
    [templates, detailTemplateId],
  );

  useEffect(() => {
    setSavedCustomTemplates(loadCustomTemplates());
  }, []);

  const filtered = useMemo(() => {
    if (activeCategory === "Custom") return [];
    const q = query.trim().toLowerCase();
    return templates.filter((t) => {
      if (!t.has_preview) return false;
      if (activeCategory !== "All" && getPPTBucket(t) !== activeCategory) return false;
      if (!q) return true;
      return [t.name, t.description, ...(t.triggers || [])].join(" ").toLowerCase().includes(q);
    });
  }, [templates, query, activeCategory]);

  const filteredCustom = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return savedCustomTemplates;
    return savedCustomTemplates.filter((ct) =>
      ct.name.toLowerCase().includes(q) || ct.sourceRef.toLowerCase().includes(q),
    );
  }, [savedCustomTemplates, query]);

  const showCustom = activeCategory === "All" || activeCategory === "Custom";

  return (
    <div className="rounded-2xl border border-gray-200/70 bg-white overflow-hidden">
      {/* Detail modal */}
      {detailTemplate && (
        <PPTTemplateDetailModal
          template={detailTemplate}
          isSelected={detailTemplate.id === selectedId}
          onSelect={(id) => { onSelect(id); setDetailTemplateId(null); }}
          onClose={() => setDetailTemplateId(null)}
        />
      )}

      {showUploadModal && (
        <CustomTemplateModal
          onConfirm={(ct) => {
            setSavedCustomTemplates(loadCustomTemplates());
            setShowUploadModal(false);
            if (onSelectCustomTemplate) onSelectCustomTemplate(ct);
          }}
          onClose={() => setShowUploadModal(false)}
        />
      )}

      {/* Top bar */}
      <div className="border-b border-gray-100">
        <div className="flex items-center px-3 pt-3 pb-0 gap-2">
          <div className="flex items-center overflow-x-auto scrollbar-none flex-1 min-w-0">
            {CATEGORIES.map((cat) => (
              <button
                key={cat}
                type="button"
                onClick={() => setActiveCategory(cat)}
                className={`flex-shrink-0 flex items-center gap-1.5 rounded-t-lg px-3.5 py-1.5 text-[12px] font-medium transition-colors whitespace-nowrap ${
                  activeCategory === cat ? "bg-gray-100 text-gray-900 font-semibold" : "text-gray-500 hover:text-gray-800"
                }`}
              >
                {cat}
                {cat === "Custom" && savedCustomTemplates.length > 0 && (
                  <span className={`inline-flex h-4 min-w-[16px] items-center justify-center rounded-full px-1 text-[9px] font-bold ${
                    activeCategory === "Custom" ? "bg-[#1B2A4A] text-white" : "bg-gray-200 text-gray-600"
                  }`}>
                    {savedCustomTemplates.length}
                  </span>
                )}
              </button>
            ))}
          </div>
          <button
            type="button"
            onClick={() => setShowUploadModal(true)}
            className="flex-shrink-0 flex items-center gap-1.5 rounded-lg border border-dashed border-gray-300 bg-white px-3 py-1.5 text-[11px] font-medium text-gray-500 hover:border-[#1B2A4A] hover:text-[#1B2A4A] hover:bg-[#1B2A4A]/5 transition-all mb-0.5"
          >
            <Upload className="h-3.5 w-3.5" />
            Upload custom
          </button>
        </div>
        <div className="px-3 py-2">
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3 w-3 -translate-y-1/2 text-gray-400" />
            <input
              type="text" value={query} onChange={(e) => setQuery(e.target.value)}
              placeholder="Search templates…"
              className="w-full rounded-lg border border-gray-200 bg-gray-50 py-1.5 pl-7 pr-3 text-[12px] text-gray-900 placeholder:text-gray-400 focus:border-gray-300 focus:bg-white focus:outline-none"
            />
          </div>
        </div>
      </div>

      {/* Grid */}
      <div className="overflow-y-auto p-3" style={{ maxHeight: "360px" }}>
        {activeCategory === "Custom" ? (
          filteredCustom.length === 0 ? (
            <div className="flex h-40 flex-col items-center justify-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl border-2 border-dashed border-gray-200 bg-gray-50">
                <Upload className="h-4 w-4 text-gray-400" />
              </div>
              <div className="text-center">
                <p className="text-[12px] font-medium text-gray-600">No custom templates yet</p>
                <p className="mt-0.5 text-[11px] text-gray-400">Upload an HTML file or paste a URL</p>
              </div>
              <button type="button" onClick={() => setShowUploadModal(true)}
                className="flex items-center gap-1.5 rounded-lg bg-[#1B2A4A] px-3 py-1.5 text-[11px] font-medium text-white hover:bg-[#0F1B33] transition-colors">
                <Upload className="h-3 w-3" /> Upload custom template
              </button>
            </div>
          ) : (
            <div className="grid gap-2.5" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(130px, 1fr))" }}>
              {filteredCustom.map((ct) => (
                <CustomTemplateCard key={ct.id} ct={ct}
                  selected={selectedCustomTemplateId === ct.id}
                  onSelect={() => { if (onSelectCustomTemplate) onSelectCustomTemplate(ct); }}
                  onDelete={() => {
                    deleteCustomTemplate(ct.id);
                    setSavedCustomTemplates(loadCustomTemplates());
                    if (selectedCustomTemplateId === ct.id && onSelectCustomTemplate) onSelectCustomTemplate(null);
                  }}
                />
              ))}
            </div>
          )
        ) : filtered.length === 0 && (!showCustom || filteredCustom.length === 0) ? (
          <div className="flex h-32 items-center justify-center text-[12px] text-gray-400">
            No templates match your search.
          </div>
        ) : (
          <div className="grid gap-2.5" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(130px, 1fr))" }}>
            {showCustom && filteredCustom.map((ct) => (
              <CustomTemplateCard key={ct.id} ct={ct}
                selected={selectedCustomTemplateId === ct.id}
                onSelect={() => { if (onSelectCustomTemplate) onSelectCustomTemplate(ct); }}
                onDelete={() => {
                  deleteCustomTemplate(ct.id);
                  setSavedCustomTemplates(loadCustomTemplates());
                  if (selectedCustomTemplateId === ct.id && onSelectCustomTemplate) onSelectCustomTemplate(null);
                }}
              />
            ))}
            {filtered.map((template) => (
              <CompactPPTCard key={template.id} template={template} selected={template.id === selectedId}
                onOpenDetail={() => setDetailTemplateId(template.id)} />
            ))}
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="border-t border-gray-100 px-4 py-1.5">
        <span className="text-[10px] text-gray-400">
          {activeCategory === "Custom"
            ? `${savedCustomTemplates.length} custom template${savedCustomTemplates.length !== 1 ? "s" : ""}`
            : `${filtered.length} template${filtered.length !== 1 ? "s" : ""}${activeCategory !== "All" ? ` · ${activeCategory}` : ""}`
          }
        </span>
      </div>
    </div>
  );
}

// ── Custom template card ──────────────────────────────────────────────────

function CustomTemplateCard({ ct, selected, onSelect, onDelete }: {
  ct: CustomTemplate; selected: boolean; onSelect: () => void; onDelete: () => void;
}) {
  return (
    <div className={`group relative flex flex-col overflow-hidden rounded-lg border bg-white text-left transition-all hover:shadow-sm ${
      selected ? "border-[#1B2A4A] ring-2 ring-[#1B2A4A]/15 shadow-sm" : "border-gray-200 hover:border-gray-300"
    }`}>
      {selected && (
        <div className="absolute right-1.5 top-1.5 z-10 flex h-5 w-5 items-center justify-center rounded-full bg-[#1B2A4A]">
          <Check className="h-2.5 w-2.5 text-white" strokeWidth={3} />
        </div>
      )}
      <button type="button" onClick={(e) => { e.stopPropagation(); onDelete(); }}
        className="absolute left-1.5 top-1.5 z-10 hidden h-5 w-5 items-center justify-center rounded-full bg-white/90 text-gray-400 shadow-sm hover:text-red-500 group-hover:flex"
        title="Remove">
        <X className="h-3 w-3" />
      </button>
      <button type="button" onClick={onSelect} className="flex flex-col flex-1 text-left focus:outline-none">
        <div className="flex h-[80px] items-center justify-center bg-gradient-to-br from-[#1B2A4A]/5 to-[#1B2A4A]/10">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-white border border-gray-200 shadow-sm">
            <Upload className="h-4 w-4 text-[#1B2A4A]" />
          </div>
        </div>
        <div className="px-2 py-1.5">
          <span className="block truncate text-[11px] font-medium text-gray-800 leading-tight">{ct.name}</span>
          <span className="text-[9px] uppercase tracking-wide text-gray-400">{ct.source === "file" ? "HTML file" : "From URL"}</span>
        </div>
      </button>
    </div>
  );
}

// ── Compact card ──────────────────────────────────────────────────────────

function CompactPPTCard({ template, selected, onOpenDetail }: {
  template: PPTTemplate; selected: boolean; onOpenDetail: () => void;
}) {
  const cardRef = useRef<HTMLButtonElement>(null);
  const [shouldMount, setShouldMount] = useState(false);
  const [previewLoaded, setPreviewLoaded] = useState(false);
  // See TemplateCard: `has_thumbnail` can be stale or the file can 404 at
  // request time. On <img> error, fall through to the live-iframe fallback.
  const [thumbnailError, setThumbnailError] = useState(false);

  useEffect(() => {
    const node = cardRef.current;
    if (!node) return;
    const observer = new IntersectionObserver(
      (entries) => { if (entries.some((e) => e.isIntersecting)) { setShouldMount(true); observer.disconnect(); } },
      { rootMargin: "150px" },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  const previewUrl = template.has_preview ? getPPTTemplatePreviewUrl(template.id) : null;
  // Only use the thumbnail while it hasn't errored (404 / load failure).
  const thumbnailUrl =
    template.has_thumbnail && !thumbnailError ? getPPTTemplateThumbnailUrl(template.id) : null;

  return (
    <button ref={cardRef} type="button" onClick={onOpenDetail}
      className={`group relative flex flex-col overflow-hidden rounded-lg border bg-white text-left transition-all hover:shadow-sm focus:outline-none ${
        selected ? "border-[#1B2A4A] ring-2 ring-[#1B2A4A]/15 shadow-sm" : "border-gray-200 hover:border-gray-300"
      }`}>
      {selected && (
        <div className="absolute right-1.5 top-1.5 z-10 flex h-5 w-5 items-center justify-center rounded-full bg-[#1B2A4A]">
          <Check className="h-2.5 w-2.5 text-white" strokeWidth={3} />
        </div>
      )}
      {/* Preview thumbnail — PPT decks are responsive (100vw/100vh).
          We render the iframe at 800×450 (16:9) and scale it down to fit
          the 130px-wide card at ~80px height. */}
      <div className="relative overflow-hidden bg-gray-50" style={{ height: "80px" }}>
        {thumbnailUrl ? (
          // Pre-rendered screenshot — one cheap <img> load instead of a full
          // iframe document render. Falls back to the sandboxed (allow-scripts) iframe below.
          <>
            {!previewLoaded && (
              <div className="absolute inset-0 animate-pulse bg-gradient-to-br from-gray-100 to-gray-200" />
            )}
            {/* eslint-disable-next-line @next/next/no-img-element -- static same-origin thumbnail; next/image optimization + remotePatterns are unwanted overhead here */}
            <img
              src={thumbnailUrl}
              alt={template.name}
              loading="lazy"
              onLoad={() => setPreviewLoaded(true)}
              onError={() => {
                // Thumbnail missing / 404 — degrade to the live iframe below.
                setThumbnailError(true);
                setShouldMount(true);
                setPreviewLoaded(false);
              }}
              className="h-full w-full object-cover object-top"
              style={{ opacity: previewLoaded ? 1 : 0, transition: "opacity 200ms ease-out" }}
            />
          </>
        ) : previewUrl && shouldMount ? (
          <>
            {!previewLoaded && (
              <div className="absolute inset-0 animate-pulse bg-gradient-to-br from-gray-100 to-gray-200" />
            )}
            {/* Fallback when no pre-rendered thumbnail exists yet: render the
                template's example.html live (HTML + JS) in a sandboxed iframe,
                scaled down. Heavier than the <img>, but only hit until the
                build-time thumbnail is generated. */}
            <iframe
              src={previewUrl}
              title={template.name}
              sandbox="allow-scripts"
              loading="lazy"
              onLoad={() => setPreviewLoaded(true)}
              style={{
                width: "800px",
                height: "450px",
                transform: "scale(0.1625)",   /* 130 / 800 = 0.1625 */
                transformOrigin: "top left",
                border: 0,
                pointerEvents: "none",
                opacity: previewLoaded ? 1 : 0,
                transition: "opacity 200ms ease-out",
              }}
            />
          </>
        ) : previewUrl ? (
          <div className="absolute inset-0 animate-pulse bg-gradient-to-br from-gray-100 to-gray-200" />
        ) : (
          <div className="flex h-full items-center justify-center bg-gradient-to-br from-gray-50 to-gray-100">
            <span className="text-[9px] text-gray-400 text-center px-2 leading-tight font-medium">{template.name}</span>
          </div>
        )}
      </div>
      <div className="px-2 py-1.5">
        <span className="block truncate text-[11px] font-medium text-gray-800 leading-tight">{template.name}</span>
        {template.mode && (
          <span className="text-[9px] uppercase tracking-wide text-gray-400">{template.mode}</span>
        )}
      </div>
    </button>
  );
}

// ── Detail modal ──────────────────────────────────────────────────────────

function PPTTemplateDetailModal({
  template,
  isSelected,
  onSelect,
  onClose,
}: {
  template: PPTTemplate;
  isSelected: boolean;
  onSelect: (id: string) => void;
  onClose: () => void;
}) {
  const previewUrl = template.has_preview ? getPPTTemplatePreviewUrl(template.id) : null;
  const [previewLoaded, setPreviewLoaded] = useState(false);

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose} />

      {/* Modal */}
      <div className="relative z-10 flex w-full max-w-4xl flex-col overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-2xl"
        style={{ maxHeight: "90vh" }}>

        {/* Header */}
        <div className="flex items-center justify-between border-b border-gray-100 px-5 py-3.5 flex-shrink-0">
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-[#1B2A4A]/10">
              <Presentation className="h-4 w-4 text-[#1B2A4A]" />
            </div>
            <div>
              <h2 className="text-[14px] font-semibold text-gray-900">{template.name}</h2>
              {template.description && (
                <p className="text-[11px] text-gray-500 mt-0.5 max-w-md truncate">{template.description}</p>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2">
            {previewUrl && (
              <button
                type="button"
                onClick={() => window.open(previewUrl, "_blank")}
                title="Open preview in new tab"
                className="flex h-7 w-7 items-center justify-center rounded-lg border border-gray-200 text-gray-400 hover:bg-gray-50 hover:text-gray-700 transition-colors"
              >
                <ExternalLink className="h-3.5 w-3.5" />
              </button>
            )}
            <button type="button" onClick={onClose}
              className="flex h-7 w-7 items-center justify-center rounded-lg border border-gray-200 text-gray-400 hover:bg-gray-50 hover:text-gray-700 transition-colors">
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>

        {/* Preview iframe — full 16:9 */}
        <div className="flex-1 min-h-0 bg-gray-900 relative" style={{ aspectRatio: "16/9", maxHeight: "60vh" }}>
          {previewUrl ? (
            <>
              {!previewLoaded && (
                <div className="absolute inset-0 flex items-center justify-center bg-gray-900">
                  <div className="flex flex-col items-center gap-3">
                    <div className="h-8 w-8 animate-spin rounded-full border-2 border-white/20 border-t-white" />
                    <p className="text-[11px] text-white/50">Loading preview…</p>
                  </div>
                </div>
              )}
              <iframe
                src={previewUrl}
                title={template.name}
                sandbox="allow-scripts"
                onLoad={() => setPreviewLoaded(true)}
                className="w-full h-full border-0"
                style={{ opacity: previewLoaded ? 1 : 0, transition: "opacity 300ms ease-out" }}
              />
            </>
          ) : (
            <div className="flex h-full items-center justify-center">
              <div className="text-center">
                <Presentation className="h-12 w-12 text-white/20 mx-auto mb-3" />
                <p className="text-[12px] text-white/40">No preview available</p>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-gray-100 px-5 py-3.5 flex-shrink-0 bg-white">
          <div className="flex items-center gap-3">
            {template.mode && (
              <span className="rounded-full bg-gray-100 px-2.5 py-1 text-[10px] font-medium text-gray-600 uppercase tracking-wide">
                {template.mode}
              </span>
            )}
            {template.design_system?.requires && (
              <span className="rounded-full bg-blue-50 px-2.5 py-1 text-[10px] font-medium text-blue-600">
                Uses design system
              </span>
            )}
          </div>
          <button
            type="button"
            onClick={() => onSelect(template.id)}
            className={`flex items-center gap-2 rounded-xl px-5 py-2.5 text-[13px] font-semibold transition-all ${
              isSelected
                ? "bg-emerald-500 text-white"
                : "bg-[#1B2A4A] text-white hover:bg-[#0F1B33]"
            }`}
          >
            {isSelected ? (
              <><Check className="h-4 w-4" strokeWidth={3} /> Selected</>
            ) : (
              "Use this template"
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
