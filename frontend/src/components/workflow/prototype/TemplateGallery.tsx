"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Search, Check, FileText, TrendingUp, Upload, X } from "lucide-react";
import { getTemplatePreviewUrl, getTemplateThumbnailUrl, type PrototypeTemplate } from "@/lib/prototype-api";
import { TemplateDetailModal } from "./TemplateDetailModal";
import {
  CustomTemplateModal,
  loadCustomTemplates,
  deleteCustomTemplate,
  type CustomTemplate,
} from "./CustomTemplateModal";

interface TemplateGalleryProps {
  templates: PrototypeTemplate[];
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  onSelectCustomTemplate?: (ct: CustomTemplate | null) => void;
  selectedCustomTemplateId?: string | null;
}

// Consolidate raw scenario values into 6 clean buckets
function getBucket(scenario: string | null): string {
  const s = (scenario ?? "").toLowerCase();
  if (["design", "personal", "creator", "education"].includes(s)) return "Design";
  if (["marketing", "sale", "sales"].includes(s)) return "Marketing";
  if (["operations", "operation", "live", "live-artifacts"].includes(s)) return "Operations";
  if (["engineering", "healthcare", "video"].includes(s)) return "Engineering";
  if (["product", "orbit"].includes(s)) return "Product";
  if (["finance", "hr"].includes(s)) return "Finance & HR";
  return "Other";
}

const CATEGORIES = ["All", "Design", "Marketing", "Operations", "Engineering", "Product", "Finance & HR", "Custom"];

