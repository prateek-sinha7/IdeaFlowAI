"use client";

import { useMemo, useState } from "react";
import { Search, Check, X } from "lucide-react";
import type { DesignSystemListItem } from "@/lib/prototype-api";

interface DesignSystemPickerProps {
  systems: DesignSystemListItem[];
  selectedId: string | null;
  onSelect: (id: string | null) => void;
}

/**
 * Inline, always-visible design system picker.
 *
 * 150 systems grouped by category, rendered as compact chips directly on the
 * page — no trigger button, no popover that clips off-screen. Search filters
 * across name, category, and description in real time.
 */
export function DesignSystemPicker({ systems, selectedId, onSelect }: DesignSystemPickerProps) {
  const [query, setQuery] = useState("");

  const selected = useMemo(
    () => systems.find((s) => s.id === selectedId) ?? null,
    [systems, selectedId],
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

  return (
    <div className="rounded-2xl border border-gray-200/70 bg-white">
      {/* Header row */}
      <div className="flex items-center justify-between gap-4 border-b border-gray-100 px-5 py-4">
        <div>
          <h2 className="text-[15px] font-semibold text-gray-900">Choose a design system</h2>
          <p className="mt-0.5 text-[12px] text-gray-500">
            Sets the brand tokens — colors, typography, density. 150 brands available.
          </p>
        </div>

        {selected && (
          <div className="flex flex-shrink-0 items-center gap-2 rounded-lg border border-[#1B2A4A]/20 bg-[#1B2A4A]/5 px-3 py-1.5">
            <div className="flex h-5 w-5 items-center justify-center rounded-full bg-[#1B2A4A]">
              <Check className="h-2.5 w-2.5 text-white" strokeWidth={3} />
            </div>
            <span className="text-[12px] font-semibold text-[#1B2A4A]">{selected.name}</span>
            <button
              type="button"
              onClick={() => onSelect(null)}
              className="ml-0.5 text-[#1B2A4A]/50 hover:text-[#1B2A4A]"
              aria-label="Clear selection"
            >
              <X className="h-3 w-3" />
            </button>
          </div>
        )}
      </div>

      {/* Search */}
      <div className="border-b border-gray-100 px-5 py-3">
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search by brand, style, or category — e.g. 'apple', 'brutalist', 'fintech'…"
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
      <div className="max-h-[360px] overflow-y-auto px-5 py-4">
        {grouped.length === 0 ? (
          <div className="py-8 text-center text-[13px] text-gray-500">
            No design systems match <span className="font-medium">"{query}"</span>.
            <button
              type="button"
              onClick={() => setQuery("")}
              className="ml-2 text-[#1B2A4A] hover:underline"
            >
              Clear
            </button>
          </div>
        ) : (
          <div className="space-y-5">
            {grouped.map(([category, items]) => (
              <div key={category}>
                <div className="mb-2 flex items-center gap-2">
                  <span className="text-[10px] font-semibold uppercase tracking-wide text-gray-400">
                    {category}
                  </span>
                  <span className="text-[10px] text-gray-300">{items.length}</span>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {items.map((ds) => {
                    const isSelected = ds.id === selectedId;
                    return (
                      <button
                        key={ds.id}
                        type="button"
                        onClick={() => onSelect(isSelected ? null : ds.id)}
                        title={ds.description || ds.name}
                        className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[12px] font-medium transition-all ${
                          isSelected
                            ? "border-[#1B2A4A] bg-[#1B2A4A] text-white shadow-sm"
                            : "border-gray-200 bg-white text-gray-700 hover:border-gray-300 hover:bg-gray-50"
                        }`}
                      >
                        {isSelected && <Check className="h-2.5 w-2.5" strokeWidth={3} />}
                        {ds.name}
                      </button>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
