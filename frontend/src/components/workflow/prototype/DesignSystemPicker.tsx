"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Search, Check, X, Plus, Pencil, Trash2 } from "lucide-react";
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
  /** Called when a custom DS is selected — passes the body so the pipeline can use it */
  onSelectCustom: (ds: CustomDesignSystem | null) => void;
}

export function DesignSystemPicker({
  systems,
  selectedId,
  onSelect,
  onSelectCustom,
}: DesignSystemPickerProps) {
  const [query, setQuery] = useState("");
  const [detailSystem, setDetailSystem] = useState<DesignSystemListItem | null>(null);
  const [customSystems, setCustomSystems] = useState<CustomDesignSystem[]>([]);
  const [showCustomModal, setShowCustomModal] = useState(false);
  const [editingCustom, setEditingCustom] = useState<CustomDesignSystem | undefined>(undefined);

  // Load custom systems from localStorage on mount
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

  const grouped = useMemo(() => {
    const q = query.trim().toLowerCase();
    const filtered = systems.filter((s) => {
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
    return Array.from(map.entries()).sort(([a], [b]) => a.localeCompare(b));
  }, [systems, query]);

  const filteredCustom = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return customSystems;
    return customSystems.filter((s) => s.name.toLowerCase().includes(q));
  }, [customSystems, query]);

  const handleSaveCustom = (ds: CustomDesignSystem) => {
    setCustomSystems((prev) => {
      const without = prev.filter((s) => s.id !== ds.id);
      const next = [ds, ...without];
      saveCustomDesignSystems(next);
      return next;
    });
    // Auto-select the newly saved custom DS
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
    onSelectCustom(null); // clear any custom selection
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

  return (
    <>
      {/* Built-in DS detail modal */}
      {detailSystem && (
        <DesignSystemDetailModal
          system={detailSystem}
          isSelected={detailSystem.id === selectedId}
          onSelect={handleSelectBuiltIn}
          onClose={() => setDetailSystem(null)}
        />
      )}

      {/* Custom DS create/edit modal */}
      {showCustomModal && (
        <CustomDesignSystemModal
          existing={editingCustom}
          onSave={handleSaveCustom}
          onClose={() => { setShowCustomModal(false); setEditingCustom(undefined); }}
        />
      )}

      <div className="rounded-2xl border border-gray-200/70 bg-white">
        {/* Header */}
        <div className="flex items-center justify-between gap-4 border-b border-gray-100 px-5 py-4">
          <div>
            <h2 className="text-[15px] font-semibold text-gray-900">Choose a design system</h2>
            <p className="mt-0.5 text-[12px] text-gray-500">
              Sets the brand tokens — colors, typography, density. Click any chip to preview the full spec.
            </p>
          </div>

          <div className="flex flex-shrink-0 items-center gap-2">
            {/* Selected badge */}
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

            {/* Add custom button */}
            <button
              type="button"
              onClick={() => { setEditingCustom(undefined); setShowCustomModal(true); }}
              className="flex items-center gap-1.5 rounded-lg border border-dashed border-gray-300 bg-white px-3 py-1.5 text-[12px] font-medium text-gray-600 hover:border-[#1B2A4A] hover:text-[#1B2A4A] transition-colors"
            >
              <Plus className="h-3 w-3" />
              Add custom
            </button>
          </div>
        </div>

        {/* Search */}
        <div className="border-b border-gray-100 px-5 py-3">
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

        {/* Grouped chips */}
        <div className="max-h-[360px] overflow-y-auto px-5 py-4 space-y-5">

          {/* ── Custom design systems ─────────────────────────────────── */}
          {filteredCustom.length > 0 && (
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
                      {/* Edit / delete actions */}
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

          {/* ── Built-in design systems ───────────────────────────────── */}
          {grouped.length === 0 && filteredCustom.length === 0 ? (
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
                items={items}
                selectedId={selectedId}
                onSelect={handleSelectBuiltIn}
                onOpenDetail={setDetailSystem}
              />
            ))
          )}
        </div>
      </div>
    </>
  );
}

// ── Group ─────────────────────────────────────────────────────────────────

interface GroupProps {
  category: string;
  items: DesignSystemListItem[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onOpenDetail: (system: DesignSystemListItem) => void;
}

function DesignSystemGroup({ category, items, selectedId, onSelect, onOpenDetail }: GroupProps) {
  const ref = useRef<HTMLDivElement>(null);
  return (
    <div ref={ref}>
      <div className="mb-2 flex items-center gap-2">
        <span className="text-[10px] font-semibold uppercase tracking-wide text-gray-400">{category}</span>
        <span className="text-[10px] text-gray-300">{items.length}</span>
      </div>
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