export function TemplateGallery({ templates, selectedId, onSelect, onSelectCustomTemplate, selectedCustomTemplateId }: TemplateGalleryProps) {
  const [query, setQuery] = useState("");
  const [activeCategory, setActiveCategory] = useState("All");
  const [detailTemplateId, setDetailTemplateId] = useState<string | null>(null);
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [savedCustomTemplates, setSavedCustomTemplates] = useState<CustomTemplate[]>([]);

  // Load saved custom templates from localStorage on mount
  useEffect(() => {
    setSavedCustomTemplates(loadCustomTemplates());
  }, []);

  const detailTemplate = useMemo(
    () => templates.find((t) => t.id === detailTemplateId) ?? null,
    [templates, detailTemplateId],
  );

  const filtered = useMemo(() => {
    // Custom tab shows only custom templates — built-in list is hidden
    if (activeCategory === "Custom") return [];
    const q = query.trim().toLowerCase();
    return templates.filter((t) => {
      if (!t.has_preview) return false; // hide templates without example.html
      if (activeCategory !== "All" && getBucket(t.scenario) !== activeCategory) return false;
      if (!q) return true;
      return [t.name, t.description, ...(t.triggers || [])]
        .join(" ").toLowerCase().includes(q);
    });
  }, [templates, query, activeCategory]);

  // Custom templates filtered by search query
  const filteredCustom = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return savedCustomTemplates;
    return savedCustomTemplates.filter((ct) =>
      ct.name.toLowerCase().includes(q) || ct.sourceRef.toLowerCase().includes(q),
    );
  }, [savedCustomTemplates, query]);

  return (
    <div className="rounded-2xl border border-gray-200/70 bg-white overflow-hidden">
      {detailTemplate && (
        <TemplateDetailModal
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

      {/* ── Top bar: category tabs + upload button + search ──────────── */}
      <div className="border-b border-gray-100">
        {/* Category tabs row — tabs on left, Upload button on right */}
        <div className="flex items-center px-3 pt-3 pb-0 gap-2">
          {/* Scrollable tabs */}
          <div className="flex items-center overflow-x-auto scrollbar-none flex-1 min-w-0">
            {CATEGORIES.map((cat) => (
              <button
                key={cat}
                type="button"
                onClick={() => setActiveCategory(cat)}
                className={`flex-shrink-0 rounded-t-lg px-3.5 py-1.5 text-[12px] font-medium transition-colors whitespace-nowrap flex items-center gap-1.5 ${
                  activeCategory === cat
                    ? "bg-gray-100 text-gray-900 font-semibold"
                    : "text-gray-500 hover:text-gray-800"
                }`}
              >
                {cat}
                {cat === "Custom" && savedCustomTemplates.length > 0 && (
                  <span className={`inline-flex h-4 min-w-[16px] items-center justify-center rounded-full px-1 text-[9px] font-bold ${
                    activeCategory === "Custom"
                      ? "bg-[#1B2A4A] text-white"
                      : "bg-gray-200 text-gray-600"
                  }`}>
                    {savedCustomTemplates.length}
                  </span>
                )}
              </button>
            ))}
          </div>

          {/* Upload custom button — always visible, top-right */}
          <button
            type="button"
            onClick={() => setShowUploadModal(true)}
            className="flex-shrink-0 flex items-center gap-1.5 rounded-lg border border-dashed border-gray-300 bg-white px-3 py-1.5 text-[11px] font-medium text-gray-500 hover:border-[#1B2A4A] hover:text-[#1B2A4A] hover:bg-[#1B2A4A]/5 transition-all mb-0.5"
            title="Upload a custom HTML template"
          >
            <Upload className="h-3.5 w-3.5" />
            Upload custom
          </button>
        </div>

        {/* Search */}
        <div className="px-3 py-2">
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3 w-3 -translate-y-1/2 text-gray-400" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search templates…"
              className="w-full rounded-lg border border-gray-200 bg-gray-50 py-1.5 pl-7 pr-3 text-[12px] text-gray-900 placeholder:text-gray-400 focus:border-gray-300 focus:bg-white focus:outline-none"
            />
          </div>
        </div>
      </div>

      {/* ── Grid ─────────────────────────────────────────────────────── */}
      <div className="overflow-y-auto p-3" style={{ maxHeight: "360px" }}>
        {activeCategory === "Custom" ? (
          /* ── Custom tab: only custom templates + upload card ── */
          filteredCustom.length === 0 && !query ? (
            /* Empty state — no custom templates yet */
            <div className="flex h-40 flex-col items-center justify-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl border-2 border-dashed border-gray-200 bg-gray-50">
                <Upload className="h-4 w-4 text-gray-400" />
              </div>
              <div className="text-center">
                <p className="text-[12px] font-medium text-gray-600">No custom templates yet</p>
                <p className="mt-0.5 text-[11px] text-gray-400">Upload an HTML file or paste a URL to get started</p>
              </div>
              <button
                type="button"
                onClick={() => setShowUploadModal(true)}
                className="flex items-center gap-1.5 rounded-lg bg-[#1B2A4A] px-3 py-1.5 text-[11px] font-medium text-white hover:bg-[#0F1B33] transition-colors"
              >
                <Upload className="h-3 w-3" />
                Upload custom template
              </button>
            </div>
          ) : (
            <div
              className="grid gap-2.5"
              style={{ gridTemplateColumns: "repeat(auto-fill, minmax(130px, 1fr))" }}
            >
              {filteredCustom.map((ct) => (
                <CustomTemplateCard
                  key={ct.id}
                  ct={ct}
                  selected={selectedCustomTemplateId === ct.id}
                  onSelect={() => { if (onSelectCustomTemplate) onSelectCustomTemplate(ct); }}
                  onDelete={() => {
                    deleteCustomTemplate(ct.id);
                    setSavedCustomTemplates(loadCustomTemplates());
                    if (selectedCustomTemplateId === ct.id && onSelectCustomTemplate) {
                      onSelectCustomTemplate(null);
                    }
                  }}
                />
              ))}
              </div>
          )
        ) : filtered.length === 0 && (activeCategory !== "All" || savedCustomTemplates.length === 0) ? (
          <div className="flex h-32 items-center justify-center text-[12px] text-gray-400">
            No templates match your search.
          </div>
        ) : (
          <div
            className="grid gap-2.5"
            style={{ gridTemplateColumns: "repeat(auto-fill, minmax(130px, 1fr))" }}
          >
            {/* KAN-87: No template / blank canvas card — shown first in All tab */}
            {activeCategory === "All" && (
              <NoTemplateCard
                selected={selectedId === null && !selectedCustomTemplateId}
                onSelect={() => {
                  onSelect(null);
                  if (onSelectCustomTemplate) onSelectCustomTemplate(null);
                }}
              />
            )}

            {/* Saved custom templates — shown at top of All tab */}
            {activeCategory === "All" && savedCustomTemplates.map((ct) => (
              <CustomTemplateCard
                key={ct.id}
                ct={ct}
                selected={selectedCustomTemplateId === ct.id}
                onSelect={() => { if (onSelectCustomTemplate) onSelectCustomTemplate(ct); }}
                onDelete={() => {
                  deleteCustomTemplate(ct.id);
                  setSavedCustomTemplates(loadCustomTemplates());
                  if (selectedCustomTemplateId === ct.id && onSelectCustomTemplate) {
                    onSelectCustomTemplate(null);
                  }
                }}
              />
            ))}

            {/* Built-in templates */}
            {filtered.map((template) => (
              <CompactTemplateCard
                key={template.id}
                template={template}
                selected={template.id === selectedId}
                onOpenDetail={setDetailTemplateId}
              />
            ))}
          </div>
        )}
      </div>

      {/* ── Footer count ─────────────────────────────────────────────── */}
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

interface CustomCardProps {
  ct: CustomTemplate;
  selected: boolean;
  onSelect: () => void;
  onDelete: () => void;
}

function CustomTemplateCard({ ct, selected, onSelect, onDelete }: CustomCardProps) {
  return (
    <div
      className={`group relative flex flex-col overflow-hidden rounded-lg border bg-white text-left transition-all hover:shadow-sm ${
        selected
          ? "border-[#1B2A4A] ring-2 ring-[#1B2A4A]/15 shadow-sm"
          : "border-gray-200 hover:border-gray-300"
      }`}
    >
      {/* Selected badge */}
      {selected && (
        <div className="absolute right-1.5 top-1.5 z-10 flex h-5 w-5 items-center justify-center rounded-full bg-[#1B2A4A]">
          <Check className="h-2.5 w-2.5 text-white" strokeWidth={3} />
        </div>
      )}

      {/* Delete button */}
      <button
        type="button"
        onClick={(e) => { e.stopPropagation(); onDelete(); }}
        className="absolute left-1.5 top-1.5 z-10 hidden h-5 w-5 items-center justify-center rounded-full bg-white/90 text-gray-400 shadow-sm hover:text-red-500 group-hover:flex"
        title="Remove custom template"
      >
        <X className="h-3 w-3" />
      </button>

      {/* Preview area */}
      <button
        type="button"
        onClick={onSelect}
        className="flex flex-col flex-1 text-left focus:outline-none"
      >
        <div className="flex h-[80px] items-center justify-center bg-gradient-to-br from-[#1B2A4A]/5 to-[#1B2A4A]/10">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-white border border-gray-200 shadow-sm">
            <Upload className="h-4 w-4 text-[#1B2A4A]" />
          </div>
        </div>
        <div className="px-2 py-1.5">
          <span className="block truncate text-[11px] font-medium text-gray-800 leading-tight">
            {ct.name}
          </span>
          <span className="text-[9px] uppercase tracking-wide text-gray-400">
            {ct.source === "file" ? "HTML file" : "From URL"}
          </span>
        </div>
      </button>
    </div>
  );
}

// ── No template card (KAN-87) ────────────────────────────────────────────

function NoTemplateCard({ selected, onSelect }: { selected: boolean; onSelect: () => void }) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={`flex flex-col overflow-hidden rounded-lg border bg-white text-left transition-all hover:shadow-sm focus:outline-none ${
        selected
          ? "border-[#1B2A4A] ring-2 ring-[#1B2A4A]/15 shadow-sm"
          : "border-gray-200 hover:border-gray-300"
      }`}
    >
      {/* Selected badge */}
      {selected && (
        <div className="absolute right-1.5 top-1.5 z-10 flex h-5 w-5 items-center justify-center rounded-full bg-[#1B2A4A]">
          <Check className="h-2.5 w-2.5 text-white" strokeWidth={3} />
        </div>
      )}
      {/* Visual area */}
      <div className="flex h-[80px] items-center justify-center bg-gradient-to-br from-gray-50 to-gray-100 relative">
        <div className="flex flex-col items-center gap-1">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-dashed border-gray-300 bg-white">
            <FileText className="h-4 w-4 text-gray-400" />
          </div>
        </div>
      </div>
      {/* Label */}
      <div className="px-2 py-1.5">
        <span className="block truncate text-[11px] font-medium text-gray-800 leading-tight">
          No template
        </span>
        <span className="text-[9px] uppercase tracking-wide text-gray-400">
          Blank canvas
        </span>
      </div>
    </button>
  );
}

// ── Upload custom card ────────────────────────────────────────────────────

function UploadCustomCard({ onOpen }: { onOpen: () => void }) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className="flex flex-col items-center justify-center gap-1.5 overflow-hidden rounded-lg border-2 border-dashed border-gray-200 bg-white text-center transition-all hover:border-gray-300 hover:bg-gray-50 focus:outline-none"
      style={{ minHeight: "110px" }}
    >
      <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-gray-100">
        <Upload className="h-3.5 w-3.5 text-gray-500" />
      </div>
      <span className="px-2 text-[10px] font-medium text-gray-500 leading-tight">
        Upload custom
      </span>
    </button>
  );
}

