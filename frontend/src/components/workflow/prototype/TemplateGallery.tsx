"use client";

import { useMemo, useState } from "react";
import { Search } from "lucide-react";
import type { PrototypeTemplate } from "@/lib/prototype-api";
import { TemplateCard } from "./TemplateCard";

interface TemplateGalleryProps {
  templates: PrototypeTemplate[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

const ALL = "all";

export function TemplateGallery({ templates, selectedId, onSelect }: TemplateGalleryProps) {
  const [query, setQuery] = useState("");
  const [platform, setPlatform] = useState<string>(ALL);

  // Platform facets are derived from the data so filters never drift from
  // the catalogue. Filter to non-empty strings — some templates leave it null.
  const platforms = useMemo(() => {
    const set = new Set<string>();
    for (const t of templates) {
      if (t.platform) set.add(t.platform);
    }
    return [ALL, ...Array.from(set).sort()];
  }, [templates]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return templates.filter((t) => {
      if (platform !== ALL && t.platform !== platform) return false;
      if (!q) return true;
      // Match on name, description, and triggers — triggers carry the user's
      // own vocabulary ("kanban", "admin panel") that template names won't.
      const haystack = [
        t.name,
        t.description,
        ...(t.triggers || []),
      ]
        .join(" ")
        .toLowerCase();
      return haystack.includes(q);
    });
  }, [templates, query, platform]);

  return (
    <div className="flex flex-col gap-4">
      {/* Filter bar */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="relative flex-1 max-w-md">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search 43 templates by name, description, or trigger…"
            className="w-full rounded-lg border border-gray-200 bg-white py-2 pl-9 pr-3 text-[13px] text-gray-900 placeholder:text-gray-400 focus:border-gray-400 focus:outline-none"
          />
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          {platforms.map((p) => (
            <button
              key={p}
              type="button"
              onClick={() => setPlatform(p)}
              className={`rounded-full border px-3 py-1 text-[11px] font-medium capitalize transition-colors ${
                platform === p
                  ? "border-[#1B2A4A] bg-[#1B2A4A] text-white"
                  : "border-gray-200 bg-white text-gray-600 hover:border-gray-300"
              }`}
            >
              {p === ALL ? "All platforms" : p}
            </button>
          ))}
        </div>
      </div>

      {/* Result count */}
      <div className="text-[11px] text-gray-500">
        {filtered.length} {filtered.length === 1 ? "template" : "templates"}
        {(query || platform !== ALL) && ` matching your filters`}
      </div>

      {/* Grid */}
      {filtered.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-gray-200 bg-white/50 py-16 text-center">
          <p className="text-[13px] text-gray-600">No templates match your filters.</p>
          <button
            type="button"
            onClick={() => { setQuery(""); setPlatform(ALL); }}
            className="mt-2 text-[11px] font-medium text-[#1B2A4A] hover:underline"
          >
            Clear filters
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {filtered.map((template) => (
            <TemplateCard
              key={template.id}
              template={template}
              selected={template.id === selectedId}
              onSelect={onSelect}
            />
          ))}
        </div>
      )}
    </div>
  );
}
