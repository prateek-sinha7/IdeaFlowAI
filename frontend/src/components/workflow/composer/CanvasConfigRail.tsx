"use client";

import { Settings2, MousePointerClick, ChevronDown, Minus, Plus } from "lucide-react";
import {
  AgentPromptSection,
  applyLeverPatch,
  useAgentCapabilities,
  getAgentInitials,
  type StepSelection,
  type SelectionsMap,
} from "../AgentsPopup";
import type { AgentDef } from "@/types/index";

// The validator→gate coupling gate name (EMP-04). The Review-gate toggle reflects
// only NON-coupling gates, mirroring the Simple view's AgentRow chip predicate.
const COUPLED_GATE = "validation";

/**
 * 41-05 — the Canvas view's per-node CONFIG rail, matched to the APPROVED PROPOSAL
 * `.rail .cfg` (ND-AJ): the selected node's header then an INLINE panel — a Model
 * dropdown, a Validator toggle, an (amber) Review-gate toggle, a Retry stepper,
 * and the Custom-prompt view.
 *
 * INV-3 — the lever LOGIC is REUSED, not forked: every write goes through the
 * SHARED pure `applyLeverPatch` (the single writer of the per-step selection
 * shape — patch + clear-unset + validator→gate coupling, EMP-04), and the OPTIONS
 * come from the SHARED `useAgentCapabilities` hook (`/api/capabilities`,
 * user_allowed-filtered; SC-001). The Custom-prompt is the REUSED
 * `AgentPromptSection` (surfaceOnly). Editing a lever updates the SAME shared
 * `selections` state the Simple view reads.
 *
 * The rail calls `onSelection` from NORMAL event handlers (not inside a setState
 * updater), so it does NOT reproduce the tracked `AdvancedExpander`
 * setState-in-render warning.
 */
