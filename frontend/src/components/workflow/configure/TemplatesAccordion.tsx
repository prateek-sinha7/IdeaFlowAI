"use client";

import { useState } from "react";
import { ArrowRight, LayoutGrid } from "lucide-react";
import { TemplateGallery } from "../prototype/TemplateGallery";
import type { PrototypeTemplate } from "@/lib/prototype-api";
import { ConfigureCard, ConfigureOverlay } from "../ConfigureScreen";

/**
 * TemplatesAccordion — the Configure "Templates" summary card + its Browse
 * overlay (mock `overlayTemplate`). DECLARED-SIGNAL-GATED by the parent (ND-AE):
 * this only mounts when the deliverable declares `opendesign`. The summary line
 * binds to the LIVE registry selection and reads "None selected" until picked
 * (ND-AF) — never a fabricated value. The overlay REUSES the shipped
 * `TemplateGallery` body verbatim.
 */
export function TemplatesAccordion({
  templates,
  selectedId,
  customBody,
  onSelect,
}: {
  templates: PrototypeTemplate[];
  selectedId: string | null;
  customBody: string | null;
  onSelect: (id: string | null) => void;
}) {
  const [open, setOpen] = useState(false);
  const summary = customBody
    ? "Custom template"
    : (templates.find((t) => t.id === selectedId)?.name ?? "None selected");

  return (
    <>
      <ConfigureCard
        testId="accordion-templates"
        icon={<LayoutGrid className="h-[17px] w-[17px]" />}
        title="Templates"
        summaryLabel="Currently using:"
        summaryValue={summary}
        action={
          <button
            type="button"
            data-testid="configure-templates-browse"
            onClick={() => setOpen(true)}
            className="inline-flex items-center gap-1.5 rounded-[9px] border border-line-border bg-surface-white px-3.5 py-2 text-[12px] font-semibold text-ink-700 transition-colors hover:border-brand hover:text-brand"
          >
            Browse full library
            <ArrowRight className="h-3.5 w-3.5" />
          </button>
        }
      />
      <ConfigureOverlay
        open={open}
        onClose={() => setOpen(false)}
        title="Choose a template"
        subtitle="Sets the visual DNA — chrome, layout, components."
        confirmLabel="Use template"
      >
        <TemplateGallery
          templates={templates}
          selectedId={customBody ? null : selectedId}
          onSelect={(id) => onSelect(id)}
        />
      </ConfigureOverlay>
    </>
  );
}
