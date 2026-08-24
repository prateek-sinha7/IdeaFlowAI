"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { motion } from "motion/react";
import { ArrowLeft, Save, Play, Plus, GitBranch, LayoutList, Sparkles, Loader2, Check, Paperclip } from "lucide-react";
import { IdentityCard } from "./IdentityCard";
import { AgentRow } from "./AgentRow";
import { SubAgentReadOnlyList } from "./SubAgentReadOnlyList";
import { SummaryRail } from "./SummaryRail";
import { CanvasView } from "./CanvasView";
import {
  HooksTab,
  PIPELINE_LABEL,
  getRole,
  type SelectionsMap,
  type StepSelection,
} from "../AgentsPopup";
import { AgentLibrary } from "../AgentLibrary";
import { useAgentLibrary } from "@/hooks/useAgentLibrary";
import {
  getAgentRecommendations,
  COMPANION_GROUPS,
  resolveDispatchType,
  useBriefAttachments,
  BriefAttachBox,
} from "../IdeaInputPage";
import { saveUserWorkflow, getToken, getWorkflowDetail } from "@/lib/api";
import { agentMatchesPipelineType } from "@/lib/workflowIcons";
import { useSkillsHooks } from "@/context/SkillsHooksContext";
import {
  addChildInTree,
  buildWorkflowManifest,
  collectAgentIds,
  findAgentInTree,
  instantiateIfTemplate,
  manifestStepsToAgents,
  type ManifestStep,
} from "@/store/api/userWorkflows";
import type { AgentDef, WorkflowCapabilities, WorkflowRunConfig, WorkflowType } from "@/types/index";

// Spec 012 (R-27/T30): once a node carries a per-node skill, a custom prompt,
// or a sub-agent tree, Save must persist the FULL `{"steps": [...]}` manifest
// (not the flat EMP-03 selections map) so those fields — and the tree shape
// itself — survive a reload (`backend/app/api/user_workflows.py::_project`
// sniffs the `"steps"` key to tell the two shapes apart).
function needsFullManifest(agents: AgentDef[]): boolean {
  return agents.some(
    (a) =>
      a.isCustom ||
      !!a.prompt ||
      (a.skills?.length ?? 0) > 0 ||
      (a.children?.length ?? 0) > 0,
  );
}

interface ComposerPageProps {
  /** base_pipeline_type — fixed at composer entry; the Deliverable-type is read-only (ND-AH). */
  workflowType: WorkflowType;
  onBack: () => void;
  /**
   * 41-06 — Run-once launch (D-05 / D-CMP-RUN). Threads the composed run through
   * the EXISTING owner-scoped onStartPipeline → startPipeline seam (no new
   * contract, no engine edit, SC-001). The parent maps this onto
   * `onStartPipeline(base_pipeline_type, brief, agentIds, attachedHooks,
   * extraParams)` — the SAME arg convention the revision launch
   * sites use. `base_pipeline_type` is the composer's fixed-at-entry workflowType
   * ("custom" for the compose entry, ND-AH) — the SAME value Save-to-catalogue
   * persists, so Run + Save carry an identical base. Absent ⇒ Run-once stays inert.
   */
  onRun?: (
    base_pipeline_type: WorkflowType,
    brief: string,
    agentIds: string[],
    extraParams?: Record<string, unknown>,
  ) => void;
  /** Edit-from-My-Workflows: pre-load the saved composition (agents + selections + name). */
  initialAgentIds?: string[];
  /**
   * The saved row's `manifest_json.steps`, when it has one. TAKES PRECEDENCE
   * over `initialAgentIds`.
   *
   * `agent_ids` is immutable after create — the API rejects composition edits
   * through it — so on a workflow that was later re-saved with a different
   * composition it holds the ORIGINAL agent list, not the current one. The
   * manifest is what Save actually rewrites (per-node skills, custom prompts and
   * the sub-agent tree all live there). Seeding from `agent_ids` reloaded a
   * workflow as whatever it looked like the day it was created and silently
   * dropped every custom agent and sub-agent.
   */
  initialManifestSteps?: ManifestStep[];
  initialSelections?: SelectionsMap;
  initialName?: string;
  initialDescription?: string;
  /**
   * Edit-from-My-Workflows: the saved row's own `id` (`WorkflowDefinition.id`,
   * from `GET /api/user-workflows`) — NOT the same thing as `workflowId` below
   * (that's the base pipeline/manifest id). When present, Save PATCHes this
   * existing row instead of POSTing a new one (avoids the 409 "already exists"
   * from re-creating a workflow under the same name).
   */
  initialUserWorkflowId?: string;
  /**
   * Edit-from-My-Workflows: the saved row's own deliverable/planner/clarify
   * (Workflow-tab rail state). Without this, reopening a saved workflow always
   * fell back to the Composer's hardcoded default ({streamed_text, output.md,
   * planner:skip, clarify:skip}) regardless of what was actually saved — so a
   * saved .html deliverable silently reverted to .md on every re-open/re-run.
   */
  initialRunConfig?: WorkflowRunConfig;
  /** SURF-03 — a known backend workflow id whose declared per-step caps are surfaced. */
  workflowId?: string;
}

const MAX_OPTIONAL = 8;

/**
 * 41-04 — the full-page Composer surface (mainView='composer'). ADDITIVE: a NEW
 * authoring surface reached from Home's "Compose a custom workflow" card and
 * edit-from-My-Workflows. It REUSES the AgentsPopup shared data model
 * (pipelineAgents order + SelectionsMap + declaredCapabilities) and its exported
 * sub-components (AdvancedExpander / CapabilityPaletteSection / HooksTab /
 * AgentPromptSection) — the AgentsPopup MODAL wrapper is RETAINED for the
 * wizard/input inline-edit flow, so this is NOT a dual implementation (INV-3).
 *
 * The header carries a Simple ⇄ Canvas toggle (D-03); Canvas is active by
 * default. Simple renders the mock-fidelity flat-list view.
 */
