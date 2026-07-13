"use client";

import { useState } from "react";
import { ArrowRight, Palette } from "lucide-react";
import { DesignSystemPicker } from "../prototype/DesignSystemPicker";
import type { DesignSystemListItem } from "@/lib/prototype-api";
import type { CustomDesignSystem } from "../prototype/CustomDesignSystemModal";
import { ConfigureCard, ConfigureOverlay } from "../ConfigureScreen";

/**
 * DesignSystemAccordion — the Configure "Design System" summary card + its Browse
 * overlay (mock `overlayDs`). DECLARED-SIGNAL-GATED by the parent (ND-AE). The
 * summary binds to the LIVE registry selection and reads "None selected" until
 * picked (ND-AF) — the mock's fabricated "Ink & Alabaster / 150 systems" is NEVER
 * cloned. The overlay REUSES the shipped `DesignSystemPicker` body verbatim.
 */
export function DesignSystemAccordion({
  systems,
  selectedId,
  customBody,
  onSelect,
  onSelectCustom,
}: {
  systems: DesignSystemListItem[];
  selectedId: string | null;
  customBody: string | null;
  onSelect: (id: string | null) => void;
  onSelectCustom: (ds: CustomDesignSystem | null) => void;
}) {
  const [open, setOpen] = useState(false);
  const summary = customBody
    ? "Custom system"
    : (systems.find((s) => s.id === selectedId)?.name ?? "None selected");

  return (
    <>
      <ConfigureCard
        testId="accordion-designsystem"
        icon={<Palette className="h-[17px] w-[17px]" />}
        title="Design System"
        summaryLabel="Currently using:"
        summaryValue={summary}
        action={
          <button
            type="button"
            data-testid="configure-ds-browse"
            onClick={() => setOpen(true)}
            className="inline-flex items-center gap-1.5 rounded-[9px] border border-line-border bg-surface-white px-3.5 py-2 text-[12px] font-semibold text-ink-700 transition-colors hover:border-brand hover:text-brand"
          >
            Browse all systems
            <ArrowRight className="h-3.5 w-3.5" />
          </button>
        }
      />
      <ConfigureOverlay
        open={open}
        onClose={() => setOpen(false)}
        title="Choose a design system"
        subtitle="Sets the brand tokens — colors, typography, and density."
        confirmLabel="Apply system"
      >
        <DesignSystemPicker
          systems={systems}
          selectedId={selectedId}
          onSelect={onSelect}
          onSelectCustom={onSelectCustom}
        />
      </ConfigureOverlay>
    </>
  );
}
