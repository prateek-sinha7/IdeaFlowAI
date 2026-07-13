"use client";

import { useCallback, useState } from "react";
import { ArrowRight, ShieldCheck } from "lucide-react";
import { ReviewGatesSection } from "../ReviewGatesSection";
import type { AgentDef } from "@/types/index";
import { ConfigureCard, ConfigureOverlay } from "../ConfigureScreen";

/**
 * ReviewGatesAccordion — the Configure "Review Gates" summary card + its gate
 * manager overlay (mock `overlayGates`). Always present (every deliverable can
 * pause for review). The summary line reflects the LIVE gate count; the overlay
 * REUSES the shipped `ReviewGatesSection` body verbatim.
 */
export function ReviewGatesAccordion({
  agents,
  initialGateIds,
  onChange,
}: {
  agents: AgentDef[];
  initialGateIds?: string[];
  onChange: (gateAgentIds: string[], touched: boolean) => void;
}) {
  const [open, setOpen] = useState(false);
  const [count, setCount] = useState(initialGateIds?.length ?? 0);

  const handleChange = useCallback(
    (ids: string[], touched: boolean) => {
      setCount(ids.length);
      onChange(ids, touched);
    },
    [onChange],
  );

  const summary =
    count === 0
      ? "No agents pause for review"
      : `${count} agent${count === 1 ? "" : "s"} configured to pause for review`;

  return (
    <>
      <ConfigureCard
        testId="accordion-gates"
        icon={<ShieldCheck className="h-[17px] w-[17px]" />}
        title="Review Gates"
        summaryValue={summary}
        action={
          <button
            type="button"
            data-testid="configure-gates-open"
            onClick={() => setOpen(true)}
            className="inline-flex items-center gap-1.5 rounded-[9px] border border-line-border bg-surface-white px-3.5 py-2 text-[12px] font-semibold text-ink-700 transition-colors hover:border-brand hover:text-brand"
          >
            Open gate manager
            <ArrowRight className="h-3.5 w-3.5" />
          </button>
        }
      />
      <ConfigureOverlay
        open={open}
        onClose={() => setOpen(false)}
        title="Review gates"
        subtitle="Pause the pipeline after these agents to review before continuing."
        confirmLabel="Done"
      >
        <ReviewGatesSection agents={agents} onChange={handleChange} initialGateIds={initialGateIds} />
      </ConfigureOverlay>
    </>
  );
}
