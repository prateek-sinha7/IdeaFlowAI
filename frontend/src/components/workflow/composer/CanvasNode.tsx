"use client";

import { useEffect, useState } from "react";
import { Lock, X, Plus, Pencil, Check, ExternalLink, AlertTriangle, ChevronLeft, ChevronRight } from "lucide-react";
import { getRole, getAgentInitials, hasToolOverride, type StepSelection } from "../AgentsPopup";
import type { AgentDef, WorkflowType } from "@/types/index";
import type { CapabilityModelEntry } from "@/lib/api";
import { userWorkflowsApi, type UserWorkflowSummary } from "@/store/api/userWorkflows";
import { getWorkflowDefinitions, getToken } from "@/lib/api";
import { WorkflowPickerModal } from "./WorkflowPickerModal";

/** Unified shape for the workflow-target picker (T43, extended) — a system
 *  (file-backed) workflow and a user-saved custom workflow live in different
 *  tables/id-namespaces, but `run_trigger_workflow`
 *  (kernel_services.py:1306-1346) already resolves EITHER kind of id for a
 *  `trigger: "workflow"` outcome's `target` — the picker only needed to
 *  offer both, no backend change. */
export type WorkflowPickerOption = {
  id: string;
  /** Authored display_name, else name — the human title. */
  name: string;
  /** Authored short_name ("PPT"), when the manifest declares one. */
  shortName?: string;
  kind: "system" | "user";
  /** The manifest's `user_launchable`. FALSE for every `*_revision` pipeline —
   *  which is a statement about the DASHBOARD launcher (you cannot start a bare
   *  revision run with nothing to revise), not about route targets. A triggered
   *  run always has a parent (`run_trigger_workflow` sets
   *  `parent_run_id_override=ectx.run_id`), which is exactly what a revision
   *  pipeline needs, and the compiler's R-10 target check never restricted to
   *  launchable ids. So the picker OFFERS these — grouped apart — instead of
   *  filtering on a flag that answers a different question. */
  launchable: boolean;
  /** Manifest `is_beta` — a beta workflow is not offered as a route target. */
  isBeta: boolean;
  /** Catalog blurb + size, for the picker's cards. A native <select> could only
   *  ever render `name`, which is why these were previously discarded. */
  description?: string;
  stepCount?: number;
  icon?: string;
};

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
let workflowListPromise: Promise<WorkflowPickerOption[]> | null = null;

/** Lazily resolves BOTH the system (file-backed) workflow catalog
 *  (`getWorkflowDefinitions`, `GET /api/workflows`, filtered to
 *  `user_launchable` — the same visibility flag the dashboard catalog
 *  filters on) and "My Workflows" (`userWorkflowsApi.list()`,
 *  `GET /api/user-workflows`) into one combined, tagged list — only once
 *  `enabled` (i.e. some outcome on this node actually needs it), caching the
 *  result across every caller via `workflowListPromise` above. A failed
 *  fetch clears the cache so a later mount/toggle can retry, and is reported
 *  back as `fetchFailed` so the picker can degrade to free text instead of
 *  the form breaking. */