export function ComposerPage({
  workflowType,
  onBack,
  onRun,
  initialAgentIds,
  initialManifestSteps,
  initialSelections,
  initialName,
  initialDescription,
  initialUserWorkflowId,
  initialRunConfig,
  workflowId,
}: ComposerPageProps) {
  const { libraryAgents: LIBRARY_AGENTS, allAgents: ALL_LIBRARY_AGENTS } = useAgentLibrary();
  const { attachedHooks } = useSkillsHooks();
  const [view, setView] = useState<"simple" | "canvas">("canvas");
  // Bumped by the Save button — see CanvasView's resetLayoutSignal doc.
  const [canvasResetLayoutSignal, setCanvasResetLayoutSignal] = useState(0);
  // Tracks the saved row this session is editing (Edit-from-My-Workflows). Save
  // PATCHes this id when set instead of always POSTing a new row — set from
  // props on mount, and again after a successful first-time create so a SECOND
  // save in the same session updates rather than 409ing on the duplicate name.
  const [userWorkflowId, setUserWorkflowId] = useState<string | undefined>(
    initialUserWorkflowId,
  );
  const [name, setName] = useState(initialName ?? "");
  const [description, setDescription] = useState(initialDescription ?? "");
  const [saving, setSaving] = useState(false);
  // Save button feedback: idle -> saving (spinner) -> justSaved ("Saved" ✓,
  // reverts on its own) instead of the old flow (a name/description DIALOG on
  // every save, with no feedback once it closed — nothing told you it had
  // actually finished, so the instinct was to click Save again).
  const [justSaved, setJustSaved] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const nameInputRef = useRef<HTMLInputElement>(null);
  const [addOpen, setAddOpen] = useState(false);
  // What-to-build instruction for Run once — lives in the canvas's Brief node
  // (CanvasView renders it as a selectable node with its own rail box) rather
  // than a modal popup, so it's always visible instead of a transient dialog.
  // `briefFocusSignal` bumps on every Run click while the brief is too short;
  // CanvasView watches it to select the Brief node and focus its textarea.
  const [briefText, setBriefText] = useState("");
  const [briefFocusSignal, setBriefFocusSignal] = useState(0);
  // Same attach/PDF-extract/image logic IdeaInputPage's brief box has always
  // had (KAN-91 / Image-input Wave 2) — reused, not re-implemented (INV-3).
  // Shared by BOTH the Simple view's Brief card and Run once below.
  const briefAttachments = useBriefAttachments();
  const briefTextareaRef = useRef<HTMLTextAreaElement>(null);
  // Spec 012 (R-35) — id of the canvas node a pending "+ Sub-agent" add should
  // nest under. Set by CanvasView's onRequestAddSubAgent, cleared whenever the
  // library closes or a plain top-level add opens it, so a stale parent from a
  // PREVIOUS sub-agent add can never silently redirect a later normal add.
  const [subAgentParentId, setSubAgentParentId] = useState<string | null>(null);
  // The chain-insert "+" button between two root nodes reports which agent
  // the new one should land BEFORE (CanvasView's onAddAgent(insertBeforeId)).
  // Consumed by addAgent below; cleared on close/append so a stale value from
  // a PREVIOUS insert can never silently redirect a later plain (end) add.
  const [insertBeforeId, setInsertBeforeId] = useState<string | null>(null);
  // Spec 012 — skills ticked in the Add-agent library's per-agent drawer,
  // staged by LIBRARY agent id (not the minted node id — a template add mints
  // `custom-agent:<instance>` while the picker keys on the library `custom-agent`).
  // Merged onto the step by `addAgent`/`addSubAgent` when the agent is added, so
  // the drawer's write-back is honest: it lands on the new step, not a dropped click.
  const [pendingSkills, setPendingSkills] = useState<Record<string, string[]>>({});

  // Shared data model: the pipeline agent order + the per-agent SelectionsMap.
  const [pipelineAgents, setPipelineAgents] = useState<AgentDef[]>(() => {
    // Manifest first — see `initialManifestSteps`: `agent_ids` is frozen at
    // create time, so it is the wrong source for a re-saved composition.
    if (initialManifestSteps?.length) {
      return manifestStepsToAgents(initialManifestSteps, (id) =>
        ALL_LIBRARY_AGENTS.find((a) => a.id === id),
      );
    }
    if (initialAgentIds?.length) {
      return initialAgentIds
        .map((id) => ALL_LIBRARY_AGENTS.find((a) => a.id === id))
        .filter(Boolean) as AgentDef[];
    }
    return LIBRARY_AGENTS.filter((a) => agentMatchesPipelineType(a.pipeline_type, workflowType)).sort(
      (a, b) => a.order - b.order,
    );
  });
  const [selections, setSelections] = useState<SelectionsMap>(initialSelections ?? {});
  // Spec 012 (R-07/R-37) — workflow-level capability switches (internet toggle).
  const [capabilities, setCapabilities] = useState<WorkflowCapabilities>({});
  // Workflow-level run settings (deliverable/planner/clarify) — previously
  // hardcoded server-side defaults at launch (run_commands.py's Case 3
  // manifest synthesis); now UI-editable, persisted into manifest_json.
  const [runConfig, setRunConfig] = useState<WorkflowRunConfig>(
    initialRunConfig ?? {
      deliverable: { strategy: "streamed_text", name: "output.md" },
      planner: "skip",
      clarify: { mode: "skip", defaults: [] },
    },
  );
  const [draggedIdx, setDraggedIdx] = useState<number | null>(null);
  const [dragOverIdx, setDragOverIdx] = useState<number | null>(null);

  // SURF-03 — the opened workflow's declared per-step capabilities (compiled
  // projection), surfaced in the palette + summary. Skipped for from-scratch.
  const [declaredCapabilities, setDeclaredCapabilities] = useState<
    { step: string; capabilities: string[] }[] | undefined
  >(undefined);
  useEffect(() => {
    if (!workflowId) {
      setDeclaredCapabilities(undefined);
      return;
    }
    let cancelled = false;
    const jwt = getToken();
    if (!jwt) return;
    getWorkflowDetail(jwt, workflowId)
      .then((detail) => {
        if (cancelled) return;
        const mapped = detail.steps
          .map((s) => {
            const caps: string[] = [];
            if (s.strategy) caps.push(`strategy:${s.strategy}`);
            for (const g of s.gates) caps.push(`gate:${g}`);
            for (const v of s.validators) caps.push(`validator:${v}`);
            if (s.compaction) caps.push(`compaction:${s.compaction}`);
            if (s.task_source?.kind) caps.push(`task_source:${s.task_source.kind}`);
            for (const sk of s.skills ?? []) caps.push(`skill:${sk}`);
            return { step: s.name || s.agent_id, capabilities: caps };
          })
          .filter((d) => d.capabilities.length > 0);
        setDeclaredCapabilities(mapped.length > 0 ? mapped : undefined);
      })
      .catch(() => {
        if (!cancelled) setDeclaredCapabilities(undefined);
      });
    return () => {
      cancelled = true;
    };
  }, [workflowId]);

  const deliverableLabel = PIPELINE_LABEL[workflowType] ?? workflowType;
  const strategy = "sequential";

  const defaultAgentIds = new Set(
    LIBRARY_AGENTS.filter((a) => agentMatchesPipelineType(a.pipeline_type, workflowType)).map((a) => a.id),
  );
  const optionalCount = pipelineAgents.filter((a) => !defaultAgentIds.has(a.id)).length;
  const canAddMore = optionalCount < MAX_OPTIONAL;

  // ── Reorder / add / remove (native drag pattern mirrors AgentsPopup) ──────────
  const moveAgent = useCallback((i: number, dir: -1 | 1) => {
    setPipelineAgents((prev) => {
      const j = i + dir;
      if (j < 0 || j >= prev.length) return prev;
      const next = [...prev];
      [next[i], next[j]] = [next[j], next[i]];
      return next;
    });
  }, []);

  const handleDragStart = useCallback(
    (i: number) => {
      if (getRole(pipelineAgents[i].id, workflowType) === "locked") return;
      setDraggedIdx(i);
    },
    [pipelineAgents, workflowType],
  );
  const handleDragOver = useCallback((e: React.DragEvent, i: number) => {
    e.preventDefault();
    setDragOverIdx(i);
  }, []);
  const handleDrop = useCallback(
    (i: number) => {
      setDraggedIdx((from) => {
        if (from === null || from === i) return null;
        setPipelineAgents((prev) => {
          const next = [...prev];
          const [moved] = next.splice(from, 1);
          next.splice(i, 0, moved);
          return next;
        });
        return null;
      });
      setDragOverIdx(null);
    },
    [],
  );
  const handleDragEnd = useCallback(() => {
    setDraggedIdx(null);
    setDragOverIdx(null);
  }, []);

  const removeAgent = useCallback((id: string) => {
    setPipelineAgents((prev) => prev.filter((a) => a.id !== id));
    setSelections((prev) => {
      const next = { ...prev };
      delete next[id];
      return next;
    });
  }, []);

  const addAgent = useCallback(
    (agent: AgentDef) => {
      setPipelineAgents((prev) => {
        // The blank `custom-agent` template is reusable N times — mint a fresh
        // instance id per add. Without this the literal id `custom-agent` lands
        // in the pipeline and the dedup below blocks every later add.
        const node = instantiateIfTemplate(agent, collectAgentIds(prev));
        if (prev.find((a) => a.id === node.id)) return prev;
        const currentOptional = prev.filter((a) => !defaultAgentIds.has(a.id)).length;
        if (currentOptional >= MAX_OPTIONAL) return prev;
        // Skills ticked in the Add-agent drawer (pendingSkills, keyed by library
        // id) land on the new step; nothing pending means the node keeps its own.
        const skills = pendingSkills[agent.id];
        const newNode = { ...node, ...(skills ? { skills } : {}), order: prev.length + 1 };
        // A mid-chain "+" reports insertBeforeId (the root agent the new node
        // should land in front of) — splice there instead of always appending.
        const insertAt = insertBeforeId ? prev.findIndex((a) => a.id === insertBeforeId) : -1;
        return insertAt >= 0
          ? [...prev.slice(0, insertAt), newNode, ...prev.slice(insertAt)]
          : [...prev, newNode];
      });
      setPendingSkills((prev) => {
        const next = { ...prev };
        delete next[agent.id];
        return next;
      });
      setInsertBeforeId(null);
      setAddOpen(false);
    },
    [defaultAgentIds, pendingSkills, insertBeforeId],
  );

  // Spec 012 (R-35) — Simple-view counterpart of CanvasView's "+ Sub-agent"
  // add. Nests the picked agent under `subAgentParentId` (set by
  // onRequestAddSubAgent) instead of appending it to the top-level chain.
  const addSubAgent = useCallback(
    (agent: AgentDef) => {
      setPipelineAgents((prev) => {
        if (!subAgentParentId) return prev;
        const node = instantiateIfTemplate(agent, collectAgentIds(prev));
        // Same pending-skills merge as `addAgent` — the drawer write-back lands
        // on the sub-agent step too, not just top-level adds.
        const skills = pendingSkills[agent.id];
        return addChildInTree(prev, subAgentParentId, skills ? { ...node, skills } : node);
      });
      setPendingSkills((prev) => {
        const next = { ...prev };
        delete next[agent.id];
        return next;
      });
      setSubAgentParentId(null);
      setAddOpen(false);
    },
    [subAgentParentId, pendingSkills],
  );

  const handleAgentSelection = useCallback(
    (agentId: string, sel: StepSelection | undefined) => {
      setSelections((prev) => {
        const next = { ...prev };
        if (sel && Object.keys(sel).length > 0) next[agentId] = sel;
        else delete next[agentId];
        return next;
      });
    },
    [],
  );

  // Spec 013 — per-agent skill picker write-through for the Simple view. The
  // Simple view has no nested tree (unlike Canvas), so this writes directly
  // into `pipelineAgents`, the same state `Save` persists.
  const handleAgentSkillsChange = useCallback((agentId: string, skills: string[]) => {
    setPipelineAgents((prev) =>
      prev.map((a) => (a.id === agentId ? { ...a, skills } : a)),
    );
  }, []);

  // ── Brief-based agent recommendations + companion suggestions (KAN-121/FIX-112) ──
  // Mirrors IdeaInputPage recommendations, keyed on `briefText` — the SAME
  // Brief field Run once reads (previously this matched against `description`,
  // a field with no attach/PDF-extract functionality and no real "brief"
  // affordance on this page at all — recommendations existed with nothing
  // backing them). Uses shared functions (INV-12 — single source).
  const [dismissedRecs, setDismissedRecs] = useState<Set<string>>(new Set());
  const currentAgentIds = new Set(pipelineAgents.map((a) => a.id));
  const recommendations = workflowType === "custom"
    ? getAgentRecommendations(ALL_LIBRARY_AGENTS, briefText, currentAgentIds)
        .filter((a) => !dismissedRecs.has(a.id))
        .slice(0, 6)
    : [];
  const companionSuggestion = workflowType === "custom" ? (() => {
    for (const group of COMPANION_GROUPS) {
      const hasAny = group.ids.some((id) => currentAgentIds.has(id));
      const hasAll = group.ids.every((id) => currentAgentIds.has(id));
      if (hasAny && !hasAll) {
        const missing = group.ids.filter((id) => !currentAgentIds.has(id));
        return { group, missing };
      }
    }
    return null;
  })() : null;

  // ── Derived summary values (live, never fabricated — ND-AG) ───────────────────
  const gateCount = pipelineAgents.filter(
    (a) => (selections[a.id]?.gates?.length ?? 0) > 0 || !!a.gate,
  ).length;
  const totalSec = pipelineAgents.reduce((s, a) => s + a.estimated_duration, 0);
  const estMinutes = Math.max(1, Math.round(totalSec / 60));
  const estDurationLabel = `~${estMinutes}m`;

  const declaredSet = new Set<string>();
  for (const sel of Object.values(selections)) {
    (sel.validators ?? []).forEach((v) => declaredSet.add(v));
    (sel.gates ?? []).forEach((g) => declaredSet.add(g));
  }
  if (declaredCapabilities) {
    for (const d of declaredCapabilities) d.capabilities.forEach((c) => declaredSet.add(c));
  }
  const declaredChips = Array.from(declaredSet);

  // ── Save-to-catalogue (owner-scoped, via the shared saveUserWorkflow dispatch) ──
  const handleSave = useCallback(
    async (wfName: string, wfDescription: string) => {
      setSaveError(null);
      setJustSaved(false);
      const token = getToken();
      if (!token) {
        setSaveError("Not authenticated.");
        return;
      }
      setSaving(true);
      try {
        // ADR-0010 — `attached_skills` is NO LONGER WRITTEN. Skills are per-agent
        // (`Step.skills`) and round-trip inside `manifest_json` via
        // `selectionsBody` below, so sending a run-level bag here would persist a
        // second, coarser copy of the same intent. The backend still accepts and
        // migrates the column for rows saved before this change.
        const hooksBody =
          attachedHooks.length > 0
            ? {
                attached_hooks: attachedHooks.map((h) => ({
                  id: h.id,
                  name: h.name,
                  event: h.event,
                  trigger: h.trigger,
                  description: h.description || `${h.name}: ${h.trigger}`,
                })),
              }
            : {};

        // Spec 012 (R-27/T30/T36) — once a node carries a per-node skill, a
        // custom prompt, or a sub-agent tree, persist the FULL `{"steps":
        // [...]}` manifest so the tree shape itself round-trips through the
        // reused `manifest_json` column.
        //
        // It goes on its OWN wire field, not on `selections`: `selections` is
        // typed `dict[str, dict]` server-side, and a manifest's `steps` is a
        // LIST, so packing it into `selections` is rejected by pydantic before
        // any handler runs. The two fields are mutually exclusive (a 422 names
        // both) precisely because they write the same column.
        const selectionsBody = needsFullManifest(pipelineAgents)
          ? { manifest: buildWorkflowManifest(pipelineAgents, capabilities, selections, runConfig) }
          : Object.keys(selections).length > 0
            ? { selections }
            : {};

        // Editing an already-saved workflow (Edit-from-My-Workflows, or a second
        // save this session after the first create) → PATCH the existing row so
        // re-saving under the same name updates it instead of 409ing on a
        // duplicate. agent_ids/base_pipeline_type are immutable post-create, so
        // only name/description/selections/hooks round-trip on update —
        // saveUserWorkflow (ISS-167, lib/api.ts) owns that split so this isn't
        // hand-rolled per caller.
        const resp = await saveUserWorkflow(token, userWorkflowId, {
          name: wfName,
          // Update always sends description (so clearing it in the UI actually
          // clears the stored value); create omits an empty one rather than
          // persisting an explicit empty string — preserved exactly as before.
          ...(userWorkflowId || wfDescription ? { description: wfDescription } : {}),
          base_pipeline_type: workflowType,
          agent_ids: pipelineAgents.map((a) => a.id),
          ...selectionsBody,
          ...hooksBody,
        });
        setUserWorkflowId(resp.id);
        setName(wfName);
        setDescription(wfDescription);
        // CWF-001 D1: surface the backend's producer-first pre-sort — reorder the
        // visible rows to the persisted order. The backend is the authoritative
        // source (the FE AgentDef carries no produces/consumes), and it repairs a
        // consumer-before-producer order server-side. Guard on a present, non-empty
        // agent_ids so a response without it (or an older shape) leaves rows
        // untouched. An unsatisfiable composition instead throws below and renders
        // inline via saveError. Selections are keyed by agent_id → reorder-safe.
        // (PATCH's response carries the row's UNCHANGED existing agent_ids since
        // composition can't be edited via update — this reorder is then a no-op.)
        //
        // GUARDED: apply the reorder ONLY when every returned id matches a root
        // node already in `prev` — i.e. it's a true permutation. `resp.agent_ids`
        // can legitimately fail to line up 1:1 (e.g. a composed tree's synthetic
        // `custom-agent:<instance_id>` ids, or a manifest-backed save where the
        // backend's id set doesn't mirror the root array exactly); the previous
        // unconditional `.filter(Boolean)` silently DROPPED every non-matching
        // node from the canvas on save, with no error — the workflow was saved
        // correctly, but the in-memory state was corrupted until a reload
        // re-fetched the real (undamaged) saved row from the server.
        if (resp?.agent_ids?.length) {
          setPipelineAgents((prev) => {
            const byId = new Map(prev.map((a) => [a.id, a]));
            const reordered = resp.agent_ids
              .map((id) => byId.get(id))
              .filter((a): a is AgentDef => Boolean(a));
            return reordered.length === prev.length ? reordered : prev;
          });
        }
        setJustSaved(true);
        setTimeout(() => setJustSaved(false), 1800);
      } catch (e) {
        setSaveError((e as Error)?.message ?? "Failed to save workflow.");
      } finally {
        setSaving(false);
      }
    },
    [workflowType, pipelineAgents, selections, capabilities, runConfig, attachedHooks, userWorkflowId],
  );

  // ── Run-once (D-05 / D-CMP-RUN — through the EXISTING launch seam, ND-AG) ─────
  // Assemble the composed run and fire it through the parent `onRun` (which maps
  // onto the unchanged onStartPipeline → startPipeline seam). The base_pipeline_type
  // is the composer's fixed-at-entry `workflowType` ("custom" for the compose entry,
  // ND-AH) — the SAME value handleSave persists, so Run + Save carry an identical
  // base. The composed agent order → agent ids; the identity brief → the run message;
  // the per-step SelectionsMap + review-gate agents → extraParams (the SAME shared
  // data-model fields the existing launch already accepts — no fabricated cost).
  // KAN-121 / FIX-113: also inject __deliverable__ (mirrors IdeaInputPage.handleRun)
  // so the engine's _apply_selections swaps the compiled plan's deliverable spec
  // (e.g. single_file/prototype.html for prototype agents). Without this the engine
  // receives no override and uses the custom manifest default (streamed_text/output.md).
  const handleRunOnce = useCallback((instruction: string) => {
    if (!onRun) return;
    const trimmed = instruction.trim();
    if (!trimmed) return;
    // KAN-91: compose attached-file content into the message at send time —
    // the EXACT same block format/behavior as IdeaInputPage.handleRun (the
    // textarea itself stays clean; the extracted text only appears here).
    const brief = `${trimmed}${briefAttachments.fileBlocks}`;
    const gateAgentIds = pipelineAgents
      .filter((a) => (selections[a.id]?.gates?.length ?? 0) > 0 || !!a.gate)
      .map((a) => a.id);

    // Resolve the dispatch type and deliverable override from the chosen agent set.
    // This is the exact same call IdeaInputPage.handleRun makes — single source
    // via the exported resolveDispatchType (INV-12, no duplication).
    const { type: dispatchType, deliverableOverride } = resolveDispatchType(pipelineAgents, workflowType);

    // ADR-0010 — fold each agent's per-agent SKILLS into its selections entry.
    //
    // This is load-bearing, not tidy-up. A saved row's `manifest_json` is never
    // the run plan: the engine compiles its own file-backed plan at run entry and
    // overlays this selections map (`engine._apply_selections`). Save carries
    // skills via the manifest; RUN carries them only here. Without this the
    // composer would show a ticked skill, persist it, and silently never deliver
    // it to the agent — which is exactly what run-level `attached_skills` used to
    // paper over before it was retired.
    const skillSelections: Record<string, { skills: string[] }> = {};
    for (const a of pipelineAgents) {
      if (a.skills?.length) skillSelections[a.id] = { skills: [...a.skills] };
    }

    // Merge __deliverable__ into the per-agent selections map so the backend's
    // _apply_selections can swap the compiled deliverable spec at run entry.
    const withSkills: Record<string, unknown> = { ...selections };
    for (const [agentId, patch] of Object.entries(skillSelections)) {
      withSkills[agentId] = {
        ...((withSkills[agentId] as Record<string, unknown> | undefined) ?? {}),
        ...patch,
      };
    }
    // The live Workflow-tab picker (runConfig.deliverable) is the source of truth
    // whenever the user has one — resolveDispatchType's agent-id heuristic never
    // recognizes Composer custom-agent instances, so it falls back to a stale
    // hardcoded default that used to reach __deliverable__ on its own and silently
    // out-race the live pick applied via `deliverable` below (KAN-121 regression).
    // Both fields are now derived from the SAME value so they can't disagree.
    const effectiveDeliverable = runConfig?.deliverable ?? deliverableOverride;
    const mergedSelections = effectiveDeliverable
      ? { ...withSkills, __deliverable__: effectiveDeliverable }
      : withSkills;

    // Case 3 (R-27/T30/T36 shape — a per-node skill, custom prompt, or sub-agent
    // tree) needs the backend to compile the saved manifest_json directly
    // (trust="db"), since dynamically-generated custom-agent instance ids can
    // never appear in the static allow-list agent_ids alone is checked against.
    // Added ALONGSIDE agent_ids (not instead of) — Case 1/2 launches are
    // unaffected, and the backend already ignores agent_ids once user_workflow_id
    // resolves to a manifest row. Only sent once the workflow has been saved at
    // least once (userWorkflowId set); an unsaved Case-3 composition still runs
    // via the pre-existing flat path until the user saves.
    // Run settings (deliverable/planner/clarify/internet) — the Composer's
    // Workflow-tab rail state, sent as this run's live values so the backend's
    // USER_WORKFLOW_MANIFEST branch uses them instead of falling back to a
    // saved-but-stale manifest or its own hardcoded default.
    const extraParams: Record<string, unknown> = {
      ...(Object.keys(mergedSelections).length > 0 ? { selections: mergedSelections } : {}),
      ...(gateAgentIds.length > 0 ? { gate_agent_ids: gateAgentIds } : {}),
      ...(needsFullManifest(pipelineAgents) && userWorkflowId
        ? { user_workflow_id: userWorkflowId }
        : {}),
      ...(effectiveDeliverable ? { deliverable: effectiveDeliverable } : {}),
      ...(runConfig?.planner ? { planner: runConfig.planner } : {}),
      ...(runConfig?.clarify ? { clarify: runConfig.clarify } : {}),
      ...(capabilities ? { capabilities } : {}),
      // Image-input Wave 2 (D3) — images ride OUT-OF-BAND, never inlined into
      // `brief`. Same shape/condition as IdeaInputPage.handleRun.
      ...(briefAttachments.attachedImages.length > 0
        ? { images: briefAttachments.attachedImages }
        : {}),
    };
    onRun(
      dispatchType,
      brief,
      pipelineAgents.map((a) => a.id),
      Object.keys(extraParams).length > 0 ? extraParams : undefined,
    );
  }, [
    onRun,
    pipelineAgents,
    selections,
    workflowType,
    userWorkflowId,
    runConfig,
    capabilities,
    briefAttachments.fileBlocks,
    briefAttachments.attachedImages,
  ]);

  const segBtn = (id: "simple" | "canvas", label: string, Icon: typeof GitBranch) => (
    <button
      type="button"
      onClick={() => setView(id)}
      className={`inline-flex items-center gap-1.5 rounded-[7px] px-3 py-1.5 font-sans text-[12px] font-semibold transition-colors ${
        view === id
          ? "bg-surface-white text-ink-900 shadow-sm"
          : "text-ink-400 hover:text-ink-700"
      }`}
    >
      <Icon className="h-3.5 w-3.5" />
      {label}
    </button>
  );

  return (
    <div className="flex h-full flex-col overflow-hidden bg-surface-paper text-ink-900">
      {/* Header */}
      <div className="flex flex-none items-center gap-3.5 border-b border-line-divider bg-surface-warm px-[34px] py-[15px]">
        <button
          type="button"
          onClick={onBack}
          aria-label="Back"
          className="grid h-9 w-9 flex-none place-items-center rounded-[9px] border border-line-control bg-surface-card text-ink-700 transition-colors hover:border-line-faint"
        >
          <ArrowLeft className="h-4 w-4" />
        </button>
        <div className="min-w-0 flex-1">
          <p className="mb-0.5 font-sans text-[10px] font-semibold uppercase tracking-[0.15em] text-ink-300">
            {deliverableLabel} · Composer
          </p>
          {/* Name + description edit directly here now — no more "Save" dialog
              popping up every time just to type/change these two fields. */}
          <input
            ref={nameInputRef}
            aria-label="Workflow name"
            name="workflow-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Untitled workflow"
            className="block w-full max-w-[420px] truncate rounded-md border border-transparent bg-transparent px-1 -mx-1 font-sans text-[22px] font-light leading-none tracking-tight text-ink-900 placeholder-ink-300 focus:border-line-control focus:bg-surface-white focus:outline-none"
          />
          <input
            aria-label="Workflow description"
            name="workflow-description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Add a description…"
            className="block mt-0.5 w-full max-w-[420px] truncate rounded-md border border-transparent bg-transparent px-1 -mx-1 font-serif text-[12px] text-ink-400 placeholder-ink-300 focus:border-line-control focus:bg-surface-white focus:text-ink-700 focus:outline-none"
          />
        </div>

        {/* Run summary — agent/review-gate counts + live est. duration. Moved
            here from the per-view docked panels (Canvas's bottom rail /
            Simple's SummaryRail) so both views share ONE glanceable summary
            that's always visible, not two competing copies further down. */}
        <div
          data-testid="composer-header-summary"
          className="hidden items-center gap-3 rounded-[10px] border border-line-control bg-surface-card px-3.5 py-2 font-sans text-[11.5px] font-semibold text-ink-700 md:flex"
        >
          <span className="whitespace-nowrap">
            <span className="tabular-nums">{pipelineAgents.length}</span>{" "}
            <span className="font-normal text-ink-300">agents</span>
          </span>
          <span className="h-3 w-px flex-none bg-line-faint-row" />
          <span className="whitespace-nowrap">
            <span className="tabular-nums">{gateCount}</span>{" "}
            <span className="font-normal text-ink-300">review gate</span>
          </span>
          <span className="h-3 w-px flex-none bg-line-faint-row" />
          <span className="whitespace-nowrap tabular-nums">{estDurationLabel}</span>
        </div>

        {/* Simple ⇄ Canvas toggle (Canvas mounts in 41-05) */}
        <div className="flex items-center gap-1 rounded-[9px] border border-line-control bg-surface-card p-1">
          {segBtn("simple", "Simple", LayoutList)}
          {segBtn("canvas", "Canvas", GitBranch)}
        </div>

        {/* Run + Save — the SINGLE pair of actions for the whole composer.
            Previously there were three save entry points across the header
            ("Save draft"/"Save workflow", identical no-op-different labels)
            and each view's own docked panel; collapsed to one of each here. */}
        <button
          type="button"
          onClick={() => {
            if (briefText.trim().length < 3) {
              // Not enough of a brief yet — focus it wherever the user
              // already is, rather than always jumping to Canvas: Simple
              // has its own Brief card now, so switching away from it would
              // fight the view the user is actually looking at.
              if (view === "simple") {
                briefTextareaRef.current?.focus();
              } else {
                setBriefFocusSignal((n) => n + 1);
              }
              return;
            }
            handleRunOnce(briefText);
          }}
          disabled={!onRun}
          title={
            !onRun
              ? "Run wiring lands in 41-06"
              : briefText.trim().length < 3
                ? "Add a brief first"
                : undefined
          }
          className={`inline-flex items-center gap-1.5 rounded-[10px] border border-line-control bg-surface-card px-3.5 py-2.5 font-sans text-[12.5px] font-semibold text-ink-700 transition-colors enabled:hover:border-line-faint enabled:hover:bg-surface-warm enabled:active:scale-[0.97] disabled:opacity-40 ${
            briefText.trim().length < 3 ? "opacity-60" : ""
          }`}
        >
          <Play className="h-3.5 w-3.5" />
          Run once
        </button>
        <button
          type="button"
          onClick={() => {
            if (!name.trim()) {
              nameInputRef.current?.focus();
              return;
            }
            setCanvasResetLayoutSignal((n) => n + 1);
            handleSave(name.trim(), description.trim());
          }}
          disabled={saving}
          title={!name.trim() ? "Name the workflow first" : undefined}
          className={`inline-flex w-[148px] items-center justify-center gap-2 rounded-[10px] px-[18px] py-2.5 font-sans text-[12.5px] font-semibold text-surface-white transition-colors enabled:active:scale-[0.97] disabled:cursor-not-allowed ${
            justSaved ? "bg-status-done" : "bg-brand enabled:hover:bg-brand-pressed disabled:opacity-50"
          }`}
        >
          {saving ? (
            <>
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              Saving…
            </>
          ) : justSaved ? (
            <>
              <Check className="h-3.5 w-3.5" />
              Saved
            </>
          ) : (
            <>
              <Save className="h-3.5 w-3.5" />
              Save workflow
            </>
          )}
        </button>
      </div>

      {/* Body */}
      <div className="min-h-0 flex-1">
        {view === "canvas" ? (
          <CanvasView
            pipelineAgents={pipelineAgents}
            selections={selections}
            pipelineType={workflowType}
            onSelection={handleAgentSelection}
            onRemoveAgent={removeAgent}
            onAddAgent={(insertBefore) => {
              setSubAgentParentId(null);
              setInsertBeforeId(insertBefore ?? null);
              setAddOpen(true);
            }}
            canAddMore={canAddMore}
            declaredCapabilities={declaredChips}
            // Spec 012 (R-35/R-37/T30) — every canvas tree edit (add sub-agent,
            // rename, skills, prompt, strategy) round-trips through the SAME
            // `pipelineAgents` state Save persists; the internet toggle is
            // workflow-level, not per-node.
            onTreeChange={setPipelineAgents}
            onRequestAddSubAgent={(parentId) => {
              setSubAgentParentId(parentId);
              setInsertBeforeId(null);
              setAddOpen(true);
            }}
            capabilities={capabilities}
            onCapabilitiesChange={setCapabilities}
            runConfig={runConfig}
            onRunConfigChange={setRunConfig}
            briefText={briefText}
            onBriefTextChange={setBriefText}
            briefFocusSignal={briefFocusSignal}
            resetLayoutSignal={canvasResetLayoutSignal}
            briefAttachments={briefAttachments}
          />
        ) : (
          <div className="h-full overflow-y-auto">
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.2 }}
            className="mx-auto grid max-w-[1200px] grid-cols-1 items-start gap-[22px] px-[34px] pb-[70px] pt-[30px] lg:grid-cols-[1fr_320px]"
          >
            {/* Main column */}
            <div>
              <IdentityCard
                name={name}
                description={description}
                deliverableLabel={deliverableLabel}
                onNameChange={setName}
                onDescriptionChange={setDescription}
              />

              {/* Brief — the SAME textarea + attach/PDF-extract UI IdeaInputPage
                  has always had (KAN-91 / Image-input Wave 2), reused here via
                  BriefAttachBox/useBriefAttachments (INV-3, no forked logic).
                  Feeds the SAME briefText Run once + the Canvas Brief node
                  already read — so a PDF dropped here reaches the run exactly
                  like it does from the standalone Prototype flow. */}
              <div className="mb-4 rounded-[14px] border border-line-border bg-surface-card px-[22px] py-5">
                <div className="mb-1.5 flex items-center gap-2.5">
                  <Paperclip className="h-4 w-4 text-ink-700" />
                  <h2 className="font-sans text-[15px] font-semibold text-ink-900">
                    Brief
                  </h2>
                </div>
                <p className="mb-3 font-serif text-[12px] leading-relaxed text-ink-400">
                  What should this run build? Attach PDFs, docs, or images — text is
                  extracted and included automatically.
                </p>
                <div className="rounded-[12px] border border-line-control overflow-hidden">
                  <BriefAttachBox
                    value={briefText}
                    onChange={setBriefText}
                    placeholder="Describe what you want this workflow to produce…"
                    attachments={briefAttachments}
                    textareaRef={briefTextareaRef}
                    onSubmitShortcut={() => handleRunOnce(briefText)}
                    rows={4}
                  />
                </div>
              </div>

              {/* KAN-121 / FIX-112: Brief-based agent recommendations.
                  Fires when the brief has ≥10 chars. Same logic as IdeaInputPage. */}
              {recommendations.length > 0 && (
                <div className="mb-4 rounded-[13px] border border-brand/15 bg-brand/[0.04] px-4 py-3">
                  <div className="mb-2 flex items-center gap-1.5">
                    <Sparkles className="h-3.5 w-3.5 text-brand" />
                    <p className="font-sans text-[10px] font-semibold uppercase tracking-wide text-brand">
                      Suggested agents for your brief
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {recommendations.map((agent) => (
                      <button
                        key={agent.id}
                        type="button"
                        onClick={() => addAgent(agent)}
                        title={agent.description}
                        className="flex items-center gap-1.5 rounded-full border border-brand/20 bg-surface-white px-2.5 py-1 font-sans text-[11px] font-medium text-ink-700 transition-colors hover:border-brand hover:bg-brand hover:text-surface-white"
                      >
                        {agent.name.replace(/ Agent$/, "")}
                        <Plus className="h-3 w-3 opacity-50" />
                      </button>
                    ))}
                    <button
                      type="button"
                      onClick={() => setDismissedRecs(new Set(recommendations.map((a) => a.id)))}
                      className="self-center px-1 font-sans text-[10px] text-ink-300 hover:text-ink-600"
                    >
                      Dismiss
                    </button>
                  </div>
                </div>
              )}

              {/* KAN-121 / FIX-112: Companion suggestion — incomplete pipeline banner. */}
              {companionSuggestion && (
                <div className="mb-4 rounded-[13px] border border-amber-200 bg-amber-50 px-4 py-3">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0 flex-1">
                      <p className="font-sans text-[11px] font-semibold text-amber-800">
                        {companionSuggestion.group.label}
                      </p>
                      <p className="mt-0.5 font-serif text-[10px] leading-relaxed text-amber-700">
                        {companionSuggestion.group.description}
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => {
                        const groupIds = new Set(companionSuggestion.group.ids);
                        const nonGroupAgents = pipelineAgents.filter((a) => !groupIds.has(a.id));
                        const fullGroupAgents = companionSuggestion.group.ids
                          .map((id) => ALL_LIBRARY_AGENTS.find((a) => a.id === id))
                          .filter(Boolean) as AgentDef[];
                        setPipelineAgents([...fullGroupAgents, ...nonGroupAgents]);
                      }}
                      className="flex flex-shrink-0 items-center gap-1 rounded-lg bg-amber-100 px-2.5 py-1 font-sans text-[11px] font-semibold text-amber-800 transition-colors hover:bg-amber-200 hover:text-amber-900"
                    >
                      <Plus className="h-3 w-3" />
                      Add {companionSuggestion.missing.length} missing
                    </button>
                  </div>
                </div>
              )}

              {/* Agent pipeline header */}
              <div className="mx-0.5 mb-3 flex items-center justify-between">
                <div>
                  <h2 className="font-sans text-[15px] font-semibold text-ink-900">
                    Agent pipeline
                  </h2>
                  <p className="font-serif text-[11.5px] text-ink-300">
                    {pipelineAgents.length} agents · runs {strategy} · drag to reorder
                  </p>
                </div>
                <span className="group relative inline-flex">
                  <button
                    type="button"
                    onClick={() => {
                      setSubAgentParentId(null);
                      setInsertBeforeId(null);
                      setAddOpen(true);
                    }}
                    disabled={!canAddMore}
                    className="inline-flex items-center gap-1.5 rounded-[9px] border border-line-control bg-surface-card px-3.5 py-2.5 font-sans text-[12px] font-semibold text-ink-700 transition-colors enabled:hover:border-brand enabled:hover:text-brand disabled:cursor-not-allowed disabled:opacity-70"
                  >
                    <Plus className="h-3.5 w-3.5" />
                    Add agent
                  </button>
                  {/* Same styled hover-tooltip as the Canvas view's insert
                      buttons (CapTip) — not a native `title=` — so the cap
                      reason reads identically everywhere. */}
                  {!canAddMore && (
                    <span
                      role="tooltip"
                      className="pointer-events-none absolute right-0 top-full z-20 mt-1.5 w-[190px] rounded-[8px] border border-line-control bg-surface-card px-2.5 py-2 text-center font-sans text-[11px] normal-case tracking-normal leading-relaxed text-ink-700 opacity-0 shadow-lg transition-opacity group-hover:opacity-100"
                    >
                      Maximum 8 root agents are allowed
                    </span>
                  )}
                </span>
              </div>

              {/* Agent rows */}
              <div className="flex flex-col gap-2.5">
                {pipelineAgents.length === 0 ? (
                  <div className="rounded-[13px] border border-dashed border-line-control bg-surface-card px-4 py-10 text-center font-serif text-[12.5px] text-ink-300">
                    No agents yet — add one from the catalogue to start composing.
                  </div>
                ) : (
                  pipelineAgents.map((agent, i) => (
                    <div key={agent.id}>
                      <AgentRow
                        agent={agent}
                        index={i}
                        total={pipelineAgents.length}
                        pipelineType={workflowType}
                        selection={selections[agent.id]}
                        onSelection={handleAgentSelection}
                        onSkillsChange={handleAgentSkillsChange}
                        onMoveUp={() => moveAgent(i, -1)}
                        onMoveDown={() => moveAgent(i, 1)}
                        onRemove={() => removeAgent(agent.id)}
                        isDragOver={dragOverIdx === i}
                        onDragStart={() => handleDragStart(i)}
                        onDragOver={(e) => handleDragOver(e, i)}
                        onDrop={() => handleDrop(i)}
                        onDragEnd={handleDragEnd}
                      />
                      {/* The Simple view is a flat list — a sub-agent tree only
                          has an editable UI in Canvas. Without this, a workflow
                          with sub-agents opened in Simple view silently hid
                          them. Read-only + indented: editing a sub-agent still
                          requires switching to Canvas, but Simple can no longer
                          make it look like they don't exist. */}
                      {agent.children?.length ? (
                        <SubAgentReadOnlyList agents={agent.children} />
                      ) : null}
                    </div>
                  ))
                )}
              </div>

              {/* Hooks (REUSE HooksTab) — ADR-0010: skills moved to the per-agent
                  AgentSkillsPicker on each agent row / canvas rail. */}
              <div className="mt-4 rounded-[14px] border border-line-border bg-surface-card px-[22px] py-5">
                <h2 className="mb-1 font-sans text-[15px] font-semibold text-ink-900">
                  Hooks
                </h2>
                <p className="mb-2 font-serif text-[12px] leading-relaxed text-ink-400">
                  Inject domain instructions and pre/post behaviours across the whole
                  workflow.
                </p>
                <HooksTab pipelineType={workflowType} />
              </div>
            </div>

            {/* Summary rail */}
            <SummaryRail
              agentCount={pipelineAgents.length}
              gateCount={gateCount}
              strategy={strategy}
              estDurationLabel={estDurationLabel}
            />
          </motion.div>
          </div>
        )}
      </div>

      {saveError && (
        <div className="flex-none px-[34px] pb-3 font-serif text-[11px] text-status-failed">
          {saveError}
        </div>
      )}

      {/* Add agent (REUSE AgentLibrary) */}
      <AgentLibrary
        isOpen={addOpen}
        onClose={() => {
          setAddOpen(false);
          setSubAgentParentId(null);
          setInsertBeforeId(null);
        }}
        onAddAgent={addAgent}
        onAddAsSubAgent={subAgentParentId ? addSubAgent : undefined}
        // Spec 012 — live the Skills tab in the drawer; the selection is staged
        // in `pendingSkills` and merged onto the step by addAgent/addSubAgent.
        onSkillsChange={(agentId, skills) =>
          setPendingSkills((prev) => ({ ...prev, [agentId]: skills }))
        }
        subAgentParentName={
          subAgentParentId ? findAgentInTree(pipelineAgents, subAgentParentId)?.name : undefined
        }
        currentPipelineType={workflowType}
        canAddMore={canAddMore}
        // collectAgentIds walks the WHOLE tree (root + nested) — a flat
        // root-only map missed agents already added as a sub-agent, letting
        // the same built-in agent be picked twice (once nested, once root).
        existingAgentIds={collectAgentIds(pipelineAgents)}
      />
    </div>
  );
}
