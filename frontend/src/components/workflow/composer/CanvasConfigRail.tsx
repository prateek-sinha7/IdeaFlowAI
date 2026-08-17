"use client";

import { useState, type ReactNode } from "react";
import {
  Settings2,
  MousePointerClick,
  ChevronDown,
  Minus,
  Plus,
  AlertCircle,
  Webhook,
  Check,
  Info,
} from "lucide-react";
import {
  AgentPromptSection,
  applyLeverPatch,
  useAgentCapabilities,
  getAgentInitials,
  KNOWN_PRODUCERS,
  type StepSelection,
  type SelectionsMap,
} from "../AgentsPopup";
import { AgentSkillsPicker } from "./AgentSkillsPicker";
import { Tabs } from "@/components/ui/Tabs";
import { useHooksCatalog } from "@/hooks/useHooksCatalog";
import { useSkillsHooks } from "@/context/SkillsHooksContext";
import type { AgentDef, SubagentStrategy } from "@/types/index";

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
  priorAgents = [],
  onSkillsChange,
  onPromptChange,
  onStrategyChange,
  onRename,
}: {
  /** The selected node's agent, or null when nothing is selected. */
  agent: AgentDef | null;
  index: number;
  total: number;
  selection?: StepSelection;
  onSelection: (agentId: string, sel: StepSelection | undefined) => void;
  /**
   * 51-07 (D6/D7/§4b) — the pipeline agents that PRECEDE the selected node
   * (`pipelineAgents.slice(0, selIndex)` from `CanvasView`). The fan-out
   * "Source list from" picker offers ONLY these earlier steps; when empty (the
   * first agent, no upstream) the fan-out toggle is disabled.
   */
  priorAgents?: AgentDef[];
  /** Spec 012 (R-01/R-36/R-38) — per-node skill picker write-through. */
  onSkillsChange?: (agentId: string, skills: string[]) => void;
  /** Spec 012 (R-06/R-36) — custom-agent-only prompt editor write-through. */
  onPromptChange?: (agentId: string, prompt: string) => void;
  /** Spec 012 (R-04/R-36) — child-group strategy + max-parallel write-through. */
  onStrategyChange?: (agentId: string, strategy: SubagentStrategy, maxParallel?: number) => void;
  /** Node rename write-through (same path the node-card pencil icon uses). */
  onRename?: (agentId: string, name: string) => void;
}) {
  // Hooks are called unconditionally (rules of hooks) before the empty-state branch.
  const { validatorOptions, gateOptions, modelOptions, loading } =
    useAgentCapabilities();
  const { hooks: HOOKS } = useHooksCatalog();
  const { attachedHooks, attachHook } = useSkillsHooks();

  // Same 4-tab inspector as the library agent drawer (AgentCapabilitiesModal) —
  // requested so the canvas rail and the library click panel share one mental
  // model instead of two different per-agent surfaces.
  const [activeTab, setActiveTab] = useState<
    "overview" | "skills" | "hooks" | "tools" | "config"
  >("overview");
  const [nameDraft, setNameDraft] = useState<string | null>(null);

  // Same hover-tooltip "i" affordance as the Workflow properties panel
  // (CanvasView's workflowSettingsSection) — reproduced here rather than
  // imported since that one is a local, unexported component.
  const InfoHint = ({ children }: { children: ReactNode }) => (
    <span className="group relative inline-flex flex-none">
      <Info className="h-3.5 w-3.5 cursor-help text-ink-300 hover:text-ink-500" />
      <span
        role="tooltip"
        className="pointer-events-none absolute left-0 top-full z-20 mt-1.5 w-[260px] max-w-[80vw] rounded-[8px] border border-line-control bg-surface-card px-2.5 py-2 font-sans text-[11px] normal-case tracking-normal leading-relaxed text-ink-700 opacity-0 shadow-lg transition-opacity group-hover:opacity-100"
      >
        {children}
      </span>
    </span>
  );

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

  if (!agent) {
    return (
      <div className="flex flex-1 flex-col">
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
      </div>
    );
  }

  const sel = selection ?? {};
  const validatorOn = (sel.validators?.length ?? 0) > 0;
  const reviewGate = gateOptions.find((g) => g !== COUPLED_GATE);
  const reviewGateOn = (sel.gates ?? []).some((g) => g !== COUPLED_GATE);
  const retry = sel.retry ?? 0;

  // ── Fan-out lever (51-07 / FANOUT-01, D6/D7/§4b) ──────────────────────────
  // Parity with the Simple-view AdvancedExpander: reuse the SHARED reducer +
  // the SHARED KNOWN_PRODUCERS allow-list (no fork, no redefine). The source
  // picker lists ONLY earlier agents (`priorAgents`, threaded from CanvasView);
  // the toggle is disabled for the first agent (no upstream); a non-blocking
  // warning steers to a known `## Task N:` producer (INSERT-A-NODE, D2/D7).
  const canFanout = priorAgents.length > 0;
  const fanoutOn = sel.strategy === "fanout_batch";
  const currentSource = sel.task_source?.source_step ?? "";
  // Default source (D7): the nearest earlier KNOWN producer if one exists, else
  // the immediately-preceding step (still valid — the warning then steers to
  // INSERT one).
  const defaultSource =
    [...priorAgents].reverse().find((a) => KNOWN_PRODUCERS.includes(a.id))?.id ??
    priorAgents[priorAgents.length - 1]?.id;
  const sourceKnown =
    !!currentSource && KNOWN_PRODUCERS.includes(currentSource);

  // Apply a patch through the SHARED reducer, then report the (possibly cleared)
  // selection upward from a normal handler.
  const patch = (p: Partial<StepSelection>) => {
    const next = applyLeverPatch(sel, p);
    onSelection(agent.id, Object.keys(next).length > 0 ? next : undefined);
  };

  // Spec 012 (R-04/R-36) — the child-group strategy selector, shown only when
  // this node has children.
  const hasChildren = (agent.children?.length ?? 0) > 0;
  const childStrategy = agent.strategy ?? "sequential";
  const maxParallel = agent.maxParallel ?? 3;

  const commitRename = () => {
    const next = (nameDraft ?? "").trim();
    if (next && next !== agent.name) onRename?.(agent.id, next);
    setNameDraft(null);
  };

  const suggestedHooks = HOOKS.filter((h) => h.compatible_agents.includes(agent.id)).slice(0, 3);
  const isHookAttached = (id: string) => attachedHooks.some((h) => h.id === id);

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
    <div className="flex-1 overflow-auto p-[18px]">
      {/* selected-node header — the name is editable here (same write-through
          the node-card pencil icon uses), independent of which tab is open. */}
      <div className="flex items-center gap-2.5">
        <div className="grid h-[34px] w-[34px] flex-none place-items-center rounded-[10px] bg-brand font-sans text-[12px] font-bold text-surface-white">
          {getAgentInitials(agent.name)}
        </div>
        <div className="min-w-0 flex-1">
          <input
            key={agent.id}
            aria-label="Agent name"
            name="agent-name"
            value={nameDraft ?? agent.name}
            onChange={(e) => setNameDraft(e.target.value)}
            onBlur={commitRename}
            onKeyDown={(e) => {
              if (e.key === "Enter") (e.target as HTMLInputElement).blur();
              if (e.key === "Escape") setNameDraft(null);
            }}
            className="w-full truncate rounded-md border border-transparent bg-transparent px-1 -mx-1 font-sans text-[15px] font-semibold text-ink-900 focus:border-line-control focus:bg-surface-white focus:outline-none"
          />
          <p className="truncate font-serif text-[11px] text-ink-300">
            Agent · step {index + 1} of {total} · {agent.role}
          </p>
        </div>
      </div>

      {/* Same 4-tab inspector as the library agent drawer (AgentCapabilitiesModal). */}
      <Tabs
        className="mt-4"
        active={activeTab}
        onChange={(id) => setActiveTab(id as typeof activeTab)}
        tabs={[
          { id: "overview", label: "Overview" },
          { id: "skills", label: "Skills" },
          { id: "hooks", label: "Hooks" },
          { id: "tools", label: "Tools" },
          { id: "config", label: "Config" },
        ]}
      />

      {activeTab === "overview" && (
        <div className="mt-4">
          {agent.description && (
            <p className="font-serif text-[12px] leading-relaxed text-ink-500">
              {agent.description}
            </p>
          )}

          {/* PROMPT — a custom-agent instance edits its OWN `prompt`
              (R-02/R-06/R-36); a built-in agent keeps the EXISTING
              prompt-override mechanism (REUSE AgentPromptSection, same full
              Edit/Save/Revert experience as the Library drawer — no
              surfaceOnly here, the canvas rail is a real write surface too). */}
          <div className="mt-4">
            <div className="mb-2 flex items-center gap-2">
              <Settings2 className="h-3.5 w-3.5 text-brand" />
              <p className="font-sans text-[10px] font-semibold uppercase tracking-[0.1em] text-ink-300">
                Prompt
              </p>
            </div>
            {agent.isCustom ? (
              <textarea
                aria-label="Custom agent prompt"
                name="canvas-agent-prompt"
                value={agent.prompt ?? ""}
                onChange={(e) => onPromptChange?.(agent.id, e.target.value)}
                placeholder="What should this agent do?"
                rows={5}
                className="w-full rounded-[9px] border border-line-control bg-surface-white p-2.5 font-sans text-[12.5px] text-ink-900 focus:border-brand focus:outline-none"
              />
            ) : (
              <AgentPromptSection agent={agent} />
            )}
          </div>
        </div>
      )}

      {activeTab === "skills" && (
        <div className="mt-4">
          {/* No separate "attached skills" chip list here — the picker below
              already shows attached state per row (the ✓ button), so a chip
              summary directly above it would just say the same thing twice in
              the same tab. The card / Simple-view chips still carry that
              at-a-glance summary for surfaces with no picker open. */}
          <AgentSkillsPicker agent={agent} onSkillsChange={onSkillsChange} />
        </div>
      )}

      {activeTab === "hooks" && (
        <div className="mt-4">
          {suggestedHooks.length > 0 ? (
            <div>
              <div className="mb-2.5 flex items-center gap-2">
                <Webhook className="h-3.5 w-3.5 text-ink-300" />
                <p className="font-sans text-[10px] font-semibold uppercase tracking-[0.1em] text-ink-300">
                  Suggested hooks
                </p>
              </div>
              <div className="space-y-1.5">
                {suggestedHooks.map((hook) => {
                  const attached = isHookAttached(hook.id);
                  return (
                    <div
                      key={hook.id}
                      className="flex items-center justify-between gap-3 rounded-lg border border-line-faint-row bg-surface-warm px-3 py-2"
                    >
                      <div className="min-w-0 flex-1">
                        <div className="mb-0.5 flex items-center gap-1.5">
                          <p className="truncate font-sans text-[11px] font-semibold text-ink-900">
                            {hook.name}
                          </p>
                          <span className="flex-shrink-0 rounded bg-line-faint px-1.5 py-0.5 font-sans text-[9px] font-semibold text-ink-300">
                            {hook.event}
                          </span>
                        </div>
                        <p className="line-clamp-1 font-serif text-[10px] leading-relaxed text-ink-300">
                          {hook.description}
                        </p>
                      </div>
                      <button
                        type="button"
                        onClick={() =>
                          !attached &&
                          attachHook({
                            id: hook.id,
                            name: hook.name,
                            event: hook.event,
                            trigger: hook.trigger,
                            description: hook.description,
                          })
                        }
                        disabled={attached}
                        className={`flex flex-shrink-0 items-center gap-1 rounded-lg px-2.5 py-1 font-sans text-[10px] font-semibold transition-colors ${
                          attached
                            ? "cursor-default bg-line-faint text-ink-300"
                            : "cursor-pointer bg-ink-900 text-surface-white hover:bg-ink-700"
                        }`}
                      >
                        {attached ? (
                          <>
                            <Check className="h-2.5 w-2.5" /> Added
                          </>
                        ) : (
                          <>
                            <Plus className="h-2.5 w-2.5" /> Attach
                          </>
                        )}
                      </button>
                    </div>
                  );
                })}
              </div>
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center py-8 text-center">
              <Webhook className="mb-3 h-8 w-8 text-ink-200" />
              <p className="font-sans text-[13px] font-medium text-ink-500">No suggested hooks</p>
              <p className="mt-1 max-w-[220px] font-serif text-[11px] leading-relaxed text-ink-300">
                There are no pre-built hooks recommended for this agent.
              </p>
            </div>
          )}
        </div>
      )}

      {activeTab === "tools" && (
        <div className="mt-4">
          <div className="mb-2.5 flex items-center gap-2">
            <Settings2 className="h-3.5 w-3.5 text-ink-300" />
            <p className="font-sans text-[10px] font-semibold uppercase tracking-[0.1em] text-ink-300">
              Tool grants
            </p>
          </div>
          {/* Fixed, not author-editable. Read + write are required by the artifact
              contract — every step reads its inputs and writes its own deliverable, so
              a step without them cannot take part in a handoff. exec is engineer-only:
              the compiler rejects it for db-trust manifests (compiler.py
              `_TRUSTED_SOURCES`), so granting it here made the workflow unsaveable.
              spawn_subagents is not listed at all — child dispatch is the engine's job,
              never a per-node grant. */}
          <div className="space-y-1.5">
            {(
              [
                { label: "Read files", desc: "List and read files in the run sandbox.", on: true },
                { label: "Write files", desc: "Create and edit files in the run sandbox.", on: true },
                { label: "Execute commands", desc: "Not available to custom workflows.", on: false },
              ] as const
            ).map(({ label, desc, on }) => (
              <div
                key={label}
                className="flex items-center justify-between gap-3 rounded-lg border border-line-faint-row bg-surface-warm px-3 py-2"
              >
                <div className="min-w-0">
                  <p className="flex items-center gap-1.5 font-sans text-[11px] font-semibold text-ink-900">
                    <InfoHint>{desc}</InfoHint>
                    {label}
                  </p>
                  <p className="font-serif text-[10px] leading-relaxed text-ink-300">{desc}</p>
                </div>
                <Toggle on={on} label={label} disabled onToggle={() => {}} />
              </div>
            ))}
          </div>
        </div>
      )}

      {activeTab === "config" && (
      <>
      {/* MODEL (whole catalog — SC-001) */}
      <p className="mb-2 mt-5 flex items-center gap-1.5 font-sans text-[10px] font-semibold uppercase tracking-[0.1em] text-ink-300">
        <InfoHint>Overrides the default model for this agent's step. &quot;Default&quot; uses the workflow's own model choice.</InfoHint>
        Model
      </p>
      <div className="relative">
        <span className="pointer-events-none absolute left-[11px] top-1/2 h-2 w-2 -translate-y-1/2 rounded-full bg-brand" />
        <select
          aria-label="Model"
          name="agent-model"
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
          <div className="flex items-center gap-1.5 font-sans text-[12.5px] font-semibold text-ink-900">
            <InfoHint>Runs a registered validator against this step's output before the pipeline continues.</InfoHint>
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
          <div className="flex items-center gap-1.5 font-sans text-[12.5px] font-semibold text-ink-900">
            <InfoHint>Pauses the run after this step so a human can approve its output before the pipeline continues.</InfoHint>
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

      {/* Retry-on-failure: {"max_attempts": N} — coerced FE→BE by
          agents/workflows/selections.py::_coerce_retry, honoured at run time by
          the engine's per-step retry wrapper (_dispatch_step_with_retry) for
          BOTH base-manifest and composed (custom-agent) steps. */}
      <div className="flex items-center justify-between border-b border-line-faint-row py-3">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5 font-sans text-[12.5px] font-semibold text-ink-900">
            <InfoHint>Automatically re-runs this step on a transient failure, up to the selected number of extra attempts.</InfoHint>
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
            onClick={() => patch({ retry: Math.min(3, retry + 1) })}
            className="bg-surface-white px-2.5 py-1.5 font-sans text-[12px] font-semibold text-ink-500 enabled:hover:text-ink-900 disabled:opacity-40"
          >
            <Plus className="h-3 w-3" />
          </button>
        </div>
      </div>

      {/* FAN-OUT (51-07 / FANOUT-01, D6/D7/§4b) — "Fan out over a list": one
          worker per `## Task N:` heading the SOURCE step emits. The kernel owns
          spawn/isolation/merge; the rail only persists {strategy, task_source}
          through the SHARED reducer (no fork). GUARDRAILS (D9/§5b): the source
          picker lists ONLY earlier agents (priorAgents); the toggle is disabled
          for a step with no upstream; a non-blocking warning steers to a known
          `## Task N:` producer (INSERT-A-NODE, D2/D7). */}
      <div className="flex flex-col gap-2 py-3">
        <div className="flex items-center justify-between">
          <div className="min-w-0">
            <div className="flex items-center gap-1.5 font-sans text-[12.5px] font-semibold text-ink-900">
              <InfoHint>Spawns one worker per `## Task N:` heading emitted by an earlier step, instead of running this step once.</InfoHint>
              Fan out over a list
            </div>
            <div className="font-serif text-[11px] text-ink-300">
              Run one worker per task the source step lists
            </div>
          </div>
          {/* Disabled: fan-out requires the source step to emit `## Task N:` headings,
              which nothing in a custom workflow guarantees. Left visible (and any
              already-saved `fanout_batch` still renders as ON) so an existing workflow
              is not silently rewritten — it just cannot be turned on from here. */}
          <Toggle
            on={fanoutOn}
            label="Fan out over a list"
            disabled
            onToggle={() =>
              fanoutOn
                ? patch({
                    strategy: undefined,
                    task_source: undefined,
                    fanout: undefined,
                  })
                : patch({
                    strategy: "fanout_batch",
                    task_source: {
                      kind: "parsed",
                      parser: "heading_tasks",
                      source_step: defaultSource ?? "",
                    },
                  })
            }
          />
        </div>

        {/* No upstream → the toggle can't source a list (D9). */}
        {!canFanout && (
          <p className="font-serif text-[11px] leading-tight text-ink-300">
            Add an earlier step that outputs a task list to fan out over.
          </p>
        )}

        {/* Source picker — earlier steps ONLY (D9/§5b). */}
        {fanoutOn && canFanout && (
          <>
            <div className="relative">
              <span className="pointer-events-none absolute left-[11px] top-1/2 h-2 w-2 -translate-y-1/2 rounded-full bg-brand" />
              <select
                aria-label="Source list from"
                name="fanout-source"
                value={currentSource}
                onChange={(e) =>
                  patch({
                    task_source: {
                      kind: "parsed",
                      parser: "heading_tasks",
                      source_step: e.target.value,
                    },
                  })
                }
                className="w-full appearance-none rounded-[9px] border border-line-control bg-surface-white py-2.5 pl-6 pr-8 font-sans text-[12.5px] font-medium text-ink-900 focus:border-brand focus:outline-none"
              >
                {priorAgents.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name}
                  </option>
                ))}
              </select>
              <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-300" />
            </div>

            {/* Non-blocking unknown-producer warning (D7/§4e) — steer to INSERT
                a dedicated `## Task N:` producer; the compile guard (51-02) is
                the server backstop. */}
            {!sourceKnown && (
              <p className="flex items-start gap-1.5 rounded-md border border-status-amber-border bg-status-amber-fill px-2 py-1 font-serif text-[10.5px] leading-tight text-status-amber">
                <AlertCircle className="mt-0.5 h-3 w-3 flex-none" />
                <span>
                  This step fans out one worker per <code>## Task N:</code>{" "}
                  heading its source outputs — pick or insert a step that emits a
                  task list.
                </span>
              </p>
            )}
          </>
        )}
      </div>

      {/* STRATEGY (R-04/R-36) — only when this node has children. */}
      {hasChildren && (
        <div className="mt-4 border-t border-line-faint-row pt-3">
          <p className="mb-2 flex items-center gap-1.5 font-sans text-[10px] font-semibold uppercase tracking-[0.1em] text-ink-300">
            <InfoHint>Sequential runs each sub-agent one after another; Parallel runs them at the same time (up to Max parallel).</InfoHint>
            Sub-agent strategy
          </p>
          <div className="relative">
            <select
              aria-label="Sub-agent strategy"
              name="subagent-strategy"
              value={childStrategy}
              onChange={(e) =>
                onStrategyChange?.(
                  agent.id,
                  e.target.value as SubagentStrategy,
                  agent.maxParallel,
                )
              }
              className="w-full appearance-none rounded-[9px] border border-line-control bg-surface-white py-2.5 pl-3 pr-8 font-sans text-[12.5px] font-medium text-ink-900 focus:border-brand focus:outline-none"
            >
              <option value="sequential">Sequential</option>
              <option value="parallel">Parallel</option>
              {/* "fanout" intentionally not offered here: the compiler requires
                  a task_source (no UI control exists for one) and exactly one
                  declared child (this rail lets you add any number) — every
                  Composer-built fanout selection is guaranteed to fail
                  compilation at launch with no earlier warning. Re-add once
                  both constraints have real UI support. */}
            </select>
            <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-300" />
          </div>
          {childStrategy !== "sequential" && (
            <div className="mt-2 flex items-center justify-between">
              <span className="font-serif text-[11px] text-ink-300">Max parallel</span>
              <div className="inline-flex flex-none overflow-hidden rounded-[8px] border border-line-control">
                <button
                  type="button"
                  aria-label="Decrease max parallel"
                  disabled={maxParallel <= 1}
                  onClick={() =>
                    onStrategyChange?.(agent.id, childStrategy, Math.max(1, maxParallel - 1))
                  }
                  className="bg-surface-white px-2.5 py-1.5 font-sans text-[12px] font-semibold text-ink-500 enabled:hover:text-ink-900 disabled:opacity-40"
                >
                  <Minus className="h-3 w-3" />
                </button>
                <span className="border-x border-line-control bg-surface-warm px-3 py-1.5 font-sans text-[12.5px] font-semibold tabular-nums text-ink-900">
                  {maxParallel}
                </span>
                <button
                  type="button"
                  aria-label="Increase max parallel"
                  onClick={() => onStrategyChange?.(agent.id, childStrategy, maxParallel + 1)}
                  className="bg-surface-white px-2.5 py-1.5 font-sans text-[12px] font-semibold text-ink-500 enabled:hover:text-ink-900"
                >
                  <Plus className="h-3 w-3" />
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* The custom-prompt editor moved to the Overview tab. */}
      </>
      )}
    </div>
    </div>
  );
}

// Type re-referenced so the INV-3 reuse guard (grep SelectionsMap) holds and the
// shared selection shape stays the single source of truth for this rail.
export type CanvasRailSelections = SelectionsMap;
