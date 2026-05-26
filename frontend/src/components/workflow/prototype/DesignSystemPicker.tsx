"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Search, Check, X, Plus, Pencil, Trash2, Upload } from "lucide-react";
import type { DesignSystemListItem } from "@/lib/prototype-api";
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

      <div className="rounded-2xl border border-gray-200/70 bg-white">

        {/* ── Header: title + selected badge + upload button ─────────── */}
        <div className="flex items-center justify-between gap-4 border-b border-gray-100 px-5 py-4">
          <div>
            <h2 className="text-[15px] font-semibold text-gray-900">Choose a design system</h2>
            <p className="mt-0.5 text-[12px] text-gray-500">
              Sets the brand tokens — colors, typography, density. Click any chip to preview the full spec.
            </p>
          </div>

          <div className="flex flex-shrink-0 items-center gap-2">
            {selectedName && (
              <div className="flex items-center gap-2 rounded-lg border border-[#1B2A4A]/20 bg-[#1B2A4A]/5 px-3 py-1.5">
                <div className="flex h-5 w-5 items-center justify-center rounded-full bg-[#1B2A4A]">
                  <Check className="h-2.5 w-2.5 text-white" strokeWidth={3} />
                </div>
                <span className="text-[12px] font-semibold text-[#1B2A4A]">{selectedName}</span>
                {selectedCustom && (
                  <span className="rounded-full bg-[#1B2A4A]/10 px-1.5 py-0.5 text-[9px] font-semibold text-[#1B2A4A]">
                    custom
                  </span>
                )}
                <button
                  type="button"
                  onClick={() => { onSelect(null); onSelectCustom(null); }}
                  className="ml-0.5 text-[#1B2A4A]/50 hover:text-[#1B2A4A]"
                  aria-label="Clear selection"
                >
                  <X className="h-3 w-3" />
                </button>
              </div>
            )}

            <button
              type="button"
              onClick={() => { setEditingCustom(undefined); setShowCustomModal(true); }}
              className="flex-shrink-0 flex items-center gap-1.5 rounded-lg border border-dashed border-gray-300 bg-white px-3 py-1.5 text-[11px] font-medium text-gray-500 hover:border-[#1B2A4A] hover:text-[#1B2A4A] hover:bg-[#1B2A4A]/5 transition-all"
              title="Upload a custom design system (DESIGN.md)"
            >
              <Upload className="h-3.5 w-3.5" />
              Upload custom
            </button>
          </div>
        </div>

        {/* ── Category tabs + search ──────────────────────────────────── */}
        <div className="border-b border-gray-100">
          {/* Scrollable category tabs */}
          <div className="flex items-center overflow-x-auto px-4 pt-3 pb-0 scrollbar-none gap-0.5">
            {allCategories.map((cat) => (
              <button
                key={cat}
                type="button"
                onClick={() => setActiveCategory(cat)}
                className={`flex-shrink-0 flex items-center gap-1.5 rounded-t-lg px-3 py-1.5 text-[11px] font-medium transition-colors whitespace-nowrap ${
                  activeCategory === cat
                    ? "bg-gray-100 text-gray-900 font-semibold"
                    : "text-gray-500 hover:text-gray-800"
                }`}
              >
                {cat}
                {/* Badge for Custom tab */}
                {cat === "Custom" && customSystems.length > 0 && (
                  <span className={`inline-flex h-4 min-w-[16px] items-center justify-center rounded-full px-1 text-[9px] font-bold ${
                    activeCategory === "Custom"
                      ? "bg-[#1B2A4A] text-white"
                      : "bg-gray-200 text-gray-600"
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
              <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-gray-400" />
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search by brand, style, or category…"
                className="w-full rounded-lg border border-gray-200 bg-gray-50 py-2 pl-9 pr-3 text-[13px] text-gray-900 placeholder:text-gray-400 focus:border-gray-300 focus:bg-white focus:outline-none"
              />
              {query && (
                <button
                  type="button"
                  onClick={() => setQuery("")}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-700"
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
              <div className="flex h-10 w-10 items-center justify-center rounded-xl border-2 border-dashed border-gray-200 bg-gray-50">
                <Upload className="h-4 w-4 text-gray-400" />
              </div>
              <div className="text-center">
                <p className="text-[12px] font-medium text-gray-600">No custom design systems yet</p>
                <p className="mt-0.5 text-[11px] text-gray-400">Paste a DESIGN.md to create your own</p>
              </div>
              <button
                type="button"
                onClick={() => { setEditingCustom(undefined); setShowCustomModal(true); }}
                className="flex items-center gap-1.5 rounded-lg bg-[#1B2A4A] px-3 py-1.5 text-[11px] font-medium text-white hover:bg-[#0F1B33] transition-colors"
              >
                <Plus className="h-3 w-3" />
                Upload custom design system
              </button>
            </div>
          )}

          {/* Custom systems — shown on All and Custom tabs */}
          {showCustomSystems && filteredCustom.length > 0 && (
            <div>
              <div className="mb-2 flex items-center gap-2">
                <span className="text-[10px] font-semibold uppercase tracking-wide text-gray-400">
                  Your custom systems
                </span>
                <span className="text-[10px] text-gray-300">{filteredCustom.length}</span>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {filteredCustom.map((ds) => {
                  const isSelected = ds.id === selectedId;
                  return (
                    <div key={ds.id} className="group relative inline-flex">
                      <button
                        type="button"
                        onClick={() => handleSelectCustom(ds)}
                        className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[12px] font-medium transition-all pr-8 ${
                          isSelected
                            ? "border-[#1B2A4A] bg-[#1B2A4A] text-white shadow-sm"
                            : "border-gray-200 bg-white text-gray-700 hover:border-gray-300 hover:bg-gray-50"
                        }`}
                      >
                        {isSelected && <Check className="h-2.5 w-2.5 flex-shrink-0" strokeWidth={3} />}
                        {ds.name}
                      </button>
                      <div className="absolute right-1 top-1/2 -translate-y-1/2 hidden group-hover:flex items-center gap-0.5">
                        <button
                          type="button"
                          onClick={(e) => { e.stopPropagation(); setEditingCustom(ds); setShowCustomModal(true); }}
                          className={`rounded p-0.5 transition-colors ${isSelected ? "text-white/70 hover:text-white" : "text-gray-400 hover:text-gray-700"}`}
                          title="Edit"
                        >
                          <Pencil className="h-2.5 w-2.5" />
                        </button>
                        <button
                          type="button"
                          onClick={(e) => { e.stopPropagation(); handleDeleteCustom(ds.id); }}
                          className={`rounded p-0.5 transition-colors ${isSelected ? "text-white/70 hover:text-white" : "text-gray-400 hover:text-red-500"}`}
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
              <div className="py-8 text-center text-[13px] text-gray-500">
                No design systems match <span className="font-medium">"{query}"</span>.
                <button type="button" onClick={() => setQuery("")} className="ml-2 text-[#1B2A4A] hover:underline">
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
            <div className="py-8 text-center text-[13px] text-gray-500">
              No design systems match <span className="font-medium">"{query}"</span>.
              <button type="button" onClick={() => setQuery("")} className="ml-2 text-[#1B2A4A] hover:underline">
                Clear
              </button>
            </div>
          )}
        </div>

        {/* ── Footer count ────────────────────────────────────────────── */}
        <div className="border-t border-gray-100 px-5 py-1.5">
          <span className="text-[10px] text-gray-400">
            {activeCategory === "Custom"
              ? `${customSystems.length} custom design system${customSystems.length !== 1 ? "s" : ""}`
              : `${totalVisible} design system${totalVisible !== 1 ? "s" : ""}${activeCategory !== "All" ? ` · ${activeCategory}` : ""}`
            }
          </span>
        </div>
      </div>
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
          <span className="text-[10px] font-semibold uppercase tracking-wide text-gray-400">{category}</span>
          <span className="text-[10px] text-gray-300">{items.length}</span>
        </div>
      )}
      <div className="flex flex-wrap gap-1.5">
        {items.map((ds) => {
          const isSelected = ds.id === selectedId;
          return (
            <button
              key={ds.id}
              type="button"
              onClick={() => onOpenDetail(ds)}
              title={ds.description || ds.name}
              className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[12px] font-medium transition-all hover:shadow-sm ${
                isSelected
                  ? "border-[#1B2A4A] bg-[#1B2A4A] text-white shadow-sm"
                  : "border-gray-200 bg-white text-gray-700 hover:border-gray-300 hover:bg-gray-50"
              }`}
            >
              {isSelected && <Check className="h-2.5 w-2.5 flex-shrink-0" strokeWidth={3} />}
              {ds.name}
            </button>
          );
        })}
      </div>
    </div>
  );
}
