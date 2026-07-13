"use client";

import { ChevronDown } from "lucide-react";

/**
 * 41-04 — the Composer identity card (mock: `Hexaware Composer.dc.html` "Workflow"
 * card). Name + Description are editable; the Deliverable-type is READ-ONLY
 * (ND-AH) — `base_pipeline_type` is fixed at composer entry, so the mock's
 * editable dropdown becomes a static, non-interactive field. All colour/type is
 * routed through the @theme tokens (no raw hex).
 */
export function IdentityCard({
  name,
  description,
  deliverableLabel,
  onNameChange,
  onDescriptionChange,
}: {
  name: string;
  description: string;
  deliverableLabel: string;
  onNameChange: (v: string) => void;
  onDescriptionChange: (v: string) => void;
}) {
  return (
    <div className="mb-4 rounded-[14px] border border-line-border bg-surface-card px-[22px] py-5">
      <p className="mb-3.5 font-sans text-[10px] font-semibold uppercase tracking-[0.12em] text-ink-300">
        Workflow
      </p>

      <div className="grid grid-cols-1 gap-3.5 sm:grid-cols-2">
        {/* Name — editable */}
        <div>
          <label
            htmlFor="composer-wf-name"
            className="mb-1.5 block font-sans text-[11.5px] font-medium text-ink-400"
          >
            Name
          </label>
          <input
            id="composer-wf-name"
            value={name}
            onChange={(e) => onNameChange(e.target.value)}
            placeholder="Name your workflow"
            className="w-full rounded-[9px] border border-line-control bg-surface-white px-3.5 py-[11px] font-serif text-[13px] font-medium text-ink-800 outline-none transition-colors placeholder:text-ink-300 focus:border-line-faint"
          />
        </div>

        {/* Deliverable type — READ-ONLY (ND-AH). Rendered as a static field with
            the mock's chevron kept for visual parity but no interaction. */}
        <div>
          <p className="mb-1.5 font-sans text-[11.5px] font-medium text-ink-400">
            Deliverable type
          </p>
          <div
            data-testid="composer-deliverable-type"
            aria-readonly="true"
            className="flex items-center rounded-[9px] border border-line-control bg-surface-white px-3.5 py-[11px] font-serif text-[13px] text-ink-800"
          >
            {deliverableLabel}
            <span className="flex-1" />
            <ChevronDown className="h-3.5 w-3.5 text-ink-200" />
          </div>
        </div>
      </div>

      {/* Description — editable */}
      <div className="mt-3.5">
        <label
          htmlFor="composer-wf-description"
          className="mb-1.5 block font-sans text-[11.5px] font-medium text-ink-400"
        >
          Description
        </label>
        <textarea
          id="composer-wf-description"
          value={description}
          onChange={(e) => onDescriptionChange(e.target.value)}
          rows={2}
          placeholder="What does this workflow produce?"
          className="w-full resize-none rounded-[9px] border border-line-control bg-surface-white px-3.5 py-[11px] font-serif text-[13px] leading-relaxed text-ink-500 outline-none transition-colors placeholder:text-ink-300 focus:border-line-faint"
        />
      </div>
    </div>
  );
}
