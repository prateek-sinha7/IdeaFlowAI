"use client";

import { useState } from "react";
import { ArrowRight, SlidersHorizontal } from "lucide-react";
import { AdvancedExpander, type SelectionsMap } from "../AgentsPopup";
import { ConfigureCard, ConfigureOverlay } from "../ConfigureScreen";

/**
 * WorkflowSettingsAccordion — the Configure "Workflow Settings" summary card + its
 * "Workflow configuration" overlay (mock `modalWorkflow`). Always present. The
 * summary reflects the LIVE agent count (never the mock's fabricated
 * "1 skill · 8 capabilities" — ND-AF). The overlay REUSES the shipped
 * `AdvancedExpander` body verbatim — the per-step Validator/Gate/Model/Retry levers
 * that report the compact `SelectionsMap` upward.
 */
export function WorkflowSettingsAccordion({
  agents,
  agentCount,
  onSelectionsChange,
  initialSelections,
}: {
  agents: { id: string; name: string }[];
  agentCount: number;
  onSelectionsChange: (selections: SelectionsMap) => void;
  initialSelections: SelectionsMap;
}) {
  const [open, setOpen] = useState(false);
  const summary = `${agentCount} agent${agentCount === 1 ? "" : "s"} · per-step levers`;

  return (
    <>
      <ConfigureCard
        testId="accordion-settings"
        icon={<SlidersHorizontal className="h-[17px] w-[17px]" />}
        title="Workflow Settings"
        summaryValue={summary}
        action={
          <button
            type="button"
            data-testid="configure-settings-open"
            onClick={() => setOpen(true)}
            className="inline-flex items-center gap-1.5 rounded-[9px] px-3.5 py-2 text-[12px] font-semibold text-brand transition-colors hover:text-brand-pressed"
          >
            Open
            <ArrowRight className="h-3.5 w-3.5" />
          </button>
        }
      />
      <ConfigureOverlay
        open={open}
        onClose={() => setOpen(false)}
        eyebrow="Advanced"
        title="Workflow configuration"
        confirmLabel="Save changes"
      >
        <AdvancedExpander
          agents={agents}
          onSelectionsChange={onSelectionsChange}
          initialSelections={initialSelections}
        />
      </ConfigureOverlay>
    </>
  );
}
