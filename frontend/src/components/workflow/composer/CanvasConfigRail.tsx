"use client";

import { Settings2, MousePointerClick } from "lucide-react";
import {
  AdvancedExpander,
  AgentPromptSection,
  getAgentInitials,
  type SelectionsMap,
  type StepSelection,
} from "../AgentsPopup";
import type { AgentDef } from "@/types/index";

/**
 * 41-05 — the Canvas view's per-node CONFIG rail (design-match to the APPROVED
 * PROPOSAL `.rail .cfg`, ND-AJ). Shows the selected node's header (avatar · name ·
 * step X of Y · role) then the per-agent Model / Validator / Gate / Retry levers
 * and the Custom-prompt view.
 *
 * INV-3: the levers + prompt are the REUSED `AdvancedExpander` (the single writer
 * of this agent's `SelectionsMap` entry) + `AgentPromptSection` (surfaceOnly) — the
 * SAME shared sub-components the Simple view's AgentRow binds to. They are NOT
 * re-implemented here; editing a lever updates the same shared `selections` state
 * the Simple view reads.
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

      {/* Configuration levers (REUSE AdvancedExpander — Model / Validator / Gate /
          Retry, the single writer of this agent's SelectionsMap entry). */}
      <div className="mt-5">
        <div className="mb-2 flex items-center gap-2">
          <Settings2 className="h-3.5 w-3.5 text-brand" />
          <p className="font-sans text-[10px] font-semibold uppercase tracking-[0.1em] text-ink-300">
            Model &amp; overrides
          </p>
        </div>
        <AdvancedExpander
          key={agent.id}
          agents={[{ id: agent.id, name: agent.name }]}
          initialSelections={
            selection ? ({ [agent.id]: selection } as SelectionsMap) : undefined
          }
          onSelectionsChange={(m) => onSelection(agent.id, m[agent.id])}
        />
      </div>

      {/* Custom prompt (REUSE AgentPromptSection, surfaceOnly). */}
      <div className="mt-5">
        <p className="mb-2 font-sans text-[10px] font-semibold uppercase tracking-[0.1em] text-ink-300">
          Custom prompt
        </p>
        <AgentPromptSection agent={agent} surfaceOnly />
      </div>
    </div>
  );
}