// Map template id → what it produces, so the placeholder is informative
const TEMPLATE_OUTPUT_LABELS: Record<string, { label: string; icon: "doc" | "chart" | "research" }> = {
  "dcf-valuation": { label: "Financial report", icon: "chart" },
  "last30days":    { label: "Research brief",   icon: "research" },
  "live-artifact": { label: "Live dashboard",   icon: "doc" },
  "x-research":    { label: "Sentiment report", icon: "research" },
};

function NoPreviewPlaceholder({ template }: { template: PrototypeTemplate }) {
  const meta = TEMPLATE_OUTPUT_LABELS[template.id];
  const label = meta?.label ?? "Document output";
  const icon = meta?.icon ?? "doc";

  return (
    <div className="flex h-full flex-col items-center justify-center gap-1.5 bg-gray-50/80 px-2">
      <div className="flex h-7 w-7 items-center justify-center rounded-md bg-white border border-gray-200 shadow-sm">
        {icon === "chart" ? (
          <TrendingUp className="h-3.5 w-3.5 text-gray-400" />
        ) : (
          <FileText className="h-3.5 w-3.5 text-gray-400" />
        )}
      </div>
      <span className="text-[9px] text-gray-400 text-center leading-tight">{label}</span>
    </div>
  );
}

// ── Compact card ──────────────────────────────────────────────────────────

