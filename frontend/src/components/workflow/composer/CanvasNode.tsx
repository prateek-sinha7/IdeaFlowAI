"use client";

import { useState } from "react";
import { Lock, X, Plus, Pencil, Check } from "lucide-react";
import { getRole, getAgentInitials, type StepSelection } from "../AgentsPopup";
import type { AgentDef, WorkflowType } from "@/types/index";
import type { CapabilityModelEntry } from "@/lib/api";

/** The node's inline model pill — looks up the catalog's human label (parity
 *  with AgentRow's `modelOptions.find(...)`), NOT a naive id string-split: a
 *  raw Bedrock inference-profile id has both `.` and `:` separators, so
 *  splitting on them and taking the last segment produced garbage like `"0"`. */
function shortModel(model: string | undefined, modelOptions: CapabilityModelEntry[]): string {
  if (!model) return "Default";
  return modelOptions.find((m) => m.id === model)?.label ?? model;
}

/** Display-only: drop a trailing " Agent" to save card width — every stock
 *  agent name ends in it ("Domain Discovery Agent", "Backlog Architecture
 *  Agent"…), and it's the noun the whole card already conveys (role text +
 *  the avatar). The REAL `agent.name` is untouched — rename still edits and
 *  saves the full name, this only affects what's rendered here. */
function displayName(name: string): string {
  return name.replace(/\s+Agent$/i, "") || name;
}

/**
 * 41-05 — one agent NODE of the hand-rolled Canvas node-graph. A single, FLAT,
 * non-recursive absolute-positioned card (avatar · name · role · Core badge ·
 * model pill · override chips · ports). Positioned and rendered directly by
 * CanvasView from its flat tree-layout output (treeLayout.ts) — this component
 * owns no positioning or recursion of its own (moved out of a recursive
 * ChildrenRow so free-drag / edge-drag-to-reparent can hit-test every node
 * uniformly as one flat graph).
 */