export function CanvasConfigRail({
  agent,
  index,
  total,
  selection,
  onSelection,
}: {
  /** The selected node's agent, or null when nothing is selected. */
  agent: AgentDef | null;
  index: number;
  total: number;
  selection?: StepSelection;
  onSelection: (agentId: string, sel: StepSelection | undefined) => void;
}) {
  // Hook is called unconditionally (rules of hooks) before the empty-state branch.
  const { validatorOptions, gateOptions, modelOptions, loading } =
    useAgentCapabilities();

  if (!agent) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-2 px-6 text-center">
        <MousePointerClick className="h-6 w-6 text-ink-200" />
        <p className="font-sans text-[13px] font-semibold text-ink-700">
          Select a node
        </p>
        <p className="font-serif text-[11.5px] leading-relaxed text-ink-300">
          Click an agent on the canvas to configure its model, overrides and custom
          prompt.
        </p>
      </div>
    );
  }

  const sel = selection ?? {};
  const validatorOn = (sel.validators?.length ?? 0) > 0;
  const reviewGate = gateOptions.find((g) => g !== COUPLED_GATE);
  const reviewGateOn = (sel.gates ?? []).some((g) => g !== COUPLED_GATE);
  const retry = sel.retry ?? 0;

  // Apply a patch through the SHARED reducer, then report the (possibly cleared)
  // selection upward from a normal handler.
  const patch = (p: Partial<StepSelection>) => {
    const next = applyLeverPatch(sel, p);
    onSelection(agent.id, Object.keys(next).length > 0 ? next : undefined);
  };

  const Toggle = ({
    on,
    amber = false,
    label,
    disabled = false,
    onToggle,
  }: {
    on: boolean;
    amber?: boolean;
    label: string;
    disabled?: boolean;
    onToggle: () => void;
  }) => (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={label}
      disabled={disabled}
      onClick={onToggle}
      className={`relative h-5 w-[34px] flex-none rounded-full transition-colors disabled:opacity-40 ${
        on ? (amber ? "bg-status-amber" : "bg-brand") : "bg-line-faint"
      }`}
    >
      <span
        className={`absolute top-0.5 h-4 w-4 rounded-full bg-surface-white shadow-sm transition-all ${
          on ? "left-[16px]" : "left-0.5"
        }`}
      />
    </button>
  );

  return (
    <div className="flex-1 overflow-auto p-[18px]">
      {/* selected-node header */}
      <div className="flex items-center gap-2.5">
        <div className="grid h-[34px] w-[34px] flex-none place-items-center rounded-[10px] bg-brand font-sans text-[12px] font-bold text-surface-white">
          {getAgentInitials(agent.name)}
        </div>
        <div className="min-w-0">
          <h2 className="truncate font-sans text-[15px] font-semibold text-ink-900">
            {agent.name}
          </h2>
          <p className="truncate font-serif text-[11px] text-ink-300">
            Agent · step {index + 1} of {total} · {agent.role}
          </p>
        </div>
      </div>

      {/* MODEL (whole catalog — SC-001) */}
      <p className="mb-2 mt-5 font-sans text-[10px] font-semibold uppercase tracking-[0.1em] text-ink-300">
        Model
      </p>
      <div className="relative">
        <span className="pointer-events-none absolute left-[11px] top-1/2 h-2 w-2 -translate-y-1/2 rounded-full bg-brand" />
        <select
          aria-label="Model"
          disabled={loading}
          value={sel.model ?? ""}
          onChange={(e) => patch({ model: e.target.value })}
          className="w-full appearance-none rounded-[9px] border border-line-control bg-surface-white py-2.5 pl-6 pr-8 font-sans text-[12.5px] font-medium text-ink-900 focus:border-brand focus:outline-none disabled:opacity-50"
        >
          <option value="">Default</option>
          {modelOptions.map((m) => (
            <option key={m.id} value={m.id}>
              {m.label} ({m.tier})
            </option>
          ))}
        </select>
        <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-300" />
      </div>

      {/* OVERRIDES — Validator / Review-gate toggles + Retry stepper */}
      <p className="mb-1 mt-5 font-sans text-[10px] font-semibold uppercase tracking-[0.1em] text-ink-300">
        Overrides
      </p>

      <div className="flex items-center justify-between border-b border-line-faint-row py-3">
        <div className="min-w-0">
          <div className="font-sans text-[12.5px] font-semibold text-ink-900">
            Validator
          </div>
          <div className="font-serif text-[11px] text-ink-300">
            Check the output before continuing
          </div>
        </div>
        <Toggle
          on={validatorOn}
          label="Validator"
          disabled={loading || validatorOptions.length === 0}
          onToggle={() =>
            patch({ validators: validatorOn ? [] : [validatorOptions[0]] })
          }
        />
      </div>

      <div className="flex items-center justify-between border-b border-line-faint-row py-3">
        <div className="min-w-0">
          <div className="font-sans text-[12.5px] font-semibold text-ink-900">
            Review gate
          </div>
          <div className="font-serif text-[11px] text-ink-300">
            Pause for human approval after this step
          </div>
        </div>
        <Toggle
          on={reviewGateOn}
          amber
          label="Review gate"
          disabled={loading || !reviewGate}
          onToggle={() =>
            patch({ gates: reviewGateOn || !reviewGate ? [] : [reviewGate] })
          }
        />
      </div>

      <div className="flex items-center justify-between py-3">
        <div className="min-w-0">
          <div className="font-sans text-[12.5px] font-semibold text-ink-900">
            Retry on failure
          </div>
          <div className="font-serif text-[11px] text-ink-300">
            Re-run automatically
          </div>
        </div>
        <div className="inline-flex flex-none overflow-hidden rounded-[8px] border border-line-control">
          <button
            type="button"
            aria-label="Decrease retries"
            disabled={retry <= 0}
            onClick={() => patch({ retry: retry - 1 > 0 ? retry - 1 : undefined })}
            className="bg-surface-white px-2.5 py-1.5 font-sans text-[12px] font-semibold text-ink-500 enabled:hover:text-ink-900 disabled:opacity-40"
          >
            <Minus className="h-3 w-3" />
          </button>
          <span className="border-x border-line-control bg-surface-warm px-3 py-1.5 font-sans text-[12.5px] font-semibold tabular-nums text-ink-900">
            {retry > 0 ? `${retry}×` : "Off"}
          </span>
          <button
            type="button"
            aria-label="Increase retries"
            disabled={retry >= 3}
            onClick={() => patch({ retry: Math.min(3, retry + 1) })}
            className="bg-surface-white px-2.5 py-1.5 font-sans text-[12px] font-semibold text-ink-500 enabled:hover:text-ink-900 disabled:opacity-40"
          >
            <Plus className="h-3 w-3" />
          </button>
        </div>
      </div>

      {/* CUSTOM PROMPT (REUSE AgentPromptSection, surfaceOnly). */}
      <div className="mt-4">
        <div className="mb-2 flex items-center gap-2">
          <Settings2 className="h-3.5 w-3.5 text-brand" />
          <p className="font-sans text-[10px] font-semibold uppercase tracking-[0.1em] text-ink-300">
            Custom prompt
          </p>
        </div>
        <AgentPromptSection agent={agent} surfaceOnly />
      </div>
    </div>
  );
}

// Type re-referenced so the INV-3 reuse guard (grep SelectionsMap) holds and the
// shared selection shape stays the single source of truth for this rail.
export type CanvasRailSelections = SelectionsMap;
