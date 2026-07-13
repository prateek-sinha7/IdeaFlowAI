"use client";

import { Lock, X } from "lucide-react";
import { getRole, getAgentInitials, type StepSelection } from "../AgentsPopup";
import type { AgentDef, WorkflowType } from "@/types/index";

/** Compact a model id/label for the node's inline model pill (mirrors AgentRow). */
function shortModel(model: string | undefined): string {
  if (!model) return "Default";
  const tail = model.split(/[.:/]/).filter(Boolean).pop() ?? model;
  return tail.length > 16 ? `${tail.slice(0, 16)}…` : tail;
}

/**
 * 41-05 — one agent NODE of the hand-rolled Canvas node-graph (design-match to
 * the APPROVED PROPOSAL `composer-canvas-proposal.html` `.node`, ND-AJ). An
 * absolute-positioned ~178px card: avatar · name · role · Core badge (getRole) ·
 * model pill · Validator/Gate/Retry override chips (on/gate states derived from
 * the shared `SelectionsMap`) · left/right ports. Clicking the card selects it
 * (brand ring) → the right config rail binds to this agent's levers. Remove takes
 * it out of `pipelineAgents` (optional agents only; Core agents can't be removed).
 * Pure presentation bound to the shared data model — NO graph library.
 */
export function CanvasNode({
  agent,
  pipelineType,
  selection,
  selected,
  onSelect,
  onRemove,
  left,
  top,
  width,
}: {
  agent: AgentDef;
  pipelineType: WorkflowType;
  selection?: StepSelection;
  selected: boolean;
  onSelect: () => void;
  onRemove: () => void;
  left: number;
  top: number;
  width: number;
}) {
  const role = getRole(agent.id, pipelineType);
  const locked = role === "locked";
  const removable = role === "optional";

  const validatorOn = (selection?.validators?.length ?? 0) > 0;
  // Ignore the auto-coupled `validation` gate when reflecting the Gate chip
  // (parity with the Simple view's AgentRow).
  const gateOn = (selection?.gates ?? []).some((g) => g !== "validation");
  const retry = selection?.retry ?? 0;
  const retryOn = retry > 0;

  const avatarCls = selected
    ? "bg-brand text-surface-white"
    : locked
      ? "bg-brand-fill text-brand"
      : "bg-line-faint-row text-ink-500";

  const port = (side: "l" | "r") => (
    <span
      aria-hidden
      className={`absolute top-1/2 h-[11px] w-[11px] -translate-y-1/2 rounded-full border-2 bg-surface-card ${
        selected ? "border-brand" : "border-line-faint"
      } ${side === "l" ? "-left-[6px]" : "-right-[6px]"}`}
    />
  );

  return (
    <div
      role="button"
      tabIndex={0}
      data-testid={`canvas-node-${agent.id}`}
      data-selected={selected ? "true" : "false"}
      onClick={onSelect}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelect();
        }
      }}
      style={{ left, top, width }}
      className={`absolute z-[3] cursor-pointer rounded-[14px] border bg-surface-card px-3 pb-[11px] pt-3 shadow-[0_1px_2px_rgba(17,17,20,0.04)] transition-shadow ${
        selected
          ? "border-brand shadow-[0_0_0_3px_var(--brand-fill),0_8px_22px_rgba(60,44,218,0.14)]"
          : "border-line-border hover:border-line-faint"
      }`}
    >
      {port("l")}
      {port("r")}

      {/* remove (top-right) — optional agents only; never selects the node */}
      <button
        type="button"
        aria-label={`Remove ${agent.name}`}
        title={removable ? "Remove agent" : "Core agents can't be removed"}
        disabled={!removable}
        onClick={(e) => {
          e.stopPropagation();
          if (removable) onRemove();
        }}
        className="absolute right-2 top-2 grid h-5 w-5 place-items-center rounded-[6px] text-ink-200 enabled:hover:text-ink-500 disabled:cursor-not-allowed disabled:opacity-0"
      >
        <X className="h-3 w-3" />
      </button>

      {/* header: avatar · name · role */}
      <div className="flex items-center gap-2.5">
        <div
          className={`grid h-[30px] w-[30px] flex-none place-items-center rounded-[9px] font-sans text-[11px] font-bold ${avatarCls}`}
        >
          {getAgentInitials(agent.name)}
        </div>
        <div className="min-w-0">
          <h3 className="truncate font-sans text-[13px] font-semibold leading-[1.15] tracking-[-0.01em] text-ink-900">
            {agent.name}
          </h3>
          <p className="mt-px truncate font-serif text-[10.5px] leading-tight text-ink-300">
            {agent.role}
          </p>
        </div>
      </div>

      {/* Core badge (getRole) */}
      {locked && (
        <span className="mt-2 inline-flex items-center gap-1 rounded-[5px] border border-line-control px-1 py-0.5 font-sans text-[8px] font-bold uppercase tracking-[0.05em] text-ink-500">
          <Lock className="h-2.5 w-2.5" />
          Core
        </span>
      )}

      {/* model pill */}
      <div className="mt-2.5 inline-flex items-center gap-1.5 rounded-[7px] border border-line-control bg-surface-warm px-2 py-1.5 font-sans text-[11px] text-ink-700">
        <span className="h-[7px] w-[7px] rounded-full bg-brand" />
        {shortModel(selection?.model)}
      </div>

      {/* override chips — Validator (brand) · Gate (amber) · Retry (brand) */}
      <div className="mt-2.5 flex gap-1.5">
        <span
          className={`rounded-[6px] border px-1.5 py-1 font-sans text-[9.5px] font-semibold ${
            validatorOn
              ? "border-brand-border bg-brand-fill text-brand"
              : "border-line-faint-row bg-surface-white text-ink-300"
          }`}
        >
          Validator
        </span>
        <span
          className={`rounded-[6px] border px-1.5 py-1 font-sans text-[9.5px] font-semibold ${
            gateOn
              ? "border-status-amber-border bg-status-amber-fill text-status-amber"
              : "border-line-faint-row bg-surface-white text-ink-300"
          }`}
        >
          Gate
        </span>
        <span
          className={`rounded-[6px] border px-1.5 py-1 font-sans text-[9.5px] font-semibold ${
            retryOn
              ? "border-brand-border bg-brand-fill text-brand"
              : "border-line-faint-row bg-surface-white text-ink-300"
          }`}
        >
          {retryOn ? `Retry ·${retry}` : "Retry"}
        </span>
      </div>
    </div>
  );
}