interface CompactCardProps {
  template: PrototypeTemplate;
  selected: boolean;
  onOpenDetail: (id: string) => void;
}

function CompactTemplateCard({ template, selected, onOpenDetail }: CompactCardProps) {
  const cardRef = useRef<HTMLButtonElement>(null);
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
      { rootMargin: "150px" },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  const previewUrl = template.has_preview ? getTemplatePreviewUrl(template.id) : null;
  const thumbnailUrl = template.has_thumbnail ? getTemplateThumbnailUrl(template.id) : null;

  return (
    <button
      ref={cardRef}
      type="button"
      onClick={() => onOpenDetail(template.id)}
      className={`group relative flex flex-col overflow-hidden rounded-lg border bg-white text-left transition-all hover:shadow-sm focus:outline-none ${
        selected
          ? "border-[#1B2A4A] ring-2 ring-[#1B2A4A]/15 shadow-sm"
          : "border-gray-200 hover:border-gray-300"
      }`}
    >
      {/* Selected badge */}
      {selected && (
        <div className="absolute right-1.5 top-1.5 z-10 flex h-5 w-5 items-center justify-center rounded-full bg-[#1B2A4A]">
          <Check className="h-2.5 w-2.5 text-white" strokeWidth={3} />
        </div>
      )}

      {/* Preview thumbnail */}
      <div className="relative overflow-hidden bg-gray-50" style={{ height: "80px" }}>
        {thumbnailUrl ? (
          // Pre-rendered screenshot of example.html — one cheap <img> load
          // instead of a full iframe document render. Falls back to the
          // (script-free) iframe path below when no thumbnail was generated.
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
                width: "1280px",
                height: "720px",
                transform: "scale(0.1016)",
                transformOrigin: "top left",
                border: 0,
                pointerEvents: "none",
                opacity: previewLoaded ? 1 : 0,
                transition: "opacity 200ms ease-out",
              }}
            />
          </>
        ) : previewUrl ? (
          // Has preview URL but not mounted yet — shimmer
          <div className="absolute inset-0 animate-pulse bg-gradient-to-br from-gray-100 to-gray-200" />
        ) : (
          // No example.html — show what the template produces
          <NoPreviewPlaceholder template={template} />
        )}
      </div>

      {/* Name */}
      <div className="px-2 py-1.5">
        <span className="block truncate text-[11px] font-medium text-gray-800 leading-tight">
          {template.name}
        </span>
        {template.platform && (
          <span className="text-[9px] uppercase tracking-wide text-gray-400">
            {template.platform}
          </span>
        )}
      </div>
    </button>
  );
}