export function CanvasNode({
  agent,
  pipelineType,
  selection,
  selected,
  isChild,
  hasChildren,
  cardWidth,
  left,
  top,
  onSelect,
  onRemove,
  onAddChild,
  onRename,
  onSkillsChange,
  onCardMouseDown,
  onPortMouseDown,
  modelOptions,
  addChildDisabledReason,
}: {
  agent: AgentDef;
  pipelineType: WorkflowType;
  selection?: StepSelection;
  selected: boolean;
  /** The shared model catalog (from `useAgentCapabilities`, lifted to
   *  CanvasView so every node reads the SAME fetched list instead of each
   *  node firing its own `/api/capabilities` call). */
  modelOptions: CapabilityModelEntry[];
  /** True for any nested (depth >= 1) node — shows the top-center incoming port. */
  isChild: boolean;
  hasChildren: boolean;
  cardWidth: number;
  left: number;
  top: number;
  onSelect: () => void;
  onRemove: () => void;
  onAddChild?: (parentId: string) => void;
  onRename?: (id: string, name: string) => void;
  onSkillsChange?: (agentId: string, skills: string[]) => void;
  /** Free-drag: mousedown anywhere on the card body (not the top port, that's
   *  reserved for edge-drag-to-reparent). */
  onCardMouseDown?: (e: React.MouseEvent) => void;
  /** Edge-drag-to-reparent: mousedown specifically on the top (incoming) port. */
  onPortMouseDown?: (e: React.MouseEvent) => void;
  /** Only 3 levels of nesting are supported (root → parent → child) and each
   *  parent may hold at most 8 direct sub-agents. When set, the "+ Sub-agent"
   *  button is disabled and shows this as its tooltip instead of silently
   *  doing nothing. */
  addChildDisabledReason?: string;
}) {
  const role = getRole(agent.id, pipelineType);
  const locked = role === "locked";
  const removable = role === "optional";

  const [renaming, setRenaming] = useState(false);
  const [draftName, setDraftName] = useState(agent.name);

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

  const port = (side: "l" | "r" | "t" | "b", handlers?: { onMouseDown?: (e: React.MouseEvent) => void }) => (
    <span
      aria-hidden={!handlers}
      onMouseDown={handlers?.onMouseDown}
      className={`absolute h-[11px] w-[11px] rounded-full border-2 bg-surface-card ${
        selected ? "border-brand" : "border-line-faint"
      } ${handlers ? "cursor-crosshair hover:scale-125 hover:border-brand" : ""} ${
        side === "l"
          ? "top-1/2 -left-[6px] -translate-y-1/2"
          : side === "r"
            ? "top-1/2 -right-[6px] -translate-y-1/2"
            : side === "t"
              ? "-top-[6px] left-1/2 -translate-x-1/2"
              : "-bottom-[6px] left-1/2 -translate-x-1/2"
      }`}
    />
  );

  const commitRename = () => {
    const next = draftName.trim();
    if (next && next !== agent.name) onRename?.(agent.id, next);
    setRenaming(false);
  };

  return (
    <div
      style={{ left, top, width: cardWidth }}
      className="absolute z-[3]"
      data-testid={`canvas-node-wrap-${agent.id}`}
    >
      <div
        role="button"
        tabIndex={0}
        data-testid={`canvas-node-${agent.id}`}
        data-selected={selected ? "true" : "false"}
        onClick={onSelect}
        onMouseDown={onCardMouseDown}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            onSelect();
          }
        }}
        className={`relative cursor-pointer rounded-[14px] border bg-surface-card px-3 pb-[11px] pt-3 shadow-[0_1px_2px_rgba(17,17,20,0.04)] transition-shadow ${
          selected
            ? "border-brand shadow-[0_0_0_3px_var(--brand-fill),0_8px_22px_rgba(60,44,218,0.14)]"
            : "border-line-border hover:border-line-faint"
        }`}
      >
        {port("l")}
        {port("r")}
        {isChild && port("t", { onMouseDown: onPortMouseDown })}
        {hasChildren && port("b")}

        {/* rename + remove — grouped top-right so the title below gets the
            card's FULL width instead of sharing its row with the pencil. */}
        <div className="absolute right-2 top-2 z-[1] flex items-center gap-1">
          {onRename && !renaming && (
            <button
              type="button"
              aria-label={`Rename ${agent.name}`}
              onClick={(e) => {
                e.stopPropagation();
                setDraftName(agent.name);
                setRenaming(true);
              }}
              title={`Rename ${agent.name}`}
              data-testid={`canvas-rename-${agent.id}`}
              className="grid h-5 w-5 place-items-center rounded-[6px] text-ink-400 hover:bg-line-faint-row hover:text-ink-700"
            >
              <Pencil className="h-3 w-3" />
            </button>
          )}
          <button
            type="button"
            aria-label={`Remove ${agent.name}`}
            title={removable ? "Remove agent" : "Core agents can't be removed"}
            disabled={!removable}
            onClick={(e) => {
              e.stopPropagation();
              if (removable) onRemove();
            }}
            className="grid h-5 w-5 place-items-center rounded-[6px] text-ink-200 enabled:hover:text-ink-500 disabled:cursor-not-allowed disabled:opacity-0"
          >
            <X className="h-3 w-3" />
          </button>
        </div>

        {/* header: avatar · name (inline-renamable) · role.
            `pr-11` reserves the strip the absolute rename+remove cluster
            above occupies (2 × 20px icons + gap) so the title never renders
            underneath it. While renaming the pencil itself is hidden (only
            × remains), so the reservation drops to `pr-6` — one icon's worth
            — freeing that space for the rename input instead of leaving it
            empty. */}
        <div className={`flex items-center gap-2.5 ${renaming ? "pr-6" : "pr-11"}`}>
          <div
            className={`grid h-[30px] w-[30px] flex-none place-items-center rounded-[9px] font-sans text-[11px] font-bold ${avatarCls}`}
          >
            {getAgentInitials(agent.name)}
          </div>
          <div className="min-w-0 flex-1">
            {renaming ? (
              <div
                className="flex items-center gap-1"
                onClick={(e) => e.stopPropagation()}
                onMouseDown={(e) => e.stopPropagation()}
                onKeyDown={(e) => e.stopPropagation()}
              >
                <input
                  aria-label={`Rename ${agent.name}`}
                  autoFocus
                  value={draftName}
                  onChange={(e) => setDraftName(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") commitRename();
                    if (e.key === "Escape") {
                      setDraftName(agent.name);
                      setRenaming(false);
                    }
                  }}
                  className="min-w-0 flex-1 rounded-[6px] border border-brand bg-surface-white px-1.5 py-0.5 font-sans text-[12.5px] font-semibold text-ink-900 focus:outline-none"
                />
                <button
                  type="button"
                  aria-label="Confirm rename"
                  onClick={commitRename}
                  className="grid h-5 w-5 flex-none place-items-center rounded-[5px] text-brand hover:bg-brand-fill"
                >
                  <Check className="h-3 w-3" />
                </button>
              </div>
            ) : (
              // The pencil now lives in the top-right rename+remove cluster
              // (not inline here), so the title gets the row's FULL width.
              // Single line, not a wrap: dropping the " Agent" suffix
              // (displayName) plus the wider card means every stock name
              // fits on one line now — truncate is a safety net for an
              // unusually long CUSTOM name, not the common case.
              <h3
                onDoubleClick={(e) => {
                  if (!onRename) return;
                  e.stopPropagation();
                  setDraftName(agent.name);
                  setRenaming(true);
                }}
                className="w-full truncate font-sans text-[13px] font-semibold leading-[1.15] tracking-[-0.01em] text-ink-900"
              >
                {displayName(agent.name)}
              </h3>
            )}
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
          {shortModel(selection?.model, modelOptions)}
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

        {/* attached-skill chips — same delete-by-X affordance as the rail's
            Overview tab, so removing a skill doesn't require opening it. */}
        {(agent.skills?.length ?? 0) > 0 && (
          <div className="mt-2.5 flex flex-wrap gap-1.5">
            {agent.skills!.map((skillId) => (
              <span
                key={skillId}
                className="inline-flex items-center gap-1 rounded-full border border-line-control bg-surface-white py-0.5 pl-2 pr-1 font-sans text-[10px] text-ink-700"
              >
                {skillId}
                {onSkillsChange && (
                  <button
                    type="button"
                    aria-label={`Remove ${skillId}`}
                    onClick={(e) => {
                      e.stopPropagation();
                      onSkillsChange(
                        agent.id,
                        (agent.skills ?? []).filter((s) => s !== skillId),
                      );
                    }}
                    className="grid h-3 w-3 place-items-center rounded-full text-ink-300 hover:bg-line-faint hover:text-ink-700"
                  >
                    <X className="h-2 w-2" />
                  </button>
                )}
              </span>
            ))}
          </div>
        )}

        {/* + Add sub-agent (R-35) — disabled once this node hits the 3-level
            nesting cap or its own 8-sub-agent sibling cap, with the SAME
            styled hover-tooltip box the rail's "i" icons use (not a plain
            native `title=`) so every cap reason in the canvas reads the
            same way. */}
        {onAddChild && (
          <span className="group relative mt-2.5 block">
            <button
              type="button"
              aria-label={`Add sub-agent to ${agent.name}`}
              disabled={!!addChildDisabledReason}
              onMouseDown={(e) => e.stopPropagation()}
              onClick={(e) => {
                e.stopPropagation();
                onAddChild(agent.id);
              }}
              className="flex w-full items-center justify-center gap-1 rounded-[7px] border border-dashed border-line-control py-1 font-sans text-[10.5px] font-semibold text-ink-300 enabled:hover:border-brand enabled:hover:text-brand disabled:cursor-not-allowed disabled:opacity-70"
            >
              <Plus className="h-3 w-3" />
              Sub-agent
            </button>
            {addChildDisabledReason && (
              <span
                role="tooltip"
                className="pointer-events-none absolute left-1/2 top-full z-20 mt-1.5 w-[190px] -translate-x-1/2 rounded-[8px] border border-line-control bg-surface-card px-2.5 py-2 text-center font-sans text-[11px] normal-case tracking-normal leading-relaxed text-ink-700 opacity-0 shadow-lg transition-opacity group-hover:opacity-100"
              >
                {addChildDisabledReason}
              </span>
            )}
          </span>
        )}
      </div>
    </div>
  );
}
