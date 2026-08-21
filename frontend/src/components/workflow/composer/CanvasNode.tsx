"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Lock, X, Plus, Pencil, Check, ExternalLink } from "lucide-react";
import { getRole, getAgentInitials, type StepSelection } from "../AgentsPopup";
import type { AgentDef, WorkflowType } from "@/types/index";
import type { CapabilityModelEntry } from "@/lib/api";
import { userWorkflowsApi, type UserWorkflowSummary } from "@/store/api/userWorkflows";
import { routes } from "@/lib/routes";

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
 * T36 (spec 014 / R-22) — the ONE new node kind this spec adds: a reference
 * card for a `trigger: "workflow"` outcome's target, i.e. a DIFFERENT
 * workflow this run diverts into on that outcome, not another step of this
 * one. R-22 explicitly rejects a new node kind for in-workflow routing (that
 * stays on the T35 route-editor panel above, on the SAME agent card) — this
 * card exists only to represent the cross-workflow case, and is deliberately
 * styled unlike both the standard agent card (solid border, avatar) and the
 * amber route-editor panel (dashed brand border, link icon, no avatar) so
 * the two are never mistaken for one another. Renders inline under the
 * outcome row it belongs to — CanvasView's graph-layout conversion (R-23) is
 * its own scoping pass and out of bounds here, so this is not yet a
 * positioned canvas node in that sense.
 */
// T43 (spec 014 / R-24) — module-scoped, not component state: every mounted
// CanvasNode (and every workflow-trigger outcome row within one) shares this
// SAME promise, so the picker below never re-fetches per row or per node,
// mirroring this file's existing `modelOptions` shared-catalog pattern
// (there lifted to CanvasView as a prop; here kept in-module since this
// task's diff is scoped to CanvasNode.tsx alone).
let workflowListPromise: Promise<UserWorkflowSummary[]> | null = null;

/** Lazily resolves the "My Workflows" list (`userWorkflowsApi.list()`, the
 *  same `GET /api/user-workflows` reuse R-24 calls for) only once `enabled`
 *  (i.e. some outcome on this node actually needs it), and caches the result
 *  across every caller via `workflowListPromise` above. A failed fetch clears
 *  the cache so a later mount/toggle can retry, and is reported back as
 *  `fetchFailed` so the picker can degrade to free text instead of the form
 *  breaking. */
function useWorkflowPickerOptions(enabled: boolean): {
  workflows: UserWorkflowSummary[] | null;
  fetchFailed: boolean;
} {
  const [workflows, setWorkflows] = useState<UserWorkflowSummary[] | null>(null);
  const [fetchFailed, setFetchFailed] = useState(false);

  useEffect(() => {
    if (!enabled || workflows || fetchFailed) return;
    if (!workflowListPromise) workflowListPromise = userWorkflowsApi.list();
    let cancelled = false;
    workflowListPromise.then(
      (list) => {
        if (!cancelled) setWorkflows(list);
      },
      () => {
        if (!cancelled) setFetchFailed(true);
        workflowListPromise = null;
      },
    );
    return () => {
      cancelled = true;
    };
  }, [enabled, workflows, fetchFailed]);

  return { workflows, fetchFailed };
}

/**
 * T43 (spec 014 / R-24) — the trigger:"workflow" outcome's target picker,
 * reusing `userWorkflowsApi.list()` ("My Workflows"'s own data source) rather
 * than a new purpose-built endpoint. `"self"` (R-12: a fresh instance of this
 * same workflow definition) is always offered regardless of what the fetch
 * returns. On a fetch failure this falls back to the same free-text input the
 * trigger:"step" case uses, with a visible warning, so a network hiccup can
 * never fully block an author from setting a target.
 */
