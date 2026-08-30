"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { ChevronUp, ChevronDown, X, Lock } from "lucide-react";
import {
  AdvancedExpander,
  AgentPromptSection,
  getRole,
  getAgentInitials,
  hasToolOverride,
  type SelectionsMap,
  type StepSelection,
} from "../AgentsPopup";
import { AgentSkillsPicker } from "./AgentSkillsPicker";
import type { AgentDef, WorkflowType } from "@/types/index";

/** Compact a model id/label for the inline pill (mock: "Opus 4.5"). The full
 *  lever + catalog live in the reused AdvancedExpander below the row. */
function shortModel(model: string | undefined): string {
  if (!model) return "Default";
  const tail = model.split(/[.:/]/).filter(Boolean).pop() ?? model;
  return tail.length > 18 ? `${tail.slice(0, 18)}…` : tail;
}

/**
 * 41-04 — one reorderable agent row of the Composer Simple view (mock:
 * `Hexaware Composer.dc.html` agent pipeline row). The row header + Overrides
 * chips are the mock's presentation; the ACTUAL per-agent levers (Model /
 * Validator / Gate / Retry) and the Custom-prompt editor are the REUSED
 * `AdvancedExpander` (SelectionsMap) + `AgentPromptSection` — NOT re-implemented
 * (INV-3). Opening the config panel (via the model pill, an Overrides chip, or
 * "Custom prompt →") reveals those shared sub-components. Reorder uses the same
 * native HTML5 drag pattern as the modal, plus up/down buttons.
 */
