"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Search, Check, X, Plus, Pencil, Trash2, Upload } from "lucide-react";
import { getDesignSystem, type DesignSystemListItem } from "@/lib/prototype-api";
import { getToken } from "@/lib/api";
import { extractPalette } from "@/lib/design-system-colors";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { DesignSystemDetailModal } from "./DesignSystemDetailModal";
import {
  CustomDesignSystemModal,
  loadCustomDesignSystems,
  saveCustomDesignSystems,
  type CustomDesignSystem,
} from "./CustomDesignSystemModal";

interface DesignSystemPickerProps {
  systems: DesignSystemListItem[];
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  onSelectCustom: (ds: CustomDesignSystem | null) => void;
}

export function DesignSystemPicker({
  systems,
  selectedId,
  onSelect,
  onSelectCustom,
}: DesignSystemPickerProps) {
  const [query, setQuery] = useState("");
  const [activeCategory, setActiveCategory] = useState("All");
  const [detailSystem, setDetailSystem] = useState<DesignSystemListItem | null>(null);
  const [customSystems, setCustomSystems] = useState<CustomDesignSystem[]>([]);
  const [showCustomModal, setShowCustomModal] = useState(false);
  const [editingCustom, setEditingCustom] = useState<CustomDesignSystem | undefined>(undefined);

  useEffect(() => {
    setCustomSystems(loadCustomDesignSystems());
  }, []);

  const selected = useMemo(
    () => systems.find((s) => s.id === selectedId) ?? null,
    [systems, selectedId],
  );
  const selectedCustom = useMemo(
    () => customSystems.find((s) => s.id === selectedId) ?? null,
    [customSystems, selectedId],
  );

  // All unique categories from built-in systems, sorted
  const allCategories = useMemo(() => {
    const cats = new Set(systems.map((s) => s.category));
    return ["All", ...Array.from(cats).sort(), "Custom"];
  }, [systems]);

  // Filtered + grouped built-in systems
  const grouped = useMemo(() => {
    const q = query.trim().toLowerCase();
    const filtered = systems.filter((s) => {
      // Category filter
      if (activeCategory !== "All" && activeCategory !== "Custom" && s.category !== activeCategory) return false;
      if (activeCategory === "Custom") return false; // custom tab shows only user systems
      // Search filter
      if (!q) return true;
      return (
        s.name.toLowerCase().includes(q) ||
        s.category.toLowerCase().includes(q) ||
        s.description.toLowerCase().includes(q)
      );
    });
    const map = new Map<string, DesignSystemListItem[]>();
    for (const s of filtered) {
      const list = map.get(s.category) ?? [];
      list.push(s);
      map.set(s.category, list);
    }
    // When a specific category is active, don't show the group header — just flat chips
    return Array.from(map.entries()).sort(([a], [b]) => a.localeCompare(b));
  }, [systems, query, activeCategory]);

  const filteredCustom = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return customSystems;
    return customSystems.filter((s) => s.name.toLowerCase().includes(q));
  }, [customSystems, query]);

  // Show custom systems when on All tab or Custom tab
  const showCustomSystems = activeCategory === "All" || activeCategory === "Custom";

  const handleSaveCustom = (ds: CustomDesignSystem) => {
    setCustomSystems((prev) => {
      const without = prev.filter((s) => s.id !== ds.id);
      const next = [ds, ...without];
      saveCustomDesignSystems(next);
      return next;
    });
    onSelect(ds.id);
    onSelectCustom(ds);
    setShowCustomModal(false);
    setEditingCustom(undefined);
  };

  const handleDeleteCustom = (id: string) => {
    setCustomSystems((prev) => {
      const next = prev.filter((s) => s.id !== id);
      saveCustomDesignSystems(next);
      return next;
    });
    if (selectedId === id) {
      onSelect(null);
      onSelectCustom(null);
    }
  };

  const handleSelectBuiltIn = (id: string) => {
    onSelect(id === selectedId ? null : id);
    onSelectCustom(null);
  };

  const handleSelectCustom = (ds: CustomDesignSystem) => {
    if (selectedId === ds.id) {
      onSelect(null);
      onSelectCustom(null);
    } else {
      onSelect(ds.id);
      onSelectCustom(ds);
    }
  };

  const selectedName = selected?.name ?? selectedCustom?.name ?? null;

  // Total count for footer
  const totalVisible = grouped.reduce((acc, [, items]) => acc + items.length, 0)
    + (showCustomSystems ? filteredCustom.length : 0);

  return (
    <>
      {detailSystem && (
        <DesignSystemDetailModal
          system={detailSystem}
          isSelected={detailSystem.id === selectedId}
          onSelect={handleSelectBuiltIn}
          onClose={() => setDetailSystem(null)}
        />
      )}

      {showCustomModal && (
        <CustomDesignSystemModal
          existing={editingCustom}
          onSave={handleSaveCustom}
          onClose={() => { setShowCustomModal(false); setEditingCustom(undefined); }}
        />
      )}

      <Card className="bg-surface-white font-sans">

        {/* ── Header: title + selected badge + upload button ─────────── */}
        <div className="flex items-center justify-between gap-4 border-b border-line-divider px-5 py-4">
          <div>
            <h2 className="text-[15px] font-semibold text-ink-900 font-sans">Choose a design system</h2>
            <p className="mt-0.5 text-[12px] text-ink-500">
              Sets the brand tokens — colors, typography, density. Click any card to preview the full spec.
            </p>
          </div>

          <div className="flex flex-shrink-0 items-center gap-2">
            {selectedName && (
              <div className="flex items-center gap-2 rounded-[var(--radius-button)] border border-brand-border bg-brand-fill px-3 py-1.5">
                <div className="flex h-5 w-5 items-center justify-center rounded-full bg-brand">
                  <Check className="h-2.5 w-2.5 text-white" strokeWidth={3} />
                </div>
                <span className="text-[12px] font-semibold text-brand">{selectedName}</span>
                {selectedCustom && (
                  <span className="rounded-full bg-brand/10 px-1.5 py-0.5 text-[9px] font-semibold text-brand">
                    custom
                  </span>
                )}
                <button
                  type="button"
                  onClick={() => { onSelect(null); onSelectCustom(null); }}
                  className="ml-0.5 text-brand/50 hover:text-brand"
                  aria-label="Clear selection"
                >
                  <X className="h-3 w-3" />
                </button>
              </div>
            )}

            <button
              type="button"
              onClick={() => { setEditingCustom(undefined); setShowCustomModal(true); }}
              className="flex-shrink-0 flex items-center gap-1.5 rounded-[var(--radius-button)] border border-dashed border-line-control bg-surface-white px-3 py-1.5 text-[11px] font-medium text-ink-500 hover:border-brand hover:text-brand hover:bg-brand-fill transition-all"
              title="Upload a custom design system (DESIGN.md)"
            >
              <Upload className="h-3.5 w-3.5" />
              Upload custom
            </button>
          </div>
        </div>

        {/* ── Category tabs + search ──────────────────────────────────── */}
        <div className="border-b border-line-divider">
          {/* Scrollable category tabs */}
          <div role="tablist" className="flex items-center overflow-x-auto px-4 pt-3 pb-0 scrollbar-none gap-0.5">
            {allCategories.map((cat) => (
              <button
                key={cat}
                type="button"
                role="tab"
                aria-selected={activeCategory === cat}
                onClick={() => setActiveCategory(cat)}
                className={`flex-shrink-0 flex items-center gap-1.5 rounded-t-lg px-3 py-1.5 text-[11px] font-medium transition-colors whitespace-nowrap ${
                  activeCategory === cat
                    ? "bg-surface-warm text-ink-900 font-semibold"
                    : "text-ink-500 hover:text-ink-800"
                }`}
              >
                {cat}
                {/* Badge for Custom tab */}
                {cat === "Custom" && customSystems.length > 0 && (
                  <span className={`inline-flex h-4 min-w-[16px] items-center justify-center rounded-full px-1 text-[9px] font-bold ${
                    activeCategory === "Custom"
                      ? "bg-brand text-white"
                      : "bg-surface-paper text-ink-600"
                  }`}>
                    {customSystems.length}
                  </span>
                )}
              </button>
            ))}
          </div>

          {/* Search */}
          <div className="px-5 py-3">
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-400" />
              <input
                type="text"
                aria-label="Search design systems"
                name="design-system-search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search by brand, style, or category…"
                className="w-full rounded-[var(--radius-button)] border border-line-control bg-surface-warm py-2 pl-9 pr-3 text-[13px] text-ink-900 placeholder:text-ink-400 focus:border-brand-border focus:bg-surface-white focus:outline-none"
              />
              {query && (
                <button
                  type="button"
                  onClick={() => setQuery("")}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-ink-400 hover:text-ink-700"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              )}
            </div>
          </div>
        </div>

        {/* ── Chip list ───────────────────────────────────────────────── */}
        <div className="max-h-[320px] overflow-y-auto px-5 py-4 space-y-5">

          {/* Custom tab — empty state */}
          {activeCategory === "Custom" && filteredCustom.length === 0 && (
            <div className="flex flex-col items-center justify-center py-10 gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl border-2 border-dashed border-line-control bg-surface-warm">
                <Upload className="h-4 w-4 text-ink-400" />
              </div>
              <div className="text-center">
                <p className="text-[12px] font-medium text-ink-600">No custom design systems yet</p>
                <p className="mt-0.5 text-[11px] text-ink-400">Paste a DESIGN.md to create your own</p>
              </div>
              <Button
                variant="primary"
                size="sm"
                onClick={() => { setEditingCustom(undefined); setShowCustomModal(true); }}
              >
                <Plus className="h-3 w-3" />
                Upload custom design system
              </Button>
            </div>
          )}

          {/* Custom systems — shown on All and Custom tabs */}
          {showCustomSystems && filteredCustom.length > 0 && (
            <div>
              <div className="mb-2 flex items-center gap-2">
                <span className="text-[10px] font-semibold uppercase tracking-wide text-ink-400">
                  Your custom systems
                </span>
                <span className="text-[10px] text-ink-300">{filteredCustom.length}</span>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {filteredCustom.map((ds) => {
                  const isSelected = ds.id === selectedId;
                  return (
                    <div key={ds.id} className="group relative inline-flex">
                      <button
                        type="button"
                        onClick={() => handleSelectCustom(ds)}
                        className={`inline-flex items-center gap-1.5 rounded-[var(--radius-pill)] border px-2.5 py-1 text-[12px] font-medium transition-all pr-8 ${
                          isSelected
                            ? "border-brand bg-brand text-white shadow-sm"
                            : "border-line-control bg-surface-white text-ink-700 hover:border-line-faint hover:bg-surface-warm"
                        }`}
                      >
                        {isSelected && <Check className="h-2.5 w-2.5 flex-shrink-0" strokeWidth={3} />}
                        {ds.name}
                      </button>
                      <div className="absolute right-1 top-1/2 -translate-y-1/2 hidden group-hover:flex items-center gap-0.5">
                        <button
                          type="button"
                          onClick={(e) => { e.stopPropagation(); setEditingCustom(ds); setShowCustomModal(true); }}
                          className={`rounded p-0.5 transition-colors ${isSelected ? "text-white/70 hover:text-white" : "text-ink-400 hover:text-ink-700"}`}
                          title="Edit"
                        >
                          <Pencil className="h-2.5 w-2.5" />
                        </button>
                        <button
                          type="button"
                          onClick={(e) => { e.stopPropagation(); handleDeleteCustom(ds.id); }}
                          className={`rounded p-0.5 transition-colors ${isSelected ? "text-white/70 hover:text-white" : "text-ink-400 hover:text-status-failed"}`}
                          title="Delete"
                        >
                          <Trash2 className="h-2.5 w-2.5" />
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Built-in systems — grouped by category */}
          {activeCategory !== "Custom" && (
            grouped.length === 0 && !showCustomSystems ? (
              <div className="py-8 text-center text-[13px] text-ink-500">
                No design systems match <span className="font-medium">"{query}"</span>.
                <button type="button" onClick={() => setQuery("")} className="ml-2 text-brand hover:underline">
                  Clear
                </button>
              </div>
            ) : (
              grouped.map(([category, items]) => (
                <DesignSystemGroup
                  key={category}
                  category={category}
                  // Hide group header when a specific category is active (redundant)
                  showHeader={activeCategory === "All"}
                  items={items}
                  selectedId={selectedId}
                  onSelect={handleSelectBuiltIn}
                  onOpenDetail={setDetailSystem}
                />
              ))
            )
          )}

          {/* No results at all */}
          {activeCategory !== "Custom" && grouped.length === 0 && filteredCustom.length === 0 && query && (
            <div className="py-8 text-center text-[13px] text-ink-500">
              No design systems match <span className="font-medium">"{query}"</span>.
              <button type="button" onClick={() => setQuery("")} className="ml-2 text-brand hover:underline">
                Clear
              </button>
            </div>
          )}
        </div>

        {/* ── Footer count ────────────────────────────────────────────── */}
        <div className="border-t border-line-divider px-5 py-1.5">
          <span className="text-[10px] text-ink-400">
            {activeCategory === "Custom"
              ? `${customSystems.length} custom design system${customSystems.length !== 1 ? "s" : ""}`
              : `${totalVisible} design system${totalVisible !== 1 ? "s" : ""}${activeCategory !== "All" ? ` · ${activeCategory}` : ""}`
            }
          </span>
        </div>
      </Card>
    </>
  );
}

// ── Group ─────────────────────────────────────────────────────────────────

interface GroupProps {
  category: string;
  showHeader: boolean;
  items: DesignSystemListItem[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onOpenDetail: (system: DesignSystemListItem) => void;
}

function DesignSystemGroup({ category, showHeader, items, selectedId, onSelect, onOpenDetail }: GroupProps) {
  return (
    <div>
      {showHeader && (
        <div className="mb-2 flex items-center gap-2">
          <span className="text-[10px] font-semibold uppercase tracking-wide text-ink-400">{category}</span>
          <span className="text-[10px] text-ink-300">{items.length}</span>
        </div>
      )}
      {/* Swatch band-card grid (RESTRUCTURE from the rounded-pill chip list). */}
      <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3">
        {items.map((ds) => (
          <DesignSystemBandCard
            key={ds.id}
            ds={ds}
            isSelected={ds.id === selectedId}
            onSelect={onSelect}
            onOpenDetail={onOpenDetail}
          />
        ))}
      </div>
    </div>
  );
}

// ── Band-card ─────────────────────────────────────────────────────────────
//
// One card per live registry entry (LOCK-F/ND-8 — the real ~14, never a
// hardcoded count). The colour swatches are sourced the SAME way
// DesignSystemDetailModal sources its preview: fetch the DESIGN.md body
// (getDesignSystem) and run extractPalette over it. No token → no fetch →
// neutral placeholder band (keeps the picker usable pre-auth / in tests).
//
// Clicking the card body opens the live detail-modal preview; the corner
// toggle drives onSelect(id) / clears to onSelect(null) — exactly the chip
// list's selection contract.

function DesignSystemBandCard({
  ds,
  isSelected,
  onSelect,
  onOpenDetail,
}: {
  ds: DesignSystemListItem;
  isSelected: boolean;
  onSelect: (id: string) => void;
  onOpenDetail: (system: DesignSystemListItem) => void;
}) {
  const [palette, setPalette] = useState<string[]>([]);

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    let cancelled = false;
    getDesignSystem(token, ds.id)
      .then((detail) => {
        if (!cancelled) setPalette(extractPalette(detail.body, 5));
      })
      .catch(() => {
        if (!cancelled) setPalette([]);
      });
    return () => {
      cancelled = true;
    };
  }, [ds.id]);

  return (
    <div
      data-testid="ds-band-card"
      className={`group relative flex flex-col overflow-hidden rounded-[var(--radius-card)] border transition-all hover:shadow-[var(--elevation-raised)] ${
        isSelected
          ? "border-brand ring-1 ring-brand"
          : "border-line-control hover:border-line-faint"
      }`}
    >
      {/* ── Card body — opens the live detail-modal preview ─────────────── */}
      <button
        type="button"
        onClick={() => onOpenDetail(ds)}
        title={ds.description || ds.name}
        className="flex flex-1 flex-col text-left"
      >
        {/* Swatch band */}
        <div data-testid="ds-swatch-band" className="flex h-11 w-full">
          {palette.length > 0 ? (
            palette.map((hex, i) => (
              <div key={i} className="h-full flex-1" style={{ backgroundColor: hex }} />
            ))
          ) : (
            // Neutral placeholder band on Phase-32 tokens (no live body yet).
            <>
              <div className="h-full flex-1 bg-surface-paper" />
              <div className="h-full flex-1 bg-surface-warm" />
              <div className="h-full flex-1 bg-line-divider" />
              <div className="h-full flex-1 bg-line-control" />
            </>
          )}
        </div>

        {/* Meta */}
        <div className="flex flex-col gap-0.5 border-t border-line-divider bg-surface-white px-3 py-2">
          <span
            className={`truncate text-[12.5px] font-semibold ${isSelected ? "text-brand" : "text-ink-800"}`}
          >
            {ds.name}
          </span>
          <span className="flex items-center gap-1.5 truncate text-[10.5px] text-ink-400">
            {ds.category}
            {ds.has_preview && (
              <span className="rounded-full bg-brand-fill px-1.5 py-px text-[8.5px] font-semibold text-brand">
                components
              </span>
            )}
          </span>
        </div>
      </button>

      {/* ── Corner select toggle — onSelect(id) / clears to onSelect(null) ── */}
      <button
        type="button"
        data-testid="ds-band-select"
        onClick={() => onSelect(ds.id)}
        aria-pressed={isSelected}
        aria-label={isSelected ? `Deselect ${ds.name}` : `Select ${ds.name}`}
        className={`absolute right-2 top-2 flex h-5 w-5 items-center justify-center rounded-full border transition-all ${
          isSelected
            ? "border-brand bg-brand text-white"
            : "border-line-control bg-surface-white text-ink-400 opacity-0 group-hover:opacity-100 hover:border-brand hover:text-brand"
        }`}
      >
        {isSelected ? <Check className="h-2.5 w-2.5" strokeWidth={3} /> : <Plus className="h-3 w-3" />}
      </button>
    </div>
  );
}