function WorkflowTargetPicker({
  value,
  onChange,
  workflows,
  fetchFailed,
}: {
  value: string;
  onChange: (next: string) => void;
  workflows: UserWorkflowSummary[] | null;
  fetchFailed: boolean;
}) {
  if (fetchFailed) {
    return (
      <div className="w-0 min-w-0 flex-1">
        <input
          aria-label="Target"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="workflow id / self"
          className="w-full rounded-[6px] border border-line-control bg-surface-white px-1.5 py-1 font-sans text-[11px] text-ink-900 focus:border-brand focus:outline-none"
        />
        <p className="mt-0.5 font-serif text-[9px] italic text-status-amber">
          Couldn&apos;t load your workflows — enter the target id directly.
        </p>
      </div>
    );
  }

  const knownIds = new Set(workflows?.map((w) => w.id));
  return (
    <select
      aria-label="Target"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="w-0 min-w-0 flex-1 rounded-[6px] border border-line-control bg-surface-white px-1.5 py-1 font-sans text-[11px] text-ink-900 focus:border-brand focus:outline-none"
    >
      <option value="" disabled>
        {workflows ? "Select a workflow…" : "Loading workflows…"}
      </option>
      <option value="self">self (this workflow)</option>
      {value && value !== "self" && !knownIds.has(value) && (
        <option value={value}>{value}</option>
      )}
      {workflows?.map((w) => (
        <option key={w.id} value={w.id}>
          {w.name}
        </option>
      ))}
    </select>
  );
}

// T44 (spec 014 / R-22) — resolves `workflowId` against T43's fetched "My
// Workflows" list (via the `workflowNameById` lookup CanvasNode builds ONCE
// per render and passes to every card, never fetched here) so the card shows
// the target's real name instead of its raw id. `"self"` and any id the list
// doesn't (yet) contain both get the same muted/italic fallback treatment —
// distinct from a resolved name — rather than silently rendering a blank or
// an unstyled raw id indistinguishable from a real one.
type RouteDraft = NonNullable<AgentDef["route"]>;
type RouteOutcomeDraft = RouteDraft["outcomes"][string];

/** Pure route-outcome merge, lifted out of the component below so this
 *  file's own Route editor (T43) and CanvasView's connect-to-existing-node
 *  drag gesture (spec 014 / R-23, T46) share the SAME mutation path — an
 *  edge created by dragging is otherwise indistinguishable, in the
 *  resulting data, from one typed directly into this form. */
function applyRoutePatch(route: RouteDraft | undefined, patch: Partial<RouteDraft>): RouteDraft {
  return { outcomes: {}, ...route, ...patch };
}
export function applyOutcomePatch(
  route: RouteDraft | undefined,
  key: string,
  patch: Partial<RouteOutcomeDraft>,
): RouteDraft {
  const prevOutcome = route?.outcomes?.[key] ?? { trigger: "step", target: "" };
  return applyRoutePatch(route, { outcomes: { ...(route?.outcomes ?? {}), [key]: { ...prevOutcome, ...patch } } });
}
/** Same "outcome_N" naming CanvasNode's own "+ Add outcome" button already
 *  uses — shared so T46's picker's "new outcome" choice mints an identical
 *  key, not a second naming scheme. */
export function nextOutcomeKey(route: RouteDraft | undefined): string {
  const outcomes = route?.outcomes ?? {};
  let n = Object.keys(outcomes).length + 1;
  while (outcomes[`outcome_${n}`]) n += 1;
  return `outcome_${n}`;
}