export function AgentRow({
  agent,
  index,
  total,
  pipelineType,
  selection,
  onSelection,
  onSkillsChange,
  onMoveUp,
  onMoveDown,
  onRemove,
  // native drag-reorder (mirrors the AgentsPopup pattern)
  isDragOver = false,
  onDragStart,
  onDragOver,
  onDrop,
  onDragEnd,
}: {
  agent: AgentDef;
  index: number;
  total: number;
  pipelineType: WorkflowType;
  selection?: StepSelection;
  onSelection: (agentId: string, sel: StepSelection | undefined) => void;
  /** Spec 013 — per-agent skill picker write-through (mirrors Canvas R-01/R-36/R-38). */
  onSkillsChange?: (agentId: string, skills: string[]) => void;
  onMoveUp: () => void;
  onMoveDown: () => void;
  onRemove: () => void;
  isDragOver?: boolean;
  onDragStart?: () => void;
  onDragOver?: (e: React.DragEvent) => void;
  onDrop?: () => void;
  onDragEnd?: () => void;
}) {
  const [configOpen, setConfigOpen] = useState(false);
  const role = getRole(agent.id, pipelineType);
  const locked = role === "locked";
  const removable = role === "optional";
  const isFirst = index === 0;
  const isLast = index === total - 1;

  const validatorOn = (selection?.validators?.length ?? 0) > 0;
  // Ignore the auto-coupled `validation` gate when reflecting the Gate chip.
  const gateOn = (selection?.gates ?? []).some((g) => g !== "validation");
  const retryOn = (selection?.retry ?? 0) > 0;
  const skillsOn = (agent.skills?.length ?? 0) > 0;
  // ISS-274 — a tool grant switched off (here or in Canvas view) is an
  // override like any other, so the row flags it instead of hiding it.
  const toolsOn = hasToolOverride(selection);

  const chip = (label: string, on: boolean) => (
    <button
      key={label}
      type="button"
      onClick={() => setConfigOpen(true)}
      className={`inline-flex items-center gap-1.5 rounded-[7px] border px-2.5 py-1.5 font-sans text-[11px] font-semibold transition-colors ${
        on
          ? "border-ink-900 bg-ink-900 text-surface-white"
          : "border-line-control bg-surface-white text-ink-500 hover:border-line-faint"
      }`}
    >
      {label}
    </button>
  );

  return (
    <motion.div
      layout
      draggable={!locked}
      onDragStart={onDragStart}
      onDragOver={onDragOver}
      onDrop={onDrop}
      onDragEnd={onDragEnd}
      data-testid={`agent-row-${agent.id}`}
      className={`rounded-[13px] border bg-surface-card px-4 py-3.5 transition-colors ${
        isDragOver ? "border-brand-border" : "border-line-border"
      } ${!locked ? "cursor-grab active:cursor-grabbing" : ""}`}
    >
      <div className="flex items-center gap-3.5">
        {/* reorder */}
        <div className="flex flex-none flex-col gap-0.5">
          <button
            type="button"
            aria-label={`Move ${agent.name} up`}
            onClick={onMoveUp}
            disabled={isFirst}
            className="grid h-4 w-5 place-items-center rounded text-ink-300 disabled:text-line-faint enabled:hover:text-ink-700"
          >
            <ChevronUp className="h-3 w-3" />
          </button>
          <button
            type="button"
            aria-label={`Move ${agent.name} down`}
            onClick={onMoveDown}
            disabled={isLast}
            className="grid h-4 w-5 place-items-center rounded text-ink-300 disabled:text-line-faint enabled:hover:text-ink-700"
          >
            <ChevronDown className="h-3 w-3" />
          </button>
        </div>

        {/* index */}
        <span className="w-4 flex-none font-sans text-[11px] font-semibold tabular-nums text-ink-200">
          {String(index + 1).padStart(2, "0")}
        </span>

        {/* avatar */}
        <div
          className={`grid h-10 w-10 flex-none place-items-center rounded-[10px] font-sans text-[12px] font-semibold ${
            locked ? "bg-brand-fill text-brand" : "bg-line-faint-row text-ink-900"
          }`}
        >
          {getAgentInitials(agent.name)}
        </div>

        {/* name + role */}
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <p className="font-sans text-[13.5px] font-semibold leading-tight text-ink-900">
              {agent.name}
            </p>
            {locked && (
              <span className="inline-flex items-center gap-1 rounded-[5px] bg-line-faint-row px-1.5 py-[3px] font-sans text-[8px] font-semibold uppercase tracking-[0.05em] text-ink-400">
                <Lock className="h-2.5 w-2.5" />
                Core
              </span>
            )}
          </div>
          <p className="mt-0.5 font-serif text-[11.5px] leading-tight text-ink-400">
            {agent.role}
          </p>
        </div>

        {/* inline model picker (opens the reused lever panel below) */}
        <button
          type="button"
          aria-label={`Model for ${agent.name}`}
          onClick={() => setConfigOpen((v) => !v)}
          className="inline-flex flex-none items-center gap-1.5 rounded-[8px] border border-line-control bg-surface-white px-2.5 py-2 font-sans text-[11.5px] font-semibold text-ink-700 transition-colors hover:border-line-faint"
        >
          <span className="h-1.5 w-1.5 rounded-full bg-brand" />
          {shortModel(selection?.model)}
          <ChevronDown className="h-3 w-3 text-ink-200" />
        </button>

        {/* remove */}
        <button
          type="button"
          aria-label={`Remove ${agent.name}`}
          onClick={removable ? onRemove : undefined}
          disabled={!removable}
          title={removable ? "Remove agent" : "Core agents can't be removed"}
          className="grid h-7 w-7 flex-none place-items-center rounded-[7px] text-ink-200 enabled:hover:text-ink-500 disabled:cursor-not-allowed disabled:text-line-faint"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* Overrides chips + Custom prompt (mock's second row) */}
      <div className="mt-2.5 flex items-center gap-1.5 pl-[74px]">
        <span className="mr-0.5 font-sans text-[10px] font-medium text-ink-200">
          Overrides
        </span>
        {chip("Validator", validatorOn)}
        {chip("Gate", gateOn)}
        {chip("Retry", retryOn)}
        {chip("Skills", skillsOn)}
        {chip("Tools", toolsOn)}
        <span className="flex-1" />
        <button
          type="button"
          onClick={() => setConfigOpen((v) => !v)}
          className="font-sans text-[11px] font-medium text-brand"
        >
          Configure →
        </button>
      </div>

      {/* attached-skill chips — same delete-by-X affordance as the Canvas
          view's node card / rail, so removing a skill doesn't require opening
          the config panel. */}
      {skillsOn && (
        <div className="mt-2 flex flex-wrap items-center gap-1.5 pl-[74px]">
          {agent.skills!.map((skillId) => (
            <span
              key={skillId}
              className="inline-flex items-center gap-1 rounded-full border border-line-control bg-surface-white py-0.5 pl-2 pr-1 font-sans text-[11px] text-ink-700"
            >
              {skillId}
              <button
                type="button"
                aria-label={`Remove ${skillId}`}
                onClick={() =>
                  onSkillsChange?.(
                    agent.id,
                    (agent.skills ?? []).filter((s) => s !== skillId),
                  )
                }
                className="grid h-3.5 w-3.5 place-items-center rounded-full text-ink-300 hover:bg-line-faint hover:text-ink-700"
              >
                <X className="h-2.5 w-2.5" />
              </button>
            </span>
          ))}
        </div>
      )}

      {/* Config panel — the REUSED per-agent levers (SelectionsMap) + prompt
          editor. Not re-implemented (INV-3): AdvancedExpander is the single
          writer of this agent's selection, AgentPromptSection the prompt view. */}
      <AnimatePresence initial={false}>
        {configOpen && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.18 }}
            className="overflow-hidden"
          >
            <div className="mt-3 space-y-2 border-t border-line-faint-row pl-[74px] pt-3">
              <AdvancedExpander
                agents={[{ id: agent.id, name: agent.name }]}
                initialSelections={
                  selection ? ({ [agent.id]: selection } as SelectionsMap) : undefined
                }
                onSelectionsChange={(m) => onSelection(agent.id, m[agent.id])}
              />
              {/* Spec 013 — the SHARED skills picker (AgentSkillsPicker), also
                  used by the Canvas view's CanvasConfigRail, so the two views
                  can't drift (R-01/R-36/R-38). */}
              <AgentSkillsPicker agent={agent} onSkillsChange={onSkillsChange} />
              <AgentPromptSection agent={agent} surfaceOnly />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