export function useWorkflowPickerOptions(enabled: boolean): {
  workflows: WorkflowPickerOption[] | null;
  fetchFailed: boolean;
} {
  const [workflows, setWorkflows] = useState<WorkflowPickerOption[] | null>(null);
  const [fetchFailed, setFetchFailed] = useState(false);

  useEffect(() => {
    if (!enabled || workflows || fetchFailed) return;
    if (!workflowListPromise) {
      const token = getToken();
      workflowListPromise = Promise.all([
        token ? getWorkflowDefinitions(token).catch(() => []) : Promise.resolve([]),
        userWorkflowsApi.list().catch(() => []),
      ]).then(([system, user]) => [
        ...system.map((w): WorkflowPickerOption => ({
          id: w.id,
          name: w.display_name ?? w.name,
          shortName: w.short_name ?? undefined,
          kind: "system",
          launchable: w.user_launchable,
          isBeta: !!w.is_beta,
          description: w.description || undefined,
          stepCount: w.step_count,
          icon: w.icon || undefined,
        })),
        ...user.map((w): WorkflowPickerOption => ({
          id: w.id,
          name: w.name,
          kind: "user",
          launchable: true,
          isBeta: false,
          description: w.description || undefined,
          stepCount: w.agent_ids?.length,
        })),
      ]);
    }
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
 * T43 (spec 014 / R-24), extended — the trigger:"workflow" outcome's target
 * picker, grouping BOTH the system (file-backed) workflow catalog and "My
 * Workflows" into one list. `"self"` (R-12: a fresh instance of this same
 * workflow definition) is always offered regardless of what the fetch
 * returns. On a fetch failure this falls back to the same free-text input the
 * trigger:"step" case uses, with a visible warning, so a network hiccup can
 * never fully block an author from setting a target.
 */
/* Widths are `w-full`, not the flex trio this once used: the picker now renders
   inside CanvasConfigRail's `grid-cols-3` Target cell, whose `<label>` is a
   BLOCK. `flex-1` is inert there and `w-0` really does collapse the control to
   zero, leaving nothing on screen but the select's chevron. */
export function WorkflowTargetPicker({
  value,
  onChange,
  workflows,
  fetchFailed,
}: {
  value: string;
  onChange: (next: string) => void;
  workflows: WorkflowPickerOption[] | null;
  fetchFailed: boolean;
}) {
  const [pickerOpen, setPickerOpen] = useState(false);

  // Fetch failed → free text, unchanged. A network hiccup must never leave an
  // author unable to set a target at all, and there is nothing for a picker to
  // list.
  if (fetchFailed) {
    return (
      <div className="w-full">
        <input
          aria-label="Target"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="workflow id / self"
          className="mt-0.5 w-full rounded-[6px] border border-line-control bg-surface-white px-1.5 py-1 font-sans text-[11px] text-ink-900 focus:border-brand focus:outline-none"
        />
        <p className="mt-0.5 font-serif text-[9px] italic text-status-amber">
          Couldn&apos;t load workflows — enter the target id directly.
        </p>
      </div>
    );
  }

  const chosen = value ? resolveWorkflowTarget(value, new Map((workflows ?? []).map((w) => [w.id, w.name]))) : null;

  return (
    <>
      {/* A button, not a <select>: the modal can show each candidate's
          description, size and group, none of which fit in an <option>. Once
          chosen, this shows the NAME only — the canvas node already carries the
          "diverts run" meaning, and repeating it here was the duplication that
          made this row read twice. */}
      <button
        type="button"
        aria-label="Target"
        data-testid="workflow-target-button"
        onClick={() => setPickerOpen(true)}
        className="mt-0.5 flex w-full items-center gap-1.5 rounded-[6px] border border-line-control bg-surface-white px-1.5 py-1 text-left font-sans text-[11px] hover:border-brand focus:border-brand focus:outline-none"
      >
        <ExternalLink className="h-3 w-3 flex-none text-brand" />
        <span className={`min-w-0 flex-1 truncate ${chosen ? "text-ink-900" : "italic text-ink-400"}`}>
          {chosen ? chosen.label : "Pick a workflow…"}
        </span>
      </button>
      {pickerOpen && (
        <WorkflowPickerModal
          value={value}
          workflows={workflows}
          onSelect={(id) => {
            onChange(id);
            setPickerOpen(false);
          }}
          onCancel={() => setPickerOpen(false)}
        />
      )}
    </>
  );
}

// T44 (spec 014 / R-22) — resolves `workflowId` against T43's fetched "My
// Workflows" list (via the `workflowNameById` lookup CanvasNode builds ONCE
// per render and passes to every card, never fetched here) so the card shows
// the target's real name instead of its raw id. `"self"` and any id the list
// doesn't (yet) contain both get the same muted/italic fallback treatment —
// distinct from a resolved name — rather than silently rendering a blank or
// an unstyled raw id indistinguishable from a real one.
export type RouteDraft = NonNullable<AgentDef["route"]>;
export type RouteOutcomeDraft = RouteDraft["outcomes"][string];

/** Pure route-outcome merge, lifted out of the component below so the Route
 *  editor (now in CanvasConfigRail) and CanvasView's connect-to-existing-node
 *  drag gesture (spec 014 / R-23, T46) share the SAME mutation path — an
 *  edge created by dragging is otherwise indistinguishable, in the
 *  resulting data, from one typed directly into this form. */
export function applyRoutePatch(route: RouteDraft | undefined, patch: Partial<RouteDraft>): RouteDraft {
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
/** Branch cap for one conditional gate. A FRONTEND-only limit — the compiler
 *  validates each outcome's shape and target but never counts them, so nothing
 *  in the engine requires this. It began at 3 because edges once fanned from
 *  the diamond's top/bottom tips and three was what physically fit; the row
 *  solver now spaces N targets symmetrically for any N, so the number is just a
 *  guard against an unreadable node.
 *
 *  Lives here (not in the rail) because BOTH creation paths must honour it: the
 *  rail's "+ Add outcome" button and CanvasView's drag-to-connect picker. */
export const MAX_ROUTE_OUTCOMES = 5;

export function nextOutcomeKey(route: RouteDraft | undefined): string {
  const outcomes = route?.outcomes ?? {};
  let n = Object.keys(outcomes).length + 1;
  while (outcomes[`outcome_${n}`]) n += 1;
  return `outcome_${n}`;
}

/** Resolve a `trigger:"workflow"` outcome's target id to what the author should
 *  read. Shared by the rail's inline strip and the canvas node so the two can
 *  never disagree about what a given target is called. */
export function resolveWorkflowTarget(
  workflowId: string,
  workflowNameById: Map<string, string>,
) {
  const id = workflowId.trim();
  const isSelf = id === "self";
  const resolvedName = !isSelf ? workflowNameById.get(id) : undefined;
  return {
    id,
    isSelf,
    // Not yet loaded, or an id the catalog does not know. Either way it is
    // rendered as provisional rather than as a confirmed name.
    isUnresolved: !isSelf && resolvedName === undefined,
    label: isSelf ? "self (this workflow)" : resolvedName ?? (id || "Select a workflow…"),
  };
}

/** Canvas width of an external-workflow node — deliberately narrower than an
 *  agent card (NODE_W 260) so it never reads as "another step of this run". */
export const EXTERNAL_NODE_W = 190;

/**
 * The canvas node for a `trigger: "workflow"` outcome (spec 014 / R-22).
 *
 * It is NOT a step of this workflow and must not look like one: the target runs
 * as a SECOND, independent `WorkflowRun` linked by `parent_run_id`
 * (`kernel_services.run_trigger_workflow`), with its own budget, gates and
 * lifecycle. So this is a reference, not an inlined graph — no avatar, no
 * ports, no chips, dashed border, and visibly smaller than an agent card.
 * Inlining the target's real steps would (a) claim they belong to this run,
 * (b) recurse forever on a `self` target, and (c) offer editing this canvas
 * cannot perform. Clicking opens that workflow instead.
 */
export function ExternalWorkflowNode({
  workflowId,
  workflowNameById,
  workflowShortNameById,
  workflowKindById,
  left,
  top,
  selected,
  onSelect,
  onMouseDown,
}: {
  workflowId: string;
  workflowNameById: Map<string, string>;
  /** id → the manifest's authored `short_name` ("PPT"). This is what the
   *  eyebrow shows — the label the workflow's author chose, not a machine id.
   *  Falls back to the kind below when a manifest declares none. */
  workflowShortNameById?: Map<string, string | undefined>;
  workflowKindById?: Map<string, "system" | "user">;
  left: number;
  top: number;
  selected?: boolean;
  onSelect?: () => void;
  onMouseDown?: (e: React.MouseEvent) => void;
}) {
  const { id, isSelf, isUnresolved, label } = resolveWorkflowTarget(workflowId, workflowNameById);
  // Eyebrow: the authored short_name when there is one ("PPT"), so the card
  // reads "(PPT) / Pitch an idea" — the manifest's own two labels. A user
  // workflow's id is a UUID and it has no short_name, so those say CUSTOM
  // rather than showing a machine identifier.
  const kind = workflowKindById?.get(id);
  const shortName = workflowShortNameById?.get(id);
  const eyebrow = isSelf
    ? "SELF"
    : shortName ?? (kind === "user" ? "CUSTOM" : id ? id.toUpperCase() : "WORKFLOW");
  return (
    <div
      role="button"
      tabIndex={0}
      data-testid={id ? `canvas-external-workflow-${id}` : "canvas-external-workflow-node"}
      data-selected={selected ? "true" : "false"}
      title={label}
      onClick={onSelect}
      onMouseDown={onMouseDown}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelect?.();
        }
      }}
      style={{ left, top, width: EXTERNAL_NODE_W }}
      // Deliberately NOT a link. Clicking selects it so it can be dragged like
      // any other node; navigating away mid-edit on a stray click was the wrong
      // trade. Open the target from the config rail's card instead.
      className={`absolute z-[3] cursor-pointer rounded-[12px] border border-dashed bg-surface-card px-2.5 py-2 shadow-[0_1px_2px_rgba(17,17,20,0.04)] transition-shadow ${
        selected
          ? "border-brand shadow-[0_0_0_3px_var(--brand-fill),0_8px_22px_rgba(60,44,218,0.14)]"
          : "border-brand-border hover:border-brand"
      }`}
    >
      <div className="flex items-center gap-1.5">
        <ExternalLink className="h-3 w-3 flex-none text-brand" />
        <span className="truncate font-sans text-[8.5px] font-bold uppercase tracking-[0.07em] text-brand">
          {eyebrow}
        </span>
      </div>
      <p
        className={`mt-1 truncate font-sans text-[12.5px] font-semibold ${
          isSelf || isUnresolved ? "italic text-ink-400" : "text-ink-900"
        }`}
      >
        {label}
      </p>
      <span className="mt-1.5 inline-block rounded-full border border-brand-border bg-brand-fill px-1.5 py-0.5 font-sans text-[8px] font-bold uppercase tracking-[0.05em] text-brand">
        Diverts run
      </span>
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
  onCardMouseDown,
  onOpenConfig,
  onChainConnectMouseDown,
  dropTarget,
  minCardHeight,
  onPortMouseDown,
  modelOptions,
  addChildDisabledReason,
  onMoveEarlier,
  onMoveLater,
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
  /** Swap this ROOT step with its neighbour. The WHOLE step moves — its
   *  sub-agents travel with it, because a step's children are nested inside it
   *  in `pipelineAgents`, so moving the node moves the subtree by construction.
   *  Undefined at the ends of the chain (and for child nodes), which is what
   *  disables the arrow. */
  onMoveEarlier?: () => void;
  onMoveLater?: () => void;
  onSkillsChange?: (agentId: string, skills: string[]) => void;
  /** Free-drag: mousedown anywhere on the card body (not the top port, that's
   *  reserved for edge-drag-to-reparent). */
  onCardMouseDown?: (e: React.MouseEvent) => void;
  /** Select this node AND jump the config rail to its Config tab — wired to
   *  the Gate chip and the Route badge, the two affordances whose editor is
   *  in that tab. */
  onOpenConfig?: () => void;
  /** Present only while some step is detached — makes the right port a
   *  drag handle for re-attaching that orphan after this step. */
  onChainConnectMouseDown?: (e: React.MouseEvent) => void;
  /** A live drag is hovering this node and would drop onto it. */
  dropTarget?: boolean;
  /** Row-wide minimum card height (px), so every root card on a row is the
   *  same height and its centred ports line up with its neighbours'. Omitted
   *  for nested nodes, which size themselves. */
  minCardHeight?: number;
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
  // ISS-382 — the chip row showed Validator/Gate/Retry but had no Tools chip,
  // so a node whose tool grants were restricted (e.g. write_files=false) gave
  // no at-a-glance signal until the author re-opened the config rail's Tools
  // tab specifically. `hasToolOverride` (exported from AgentsPopup alongside
  // effectiveToolGrants) returns true whenever any grant deviates from default.
  const toolsOn = hasToolOverride(selection);
  // Route badge (spec 014 / R-02/R-03) — surfaced only when this step's own
  // gates list carries "conditional" (the compiler REQUIRES a non-empty
  // route.outcomes whenever that gate is declared, and rejects it the other
  // way round too). The editable form itself now lives in CanvasConfigRail
  // (the sidebar) — read directly off `agent.route` (the parent's
  // authoritative copy, kept fresh via `onRouteChange` -> `onTreeChange` ->
  // `pipelineAgents`) rather than mirroring it into local state here, since
  // this node no longer writes to it.
  const conditionalOn = (selection?.gates ?? []).includes("conditional");
  const outcomeCount = Object.keys(agent.route?.outcomes ?? {}).length;

  const avatarCls = selected
    ? "bg-brand text-surface-white"
    : locked
      ? "bg-brand-fill text-brand"
      : "bg-line-faint-row text-ink-500";

  // A conditional step's RIGHT port IS the diamond — the same port, a
  // different shape, in exactly the same place. It is not an extra symbol laid
  // over the circle (that showed two), and it is not a separately positioned
  // overlay (that drifted off the circle's spot). Every route edge starts at
  // this one point; CanvasView anchors them to the card's right edge at the
  // node's vertical center, which is where this sits.
  const port = (
    side: "l" | "r" | "t" | "b",
    handlers?: { onMouseDown?: (e: React.MouseEvent) => void },
    diamond?: boolean,
    extra?: { testId?: string; title?: string },
  ) => (
    <span
      aria-hidden={!handlers}
      data-testid={extra?.testId}
      title={extra?.title}
      onMouseDown={handlers?.onMouseDown}
      className={`absolute h-[11px] w-[11px] border-2 bg-surface-card ${
        diamond ? "rotate-45 rounded-[2px]" : "rounded-full"
      } ${
        // Colour tracks SELECTION, never type — the diamond SHAPE already says
        // "branch point". A permanently amber diamond made every conditional
        // node look active even when nothing was selected, the same thing the
        // route lines used to do before dash took over carrying the meaning.
        selected ? "border-brand" : "border-line-faint"
      } ${
        handlers ? "cursor-crosshair hover:scale-125 hover:border-brand" : ""
      } ${
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
        style={minCardHeight ? { minHeight: minCardHeight } : undefined}
        onClick={onSelect}
        onMouseDown={onCardMouseDown}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            onSelect();
          }
        }}
        className={`relative cursor-pointer rounded-[14px] border bg-surface-card px-3 pb-[11px] pt-3 shadow-[0_1px_2px_rgba(17,17,20,0.04)] transition-shadow ${
          dropTarget
            ? "border-brand shadow-[0_0_0_4px_var(--brand-fill)]"
            : selected
            ? "border-brand shadow-[0_0_0_3px_var(--brand-fill),0_8px_22px_rgba(60,44,218,0.14)]"
            : agent.detached
              ? "border-dashed border-status-amber hover:border-status-amber"
              : "border-line-border hover:border-line-faint"
        }`}
      >
        {/* Reparent-drag handle: children use the top port (they sit BELOW
            their parent); root nodes use the left port instead (they sit in
            the horizontal chain) — same underlying gesture/handler either
            way (CanvasView's handlePortMouseDown -> moveAgentInTree already
            treats root and nested nodes identically), this was previously
            only ever wired to children, leaving root nodes with no drag
            handle of their own to attach to another node. */}
        {isChild ? port("t", { onMouseDown: onPortMouseDown }) : port("l", { onMouseDown: onPortMouseDown })}
        {/* Decorative, exactly like the circle it replaces — you cannot start a
            connection by dragging it. Route targets are set in the config
            rail's Route section; the drawn lines themselves stay grabbable for
            re-targeting. */}
        {conditionalOn
          ? port("r", undefined, true, { testId: `canvas-route-connect-${agent.id}` })
          : port(
              "r",
              // Live ONLY while something is orphaned — otherwise this stays the
              // decorative dot it has always been, and the canvas gains no
              // gesture you would have to know about but never need.
              onChainConnectMouseDown ? { onMouseDown: onChainConnectMouseDown } : undefined,
              false,
              onChainConnectMouseDown
                ? { title: "Drag onto the unconnected step to attach it here" }
                : undefined,
            )}
        {hasChildren && port("b")}

        {/* Reorder — move this whole step one place earlier / later in the
            chain. Placed on the LEFT and RIGHT edges, vertically centred beside
            the connection ports, so the control points the same way the move
            does: "<" sends the step left, ">" sends it right. In the top-right
            cluster they read as generic icons with no direction; here the
            position IS the affordance.

            Offset inside the card edge (not on it) so they never sit under the
            11px port circles, which straddle the border at -6px. */}
        {(onMoveEarlier || onMoveLater) && !renaming && (
          <>
            <button
              type="button"
              aria-label={`Move ${agent.name} earlier`}
              title={onMoveEarlier ? "Move one step earlier" : "Already first"}
              disabled={!onMoveEarlier}
              onClick={(e) => { e.stopPropagation(); onMoveEarlier?.(); }}
              data-testid={`canvas-move-earlier-${agent.id}`}
              className="absolute left-1 top-1/2 z-[1] grid h-6 w-5 -translate-y-1/2 place-items-center rounded-[6px] text-ink-300 enabled:hover:bg-line-faint-row enabled:hover:text-ink-700 disabled:cursor-not-allowed disabled:opacity-0"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            <button
              type="button"
              aria-label={`Move ${agent.name} later`}
              title={onMoveLater ? "Move one step later" : "Already last"}
              disabled={!onMoveLater}
              onClick={(e) => { e.stopPropagation(); onMoveLater?.(); }}
              data-testid={`canvas-move-later-${agent.id}`}
              className="absolute right-1 top-1/2 z-[1] grid h-6 w-5 -translate-y-1/2 place-items-center rounded-[6px] text-ink-300 enabled:hover:bg-line-faint-row enabled:hover:text-ink-700 disabled:cursor-not-allowed disabled:opacity-0"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </>
        )}

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

        {/* override chips — Validator (brand) · Gate (amber) · Retry (brand) · Tools (amber when restricted) */}
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
          {/* Clickable, unlike its Validator/Retry neighbours: the gate is the
              one chip with a whole editor behind it (review gate + the route
              form), so clicking it jumps the rail to Config rather than making
              the author select the node and then hunt for the tab. */}
          <button
            type="button"
            title="Configure this step's gate"
            onClick={(e) => {
              e.stopPropagation();
              onOpenConfig?.();
            }}
            className={`rounded-[6px] border px-1.5 py-1 font-sans text-[9.5px] font-semibold transition-colors hover:border-status-amber ${
              gateOn
                ? "border-status-amber-border bg-status-amber-fill text-status-amber"
                : "border-line-faint-row bg-surface-white text-ink-300"
            }`}
          >
            Gate
          </button>
          <span
            className={`rounded-[6px] border px-1.5 py-1 font-sans text-[9.5px] font-semibold ${
              retryOn
                ? "border-brand-border bg-brand-fill text-brand"
                : "border-line-faint-row bg-surface-white text-ink-300"
            }`}
          >
            {retryOn ? `Retry ·${retry}` : "Retry"}
          </span>
          {/* ISS-382 — Tools chip: active (amber) when any tool grant deviates
              from the default (write_files=true, read_files=true). This is the
              same at-a-glance signal Validator/Gate/Retry already provide for
              their respective overrides — without it a restricted node card was
              visually indistinguishable from an unrestricted one. */}
          <span
            title={toolsOn ? "Tool grants are restricted — open Config to view" : undefined}
            className={`rounded-[6px] border px-1.5 py-1 font-sans text-[9.5px] font-semibold ${
              toolsOn
                ? "border-status-amber-border bg-status-amber-fill text-status-amber"
                : "border-line-faint-row bg-surface-white text-ink-300"
            }`}
          >
            Tools
          </span>
        </div>

        {agent.detached && (
          <div
            data-testid={`canvas-node-detached-${agent.id}`}
            className="mb-2 flex items-center gap-1.5 rounded-[8px] border border-status-amber-border bg-status-amber-fill/50 px-2 py-1"
          >
            <AlertTriangle className="h-3 w-3 flex-none text-status-amber" />
            <span className="font-serif text-[10px] leading-snug text-status-amber">
              Not connected — point a route at this step, or remove it.
            </span>
          </div>
        )}

        {/* Route badge (spec 014 / R-02, redesigned) — a compact glance-only
            indicator. The editable form (Condition source, per-outcome
            Condition/Type/Target, Add outcome, Default) now lives in
            CanvasConfigRail (the sidebar), which has the width to render it
            without cropping — see that file's Route section, revealed the
            moment "Review gate" is set to "conditional". This card keeps
            only enough to answer "does this step route, and how many ways"
            at a glance; the drag-to-connect diamond handle (CanvasView) is
            unaffected — it's a separate overlay, not part of this block. */}
        {conditionalOn && (
          <button
            type="button"
            data-testid={`canvas-node-route-${agent.id}`}
            title="Edit this step's route outcomes"
            onClick={(e) => {
              e.stopPropagation();
              onOpenConfig?.();
            }}
            className={`mt-2.5 flex w-full items-center gap-1.5 rounded-[9px] border px-2 py-1.5 text-left transition-colors ${
              selected
                ? "border-status-amber-border bg-status-amber-fill/40 hover:bg-status-amber-fill"
                : "border-line-faint-row bg-surface-warm hover:border-line-control"
            }`}
          >
            <span
              className={`font-sans text-[9.5px] font-bold uppercase tracking-[0.05em] ${
                selected ? "text-status-amber" : "text-ink-400"
              }`}
            >
              Route
            </span>
            <span
              className={`font-serif text-[10px] ${selected ? "text-status-amber" : "text-ink-400"}`}
            >
              {outcomeCount === 0
                ? "no outcomes yet"
                : outcomeCount === 1
                  ? "1 outcome"
                  : `${outcomeCount} outcomes`}
            </span>
          </button>
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