function ExternalPipelineCard({
  workflowId,
  workflowNameById,
}: {
  workflowId: string;
  workflowNameById: Map<string, string>;
}) {
  const id = workflowId.trim();
  const isSelf = id === "self";
  const resolvedName = !isSelf ? workflowNameById.get(id) : undefined;
  const isUnresolved = !isSelf && resolvedName === undefined;

  const label = isSelf ? "self (this workflow)" : resolvedName ?? (id || "Select a workflow…");

  const cardCls =
    "mt-1 flex items-center gap-1.5 rounded-[8px] border border-dashed border-brand-border bg-surface-white px-2 py-1";
  const labelCls = `min-w-0 flex-1 truncate font-sans text-[10.5px] font-semibold ${
    isSelf || isUnresolved ? "italic text-ink-400" : "text-brand"
  }`;
  const body = (
    <>
      <ExternalLink className="h-3 w-3 flex-none text-brand" />
      <span className={labelCls}>{label}</span>
      <span className="flex-none rounded-full border border-brand-border bg-brand-fill px-1.5 py-0.5 font-sans text-[8px] font-bold uppercase tracking-[0.05em] text-brand">
        Diverts run
      </span>
    </>
  );

  // Launch affordance only for a real, resolvable target: "self" has no
  // concrete workflow id this component can navigate to (the composer's own
  // in-progress workflow may not even be saved yet, and its id isn't threaded
  // into CanvasNode), and an empty target has nowhere to go. An unresolved
  // (not-yet-loaded, or genuinely unknown) id still gets the link — it's a
  // real id the author picked/typed, same as SavedWorkflowsPage's Edit action.
  if (!isSelf && id) {
    return (
      <Link
        data-testid="canvas-external-pipeline-card"
        href={routes.workflowEdit(id)}
        className={`${cardCls} hover:border-brand`}
      >
        {body}
      </Link>
    );
  }

  return (
    <div data-testid="canvas-external-pipeline-card" className={cardCls}>
      {body}
    </div>
  );
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
  onRouteChange,
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
  /** Route-editor write-through (spec 014 / R-02). Fired with the full draft
   *  `route` on every edit; CanvasView wires this to `handleRouteChange`,
   *  which round-trips through `onTreeChange` into `pipelineAgents` (T35). */
  onRouteChange?: (agentId: string, route: AgentDef["route"]) => void;
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
  // Route-target editor (spec 014 / R-02/R-03) — surfaced only when this
  // step's own gates list carries "conditional" (the compiler REQUIRES a
  // non-empty route.outcomes whenever that gate is declared, and rejects it
  // the other way round too).
  const conditionalOn = (selection?.gates ?? []).includes("conditional");

  const [route, setRoute] = useState<RouteDraft | undefined>(agent.route);

  const updateRoute = (patch: Partial<RouteDraft>) => {
    const next = applyRoutePatch(route, patch);
    setRoute(next);
    onRouteChange?.(agent.id, next);
  };
  const updateOutcome = (key: string, patch: Partial<RouteOutcomeDraft>) => {
    const next = applyOutcomePatch(route, key, patch);
    setRoute(next);
    onRouteChange?.(agent.id, next);
  };
  const renameOutcome = (oldKey: string, newKey: string) => {
    if (!newKey || newKey === oldKey || route?.outcomes?.[newKey]) return;
    const next: RouteDraft["outcomes"] = {};
    for (const [k, v] of Object.entries(route?.outcomes ?? {})) next[k === oldKey ? newKey : k] = v;
    updateRoute({ outcomes: next });
  };
  const addOutcome = () => {
    updateOutcome(nextOutcomeKey(route), {});
  };
  const removeOutcome = (key: string) => {
    const outcomes = { ...(route?.outcomes ?? {}) };
    delete outcomes[key];
    updateRoute({ outcomes });
  };

  // T43 (spec 014 / R-24) — only fetches once some outcome on THIS node
  // actually routes to a workflow target; `useWorkflowPickerOptions` itself
  // dedupes the underlying network call across every node/row via the
  // module-scoped `workflowListPromise`.
  const needsWorkflowOptions =
    conditionalOn && Object.values(route?.outcomes ?? {}).some((o) => o.trigger === "workflow");
  const { workflows: workflowOptions, fetchFailed: workflowFetchFailed } =
    useWorkflowPickerOptions(needsWorkflowOptions);
  // T44 (spec 014 / R-22) — id→name lookup for every ExternalPipelineCard on
  // this node, derived from the SAME already-fetched `workflowOptions` above
  // (built once here, reused by every card below — never re-fetched or
  // re-derived per card).
  const workflowNameById = new Map((workflowOptions ?? []).map((w) => [w.id, w.name]));

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
                  name="agent-rename"
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

        {/* Route-target editor (spec 014 / R-02) — node-level form only: lets
            the author declare each condition value's destination (outcomes),
            an optional condition source, and the no-match fallback. No
            edge-drawing/graph-layout here — that's CanvasView's own scoping
            pass. Stops all three event kinds from bubbling to the card (click
            = select, mousedown = free-drag, keydown = the card's Enter/Space
            select shortcut) so typing/clicking inside the form never
            (de)selects or drags the node. */}
        {conditionalOn && (
          <div
            data-testid={`canvas-node-route-${agent.id}`}
            onClick={(e) => e.stopPropagation()}
            onMouseDown={(e) => e.stopPropagation()}
            onKeyDown={(e) => e.stopPropagation()}
            className="mt-2.5 rounded-[9px] border border-status-amber-border bg-status-amber-fill/40 p-2"
          >
            <p className="font-sans text-[9.5px] font-bold uppercase tracking-[0.05em] text-status-amber">
              Route
            </p>

            <label className="mt-1.5 block font-sans text-[10px] text-ink-500">
              Condition source
              <input
                aria-label="Condition source"
                value={route?.condition_agent ?? ""}
                onChange={(e) => updateRoute({ condition_agent: e.target.value || undefined })}
                placeholder="this step's own output"
                className="mt-0.5 w-full rounded-[6px] border border-line-control bg-surface-white px-1.5 py-1 font-sans text-[11px] text-ink-900 focus:border-brand focus:outline-none"
              />
            </label>

            <div className="mt-2 space-y-1.5">
              {Object.entries(route?.outcomes ?? {}).map(([key, outcome]) => (
                <div key={key}>
                  <div className="flex items-center gap-1">
                    <input
                      aria-label="Condition value"
                      defaultValue={key}
                      onBlur={(e) => renameOutcome(key, e.target.value.trim())}
                      placeholder="condition value"
                      className="w-0 min-w-0 flex-1 rounded-[6px] border border-line-control bg-surface-white px-1.5 py-1 font-sans text-[11px] text-ink-900 focus:border-brand focus:outline-none"
                    />
                    <select
                      aria-label="Trigger"
                      value={outcome.trigger}
                      onChange={(e) => updateOutcome(key, { trigger: e.target.value as RouteOutcomeDraft["trigger"] })}
                      className="flex-none rounded-[6px] border border-line-control bg-surface-white px-1 py-1 font-sans text-[10.5px] text-ink-900 focus:border-brand focus:outline-none"
                    >
                      <option value="step">Step</option>
                      <option value="workflow">Workflow</option>
                    </select>
                    {/* T43 (spec 014 / R-24) — the workflow-target case gets
                        a real picker over the "My Workflows" list instead of
                        this bare free-text field; the step-target case below
                        is untouched. */}
                    {outcome.trigger === "workflow" ? (
                      <WorkflowTargetPicker
                        value={outcome.target}
                        onChange={(next) => updateOutcome(key, { target: next })}
                        workflows={workflowOptions}
                        fetchFailed={workflowFetchFailed}
                      />
                    ) : (
                      <input
                        aria-label="Target"
                        value={outcome.target}
                        onChange={(e) => updateOutcome(key, { target: e.target.value })}
                        placeholder="step id"
                        className="w-0 min-w-0 flex-1 rounded-[6px] border border-line-control bg-surface-white px-1.5 py-1 font-sans text-[11px] text-ink-900 focus:border-brand focus:outline-none"
                      />
                    )}
                    <button
                      type="button"
                      aria-label={`Remove outcome ${key}`}
                      onClick={() => removeOutcome(key)}
                      className="grid h-5 w-5 flex-none place-items-center rounded-[5px] text-ink-300 hover:bg-line-faint hover:text-ink-700"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </div>
                  {/* T36/R-22 — the new external-pipeline reference node,
                      surfaced the moment this outcome's trigger is set to
                      "workflow" (a cross-workflow divert), distinct from the
                      plain "step" case which stays a bare text target above. */}
                  {outcome.trigger === "workflow" && (
                    <ExternalPipelineCard workflowId={outcome.target} workflowNameById={workflowNameById} />
                  )}
                </div>
              ))}
            </div>

            <button
              type="button"
              data-testid={`canvas-node-route-add-${agent.id}`}
              onClick={addOutcome}
              className="mt-1.5 flex items-center gap-1 font-sans text-[10px] font-semibold text-status-amber hover:underline"
            >
              <Plus className="h-2.5 w-2.5" />
              Add outcome
            </button>

            <label className="mt-2 block font-sans text-[10px] text-ink-500">
              Default (no match)
              <input
                aria-label="Default (no match)"
                value={route?.default_next ?? ""}
                onChange={(e) => updateRoute({ default_next: e.target.value || undefined })}
                placeholder="run ends here"
                className="mt-0.5 w-full rounded-[6px] border border-line-control bg-surface-white px-1.5 py-1 font-sans text-[11px] text-ink-900 focus:border-brand focus:outline-none"
              />
            </label>

            {Object.keys(route?.outcomes ?? {}).length === 0 && (
              <p className="mt-1.5 font-serif text-[9.5px] italic text-ink-300">
                At least one outcome is required for this gate to run.
              </p>
            )}
          </div>
        )}

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
