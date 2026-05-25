"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Search, Check, FileText, TrendingUp } from "lucide-react";
import { getTemplatePreviewUrl, type PrototypeTemplate } from "@/lib/prototype-api";
import { TemplateDetailModal } from "./TemplateDetailModal";

interface TemplateGalleryProps {
  templates: PrototypeTemplate[];
  selectedId: string | null;
  onSelect: (id: string) => void;
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

const CATEGORIES = ["All", "Design", "Marketing", "Operations", "Engineering", "Product", "Finance & HR"];

export function TemplateGallery({ templates, selectedId, onSelect }: TemplateGalleryProps) {
  const [query, setQuery] = useState("");
  const [activeCategory, setActiveCategory] = useState("All");
  const [detailTemplateId, setDetailTemplateId] = useState<string | null>(null);

  const detailTemplate = useMemo(
    () => templates.find((t) => t.id === detailTemplateId) ?? null,
    [templates, detailTemplateId],
  );

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return templates.filter((t) => {
      if (!t.has_preview) return false; // hide templates without example.html
      if (activeCategory !== "All" && getBucket(t.scenario) !== activeCategory) return false;
      if (!q) return true;
      return [t.name, t.description, ...(t.triggers || [])]
        .join(" ").toLowerCase().includes(q);
    });
  }, [templates, query, activeCategory]);

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

      {/* ── Top bar: category tabs + search ──────────────────────────── */}
      <div className="border-b border-gray-100">
        {/* Category tabs */}
        <div className="flex items-center overflow-x-auto px-3 pt-3 pb-0 scrollbar-none">
          {CATEGORIES.map((cat) => (
            <button
              key={cat}
              type="button"
              onClick={() => setActiveCategory(cat)}
              className={`flex-shrink-0 rounded-t-lg px-3.5 py-1.5 text-[12px] font-medium transition-colors whitespace-nowrap ${
                activeCategory === cat
                  ? "bg-gray-100 text-gray-900 font-semibold"
                  : "text-gray-500 hover:text-gray-800"
              }`}
            >
              {cat}
            </button>
          ))}
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
        {filtered.length === 0 ? (
          <div className="flex h-32 items-center justify-center text-[12px] text-gray-400">
            No templates match your search.
          </div>
        ) : (
          <div
            className="grid gap-2.5"
            style={{ gridTemplateColumns: "repeat(auto-fill, minmax(130px, 1fr))" }}
          >
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
          {filtered.length} template{filtered.length !== 1 ? "s" : ""}
          {activeCategory !== "All" && ` · ${activeCategory}`}
        </span>
      </div>
    </div>
  );
}

// ── No-preview placeholder — shown for templates that produce Markdown/reports ──

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
        {previewUrl && shouldMount ? (
          <>
            {!previewLoaded && (
              <div className="absolute inset-0 animate-pulse bg-gradient-to-br from-gray-100 to-gray-200" />
            )}
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
