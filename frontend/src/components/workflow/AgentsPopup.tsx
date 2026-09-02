"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useEscapeToClose } from "@/hooks/useEscapeToClose";
import { motion, AnimatePresence } from "motion/react";
import {
  X, Plus, Lock, GripVertical, Info,
  Clock, Zap, BookMarked, CheckCircle2, ChevronRight, ChevronDown,
  Puzzle, Webhook, Search, Check, Sliders, AlertCircle, Settings2, Cpu,
  FileText, Edit3, RotateCcw, Maximize2,
} from "lucide-react";
import { AgentLibrary } from "./AgentLibrary";
import { CanvasView } from "./composer/CanvasView";
import { useBriefAttachments } from "./IdeaInputPage";
import { addChildInTree, collectAgentIds, findAgentInTree, instantiateIfTemplate } from "@/store/api/userWorkflows";
import type { HookDef } from "@/store/api/hooks";
// NOTE: the API fetcher `getCapabilities` is aliased to `fetchCapabilities` to
// avoid the NAME COLLISION with the local `getCapabilities(agent)` helper below
// (the local one derives display strings from an agent description; the import
// fetches the live `/api/capabilities` registry payload — D-02 reuse shell).
import {
  getCapabilities as fetchCapabilities,
  getToken,
  getAgentPrompt,
  saveAgentPromptOverride,
  deleteAgentPromptOverride,
  saveUserWorkflow,
  type CapabilityEntry,
  type CapabilityModelEntry,
  type AgentPromptData,
} from "@/lib/api";
import { NameWorkflowModal } from "@/components/catalog/NameWorkflowModal";
import type { AgentDef, WorkflowType, AttachedHook, AgentToolGrants, WorkflowRunConfig } from "@/types/index";
import { useHooksCatalog } from "@/hooks/useHooksCatalog";
import { useSkillsCatalog } from "@/hooks/useSkillsCatalog";
import { AgentSkillsPicker } from "@/components/workflow/composer/AgentSkillsPicker";
import { useSkillsHooks } from "@/context/SkillsHooksContext";
import { Tabs } from "@/components/ui/Tabs";
import { useAppSelector } from "@/store/hooks";
import { getPrimaryPipelineType } from "@/lib/workflowIcons";

// ─── Props ────────────────────────────────────────────────────────────────────

interface AgentsPopupProps {
  isOpen: boolean;
  onClose: () => void;
  /** Debug only: names the remount generation, so the console shows whether this
   *  mount saw the manifest-seeded selections or the empty pre-fetch ones. */
  debugLabel?: string;
  /** Reopen this same composition in the FULL-PAGE Composer. This modal already
   *  renders composer/CanvasView, so it is the same canvas at full size — not a
   *  second surface. Omitted by callers that have nowhere to navigate to. */
  onOpenInCanvas?: () => void;
  /**
   * ISS-167 (follow-up) — the reopened saved workflow's identity, so this
   * popup's OWN footer "Save workflow" button (distinct from any page-level
   * save button a caller may also render) updates the existing row in place
   * instead of always creating a new one via NameWorkflowModal. Absent ⇒
   * always creates new (today's behavior, unchanged) — a caller that hasn't
   * been wired to restore a saved workflow's id simply omits these.
   */
  userWorkflowId?: string;
  savedName?: string;
  savedDescription?: string;
  /**
   * Spec 016 — this user has saved their OWN version of this built-in workflow.
   * When true the header renders a checkbox that swaps `agents` between their
   * version and the system one. Absent (the default) for every user who has
   * never saved an override, and for every caller that has not wired this up —
   * the header then renders exactly as before.
   */
  /**
   * The workflow's DECLARED run config (deliverable / planner / clarify), from
   * `GET /api/workflows/{id}`. Read-only here — no `onRunConfigChange` is
   * forwarded, so the rail's controls stay disabled exactly as before.
   *
   * Without it the rail fell back to CanvasView's blank-canvas defaults and
   * told every user that ppt outputs `streamed_text`/`output.md` with planning
   * and clarify off, when its manifest declares `ppt`/`presentation.pptx`,
   * `planner: run` and `clarify: auto`. Four wrong values on a read-only panel.
   */
  runConfig?: WorkflowRunConfig;
  overrideAvailable?: boolean;
  /** Whether the override is currently the one being shown AND the one that
   *  will run. Persisted server-side, not view-local: a display-only toggle
   *  would let this modal show one plan while the launch executed another. */
  overrideActive?: boolean;
  onToggleOverride?: (next: boolean) => void;
  agents: AgentDef[];
  pipelineType: WorkflowType;
  /** `insertBeforeId` is the root agent the new one should land IN FRONT OF —
   *  reported by the canvas's "+" affordances (including the head one, between
   *  the Brief pill and step 1). Omitted ⇒ append. A caller that ignores the
   *  second argument keeps its previous append-only behaviour. */
  /**
   * Offer the blank `custom-agent` template in the agent library? Default true.
   * The LaunchWizard passes false — see AgentLibrary.allowCustomAgentTemplate
   * for why a file-less step cannot be launched inside a built-in.
   */
  allowCustomAgentTemplate?: boolean;
  onAddAgent?: (agent: AgentDef, insertBeforeId?: string) => void;
  onRemoveAgent?: (agentId: string) => void;
  onReorder?: (agents: AgentDef[]) => void;
  canAddMore?: boolean;
  attachedHooks?: AttachedHook[];
  onAttachHook?: (hook: AttachedHook) => void;
  onDetachHook?: (hookId: string) => void;
  /**
   * LEGACY (ISS-014 / MODEL-03) — per-agent model-overrides callback, retained
   * for caller compatibility (the IdeaInputPage composer flow threads its own
   * `model_overrides` for saved-workflow reload). AgentsPopup NO LONGER emits
   * overrides here: per-agent model selection is the inline Model lever, reported
   * via `onSelectionsChange` as `selections[id].model` — the single source of
   * truth (the standalone AgentModelPicker that once drove this is gone).
   */
  onModelOverridesChange?: (modelOverrides: Record<string, string>) => void;
  /**
   * EMP-01 (D-05) — the per-agent Advanced expander's compact selections map
   * (agentId -> {validators?, gates?, model?, retry?}). Reported upward so
   * IdeaInputPage can thread it into the save payload as `selections` (the EXACT
   * shape 22-04 persists in manifest_json and `_apply_selections` consumes).
   * Additive — omit to ignore advanced lever selection.
   */
  onSelectionsChange?: (selections: SelectionsMap) => void;
  /**
   * LEGACY (WR-01 / LAUNCH-EXISTING-PATH §4.6) — a saved-workflow model-override
   * seed, retained for caller compatibility. AgentsPopup no longer reads it: the
   * inline Model lever seeds per-agent model from `initialSelections`
   * (`selections[id].model`); the IdeaInputPage composer flow still owns the
   * separate model_overrides reload path.
   */
  initialModelOverrides?: Record<string, string>;
  /**
   * WR-01 — seed the Advanced expander's per-step selections map when launching a
   * saved workflow, so the persisted `manifest_json` levers (validators / gates /
   * model / retry) re-load AND re-send on launch. Absent ⇒ the expander starts empty
   * (compose-from-scratch). Additive — preserves the byte-identical no-selections path.
   */
  initialSelections?: SelectionsMap;
  /**
   * ISS-247 — the LIVE per-step selections map, owned by the caller. When
   * supplied the popup renders from THIS map instead of its own mount-once copy
   * of `initialSelections`, so a gate set OUTSIDE the modal (the Review-gates
   * checklist, which writes the same `selections[id].gates` the Config rail's
   * Gate combobox reads) is visible INSIDE it. Absent ⇒ the popup keeps owning
   * its own copy, unchanged.
   */
  selections?: SelectionsMap;
  /**
   * SURF-03 — the opened launchable workflow's declared per-step capabilities
   * (compiled projection). Threaded into the embedded palette so the composer
   * shows what the workflow already uses before composing. Absent on
   * compose-from-scratch.
   */
  declaredCapabilities?: { step: string; capabilities: string[] }[];
}

// ─── Constants ────────────────────────────────────────────────────────────────

const LOCKED_AGENT_IDS = new Set([
  "domain-analyst", "backlog-compiler",
  "ppt-content-strategist", "ppt-assembler",
  "requirements-analyst", "prototype-finalizer",
  "material-analyzer", "app-sdlc-governance",
  "repo-scanner", "documentation-generator",
  "mulesoft-inventory", "mulesoft-sdlc-governance",
  "dotnet-inventory", "dotnet-sdlc-governance",
  // od_ppt pipeline agents — all core, none removable
  "ppt-brief-analyst", "ppt-composer", "ppt-validator",
  // od_prototype pipeline agents — all core, none removable
  "prototype-specify", "prototype-plan", "prototype-analyze", "prototype-build", "prototype-validate",
]);

const REQUIRED_AGENT_IDS = new Set([
  "epic-architect", "story-estimator", "nfr-specialist", "backlog-reviewer",
  "ppt-slide-architect", "ppt-code-generator",
  "html-prototype-builder", "prototype-polisher",
  "app-user-stories", "app-system-design", "app-security-architecture",
  "app-ux-design", "app-api-design", "app-database-design",
  "app-code-generator", "app-feature-implementation", "app-infra-generator",
  "app-code-compliance", "app-test-implementation",
  "app-test-compliance", "app-devops",
  "deep-analyzer", "modernization-planner",
  "mulesoft-user-stories", "mulesoft-decomposition", "mulesoft-security-architecture",
  "mulesoft-springboot-scaffold", "mulesoft-feature-coding",
  "mulesoft-dataweave-translator", "mulesoft-aws-infra",
  "mulesoft-code-compliance", "mulesoft-test-implementation",
  "mulesoft-test-compliance", "mulesoft-validation",
  "dotnet-user-stories", "dotnet-azure-target-mapping", "dotnet-security-architecture",
  "dotnet-modernization", "dotnet-feature-coding",
  "dotnet-azure-bicep", "dotnet-azure-ai",
  "dotnet-code-compliance", "dotnet-test-implementation",
  "dotnet-test-compliance", "dotnet-validation",
]);

type AgentRole = "locked" | "required" | "optional";

// EXPORTED (41-04): reused by the full-page Composer (composer/AgentRow) for the
// per-agent Core/Required lock badge — the SAME role predicate the modal uses,
// so the composer and the retained modal agree on which agents are locked.
export function getRole(agentId: string, pipelineType: WorkflowType): AgentRole {
  const isNativeLocked = LOCKED_AGENT_IDS.has(agentId);
  const isNativeRequired = REQUIRED_AGENT_IDS.has(agentId);
  if (!isNativeLocked && !isNativeRequired) return "optional";
  const pipelinePrefixes: Record<string, string[]> = {
    user_stories: ["domain-analyst", "epic-architect", "story-estimator", "nfr-specialist", "backlog-reviewer", "backlog-compiler"],
    ppt: ["ppt-content-strategist", "ppt-slide-architect", "ppt-code-generator", "ppt-assembler",
          "ppt-brief-analyst", "ppt-composer", "ppt-validator"],
    prototype: ["requirements-analyst", "html-prototype-builder", "prototype-polisher", "prototype-finalizer",
                "prototype-specify", "prototype-plan", "prototype-analyze", "prototype-build", "prototype-validate"],
    app_builder: [
      "material-analyzer", "app-user-stories", "app-system-design",
      "app-security-architecture", "app-ux-design", "app-api-design",
      "app-database-design", "app-code-generator", "app-feature-implementation",
      "app-infra-generator", "app-code-compliance", "app-test-implementation",
      "app-test-compliance", "app-devops", "app-sdlc-governance",
    ],
    mulesoft_to_springboot: [
      "mulesoft-inventory", "mulesoft-user-stories", "mulesoft-decomposition",
      "mulesoft-security-architecture", "mulesoft-springboot-scaffold", "mulesoft-feature-coding",
      "mulesoft-dataweave-translator", "mulesoft-aws-infra", "mulesoft-code-compliance",
      "mulesoft-test-implementation", "mulesoft-test-compliance", "mulesoft-validation",
      "mulesoft-sdlc-governance",
    ],
    dotnet_to_azure: [
      "dotnet-inventory", "dotnet-user-stories", "dotnet-azure-target-mapping",
      "dotnet-security-architecture", "dotnet-modernization", "dotnet-feature-coding",
      "dotnet-azure-bicep", "dotnet-azure-ai", "dotnet-code-compliance",
      "dotnet-test-implementation", "dotnet-test-compliance", "dotnet-validation",
      "dotnet-sdlc-governance",
    ],
    custom: [],
  };
  const nativeAgents = pipelinePrefixes[pipelineType] || [];
  if (!nativeAgents.includes(agentId)) return "optional";
  if (isNativeLocked) return "locked";
  if (isNativeRequired) return "required";
  return "optional";
}

// EXPORTED (41-04): the Composer's read-only Deliverable-type label (ND-AH) reads
// the SAME pipeline→label map the modal uses.
export const PIPELINE_LABEL: Record<string, string> = {
  user_stories: "User Stories", ppt: "Presentation", prototype: "Prototype",
  app_builder: "App Builder", custom: "Custom",
  mulesoft_to_springboot: "Mulesoft → Spring Boot", dotnet_to_azure: ".NET → Azure",
};

const ICON_STYLES = [
  { bg: "var(--brand-fill)", text: "var(--brand)" }, { bg: "#F0EDE8", text: "#5C4A2A" },
  { bg: "#EAF0EA", text: "#2A5C2A" }, { bg: "#F0E8EE", text: "#5C2A4A" },
  { bg: "#E8EEF0", text: "#2A4A5C" }, { bg: "#F0EEE8", text: "#5C5A2A" },
];

// EXPORTED (41-04): the Composer's AgentRow avatar reuses the modal's initials rule.
export function getAgentInitials(name: string): string {
  const words = name.replace(/\s+agent$/i, "").split(" ");
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[1][0]).toUpperCase();
}

function getCapabilities(agent: AgentDef): string[] {
  const desc = agent.description;
  const parts = desc.split(/,\s*(?:and\s+)?|;\s*/).filter(p => p.trim().length > 10);
  if (parts.length >= 2) return parts.map(p => p.trim()).slice(0, 5);
  return [desc];
}


// ─── AgentPromptSection (KAN-76) ─────────────────────────────────────────────
// Collapsible section shown inside AgentCapabilitiesModal.
// Displays the base AGENT.md prompt body (read-only view) and — unless
// `surfaceOnly` is set — allows editing a per-user prompt override.
//
// ND-7 / LOCK-E (37-06): the Agent-drawer Config tab mounts this with
// `surfaceOnly` so the override PERSISTENCE is DEFERRED — the write affordances
// (Edit / Save override / Revert-to-default, which call PUT/DELETE
// /api/agents/{id}/prompt) are OMITTED. The prompt body + override state stay
// VIEW-only; no durable write path is reachable from the drawer.

// EXPORTED (41-04): the Composer's AgentRow "Custom prompt →" affordance reuses
// this exact section (surfaceOnly) — no forked prompt editor.
export function AgentPromptSection({
  agent,
  surfaceOnly = false,
}: {
  agent: AgentDef;
  /** ND-7: when set, omit all write affordances — read-only prompt view only. */
  surfaceOnly?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [promptData, setPromptData] = useState<AgentPromptData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editMode, setEditMode] = useState(false);
  const [draftContent, setDraftContent] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  // Fetch prompt data on first open
  useEffect(() => {
    if (!open || promptData !== null) return;
    const token = getToken();
    if (!token) return;
    setLoading(true);
    setError(null);
    getAgentPrompt(token, agent.id)
      .then(d => { setPromptData(d); })
      .catch(e => setError(e?.message ?? "Failed to load prompt."))
      .finally(() => setLoading(false));
  }, [open, agent.id, promptData]);

  const handleEditStart = () => {
    if (!promptData) return;
    setDraftContent(promptData.override ?? promptData.prompt_body);
    setEditMode(true);
    setSaveError(null);
  };

  const handleSave = async () => {
    if (!promptData) return;
    const token = getToken();
    if (!token) return;
    setSaving(true);
    setSaveError(null);
    try {
      await saveAgentPromptOverride(token, agent.id, draftContent);
      setPromptData({ ...promptData, override: draftContent, has_override: true });
      setEditMode(false);
    } catch (e) {
      setSaveError((e as Error)?.message ?? "Failed to save.");
    } finally {
      setSaving(false);
    }
  };

  const handleRevert = async () => {
    if (!promptData) return;
    const token = getToken();
    if (!token) return;
    setSaving(true);
    setSaveError(null);
    try {
      await deleteAgentPromptOverride(token, agent.id);
      setPromptData({ ...promptData, override: null, has_override: false });
      setEditMode(false);
    } catch (e) {
      setSaveError((e as Error)?.message ?? "Failed to revert.");
    } finally {
      setSaving(false);
    }
  };

  const displayContent = editMode
    ? draftContent
    : (promptData?.override ?? promptData?.prompt_body ?? "");

  return (
    <div className="rounded-xl overflow-hidden bg-surface-near-black">
      {/* Collapsible header */}
      <button
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-white/5 transition-colors text-left"
      >
        <div className="flex items-center gap-2.5">
          <FileText className="h-4 w-4 text-ink-400 flex-shrink-0" />
          <div>
            <p className="text-[11px] font-semibold text-white">System Prompt</p>
            <p className="text-[10px] text-ink-400">
              {promptData?.has_override ? "Custom override active" : "Base AGENT.md prompt"}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {promptData?.has_override && (
            <span className="text-[9px] font-semibold px-1.5 py-0.5 rounded bg-brand-fill text-brand">overridden</span>
          )}
          <ChevronDown className={`h-3.5 w-3.5 text-ink-400 transition-transform ${open ? "rotate-180" : ""}`} />
        </div>
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.18 }}
            className="overflow-hidden border-t border-white/10"
          >
            <div className="bg-surface-near-black">
              {loading && (
                <p className="text-[11px] text-ink-400 px-4 py-3">Loading prompt…</p>
              )}
              {error && (
                <p className="text-[11px] text-red-400 px-4 py-3">{error}</p>
              )}
              {!loading && !error && promptData && (
                <>
                  {/* Source badge */}
                  <div className="flex items-center justify-between px-4 pt-3 pb-2 gap-2">
                    <span className={`text-[9px] font-semibold px-2 py-0.5 rounded-full border ${
                      promptData.has_override
                        ? "bg-brand-fill text-brand border-brand-border"
                        : "bg-white/10 text-ink-300 border-white/20"
                    }`}>
                      {promptData.has_override ? "Your override" : "Default AGENT.md"}
                    </span>
                    {/* ND-7 / LOCK-E: the drawer Config tab passes `surfaceOnly`,
                        which OMITS every write affordance (Revert / Edit → Save)
                        so no durable override PUT/DELETE is reachable. */}
                    {!surfaceOnly && (
                    <div className="flex items-center gap-1.5">
                      {promptData.has_override && !editMode && (
                        <button
                          onClick={handleRevert}
                          disabled={saving}
                          className="flex items-center gap-1 text-[10px] text-gray-400 hover:text-red-600 transition-colors disabled:opacity-40"
                        >
                          <RotateCcw className="h-3 w-3" /> Revert to default
                        </button>
                      )}
                      {!editMode && (
                        <button
                          onClick={handleEditStart}
                          className="flex items-center gap-1.5 text-[12px] font-semibold text-white/80 hover:text-surface-near-black transition-colors px-3 py-1 rounded-md border border-white/20 hover:bg-white"
                        >
                          <Edit3 className="h-3.5 w-3.5" /> Edit
                        </button>
                      )}
                    </div>
                    )}
                  </div>

                  {/* Prompt content — surfaceOnly forces the read-only view (the
                      edit textarea + Save override control are never reachable). */}
                  {editMode && !surfaceOnly ? (
                    <div className="px-4 pb-3 space-y-2">
                      <textarea
                        value={draftContent}
                        onChange={e => setDraftContent(e.target.value)}
                        rows={12}
                        aria-label="Custom agent prompt"
                        name="agent-prompt"
                        className="w-full px-3 py-2 text-[11px] font-mono bg-surface-white text-ink-900 border border-line-control rounded-lg focus:outline-none focus:border-ink-400 resize-none leading-relaxed transition-colors"
                        placeholder="Enter custom prompt instructions…"
                      />
                      <p className="text-[9px] text-ink-400">{draftContent.length} chars · max 32,768</p>
                      {saveError && (
                        <p className="text-[11px] text-status-failed">{saveError}</p>
                      )}
                      <div className="flex items-center gap-2 justify-end">
                        <button
                          onClick={() => { setEditMode(false); setSaveError(null); }}
                          className="px-3 py-1.5 rounded-lg text-[11px] font-medium text-ink-500 hover:bg-line-faint-row transition-colors"
                        >
                          Cancel
                        </button>
                        <button
                          onClick={handleSave}
                          disabled={saving || !draftContent.trim()}
                          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-brand text-white text-[11px] font-semibold hover:bg-brand-pressed transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                        >
                          {saving ? "Saving…" : <><Check className="h-3 w-3" /> Save override</>}
                        </button>
                      </div>
                    </div>
                  ) : (
                    <p className="px-4 pb-4 pt-1 text-[13px] text-white font-sans leading-relaxed whitespace-pre-wrap overflow-x-auto max-h-64 overflow-y-auto">
                      {displayContent || <span className="text-ink-400 italic">No prompt body found.</span>}
                    </p>
                  )}
                </>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}


// ─── AgentCapabilitiesModal ───────────────────────────────────────────────────

export function AgentCapabilitiesModal({
  agent, agentIndex, onClose,
  attachedHooks: propHooks,
  onAttachHook: propAttachHook,
  onSkillsChange,
  onSelectionsChange, initialSelections, token,
  priorAgents,
  asDrawer = false,
}: {
  agent: AgentDef;
  agentIndex: number;
  onClose: () => void;
  attachedHooks?: AttachedHook[];
  onAttachHook?: (hook: AttachedHook) => void;
  /**
   * ADR-0010 — per-agent skill attachment. When supplied, the Skills tab writes
   * the agent's new skill-id list back through this callback (the composer then
   * stores it on the step). When OMITTED there is no step to write to — the
   * Library page opens this drawer for a catalog agent that belongs to no
   * pipeline — and the Skills tab renders read-only rather than offering
   * controls that discard the click.
   */
  onSkillsChange?: (agentId: string, skills: string[]) => void;
  /** Pass-through to AdvancedExpander for per-agent config levers */
  onSelectionsChange?: (selections: SelectionsMap) => void;
  initialSelections?: SelectionsMap;
  token?: string | null;
  /**
   * 51-06 — the pipeline agents preceding this one, threaded to the
   * AdvancedExpander fan-out source picker so a single-agent config surface can
   * still offer earlier steps as the fan-out `source_step` (D7/§4e).
   */
  priorAgents?: { id: string; name: string }[];
  /**
   * Render as a slide-in-from-right DRAWER (the Library agent-detail surface,
   * mock `drawerOpen`) instead of the default centered modal. Only the shell
   * (scrim layout + panel chrome + slide animation) changes — the four tab
   * bodies (Overview/Skills/Hooks/Config) are identical across both forms.
   */
  asDrawer?: boolean;
}) {
  const { hooks: HOOKS, events: HOOK_EVENTS } = useHooksCatalog();
  // Always use context — works from Library page, Add agent modal, and AgentsPopup.
  // HOOKS ONLY since ADR-0010; skills come from `agent.skills` and are written
  // back through `onSkillsChange`, not through this context.
  const ctx = useSkillsHooks();
  const attachedHooks = ctx.attachedHooks;
  const onAttachHook = ctx.attachHook;

  // SHELL-04 (37-06): the drawer is a 4-tab inspector. Overview is the default
  // surface; Config carries the ND-7/LOCK-E surface-only prompt-override.
  const [drawerTab, setDrawerTab] = useState<
    "overview" | "skills" | "hooks" | "config"
  >("overview");

  // Local per-agent selections state for the Config tab when the caller does
  // not supply onSelectionsChange (e.g. LibraryPage drawer). Merges with the
  // prop-driven path so AdvancedExpander always renders in the Config tab.
  const [localSelections, setLocalSelections] = useState<SelectionsMap>(initialSelections ?? {});
  // Always notify BOTH the local state AND the parent prop so:
  // - local display updates immediately (setLocalSelections)
  // - parent persists the value (onSelectionsChange)
  const effectiveOnSelectionsChange = (next: SelectionsMap) => {
    setLocalSelections(next);
    onSelectionsChange?.(next);
  };
  // Always use localSelections for the Config tab display — it is seeded from
  // initialSelections on mount and updated by every lever change or Save call.
  const effectiveSelections = localSelections;

  // Spec 012 — the same mirror for the Skills tab when the caller supplies
  // onSkillsChange (the drawer mounts: AgentLibrary add-agent modal, LibraryPage).
  // AgentSkillsPicker derives from `agent.skills`, but those mounts pass a STATIC
  // catalog agent, so without local state a toggle would never re-render checked
  // and the next toggle would recompute from the stale set — silently dropping
  // the previous pick. Mirror here, seeded from `agent.skills`, and report every
  // change both locally (re-render) and up (onSkillsChange → composer/ref).
  const [localSkills, setLocalSkills] = useState<string[] | undefined>(
    onSkillsChange ? agent.skills : undefined,
  );
  const effectiveOnSkillsChange = (agentId: string, skills: string[]) => {
    setLocalSkills(skills);
    onSkillsChange?.(agentId, skills);
  };
  const skillsAgent = localSkills !== undefined ? { ...agent, skills: localSkills } : agent;

  // Skill id → name resolution for the Overview tab's Attached-skills chips.
  const { skills: SKILLS } = useSkillsCatalog();
  const attachedSkillNames = useMemo(
    () =>
      (skillsAgent.skills ?? []).map((id) => ({
        id,
        name: SKILLS.find((s) => s.id === id)?.name ?? id,
      })),
    [skillsAgent.skills, SKILLS],
  );

  // resetKey: incrementing this remounts ConfigLeversFlat (key prop), which
  // re-seeds its localSel from the now-empty effectiveSelections — the correct
  // React-idiomatic way to reset child state from a parent.
  const [resetKey, setResetKey] = useState(0);
  // saved: brief "Saved ✓" feedback on the Save button before closing.
  const [saved, setSaved] = useState(false);

  const iconStyle = ICON_STYLES[agentIndex % ICON_STYLES.length];
  const capabilities = getCapabilities(agent);
  const pipelineLabel = PIPELINE_LABEL[getPrimaryPipelineType(agent.pipeline_type)] ?? getPrimaryPipelineType(agent.pipeline_type);

  // ISS-491: AgentCapabilitiesModal declared role="dialog" / aria-modal="true" with
  // no Escape handler — the same gap FIX-388 closed for WorkflowDialog. The shared
  // hook already exists (useEscapeToClose); two lines and it is fixed.
  useEscapeToClose(onClose);

  // ISS-399: AgentSkillsPicker uses `!s.compatible_agents?.length || ...includes()`
  // as the "compatible with everything" fallback (R-33). The hooks filter had no
  // equivalent — a hook whose compatible_agents list was emptied of stale ids by
  // FIX-360 would never suggest for any real agent. Add the same fallback so an
  // empty list means "compatible with all" rather than "matches nothing".
  const suggestedHooks = HOOKS.filter(h => !h.compatible_agents?.length || h.compatible_agents.includes(agent.id)).slice(0, 3);

  const isHookAttached = (id: string) => attachedHooks.some(h => h.id === id);

  const handleAttachHook = (hook: HookDef) => {
    if (isHookAttached(hook.id)) return;
    onAttachHook?.({
      id: hook.id, name: hook.name, event: hook.event, trigger: hook.trigger,
      description: hook.description,
    });
  };

  return (
    <motion.div
      initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      className={asDrawer
        ? "fixed inset-0 z-[80] flex justify-end bg-black/40"
        : "fixed inset-0 z-[80] flex items-center justify-center p-6 bg-black/30 backdrop-blur-sm"}
      onClick={onClose}
    >
      <motion.div
        data-testid={asDrawer ? "agent-drawer" : undefined}
        role="dialog"
        aria-modal="true"
        aria-label={`${agent.name} details`}
        initial={asDrawer ? { x: "100%" } : { opacity: 0, scale: 0.96, y: 12 }}
        animate={asDrawer ? { x: 0 } : { opacity: 1, scale: 1, y: 0 }}
        exit={asDrawer ? { x: "100%" } : { opacity: 0, scale: 0.96, y: 12 }}
        transition={asDrawer
          ? { duration: 0.32, ease: [0.32, 0.72, 0, 1] }
          : { duration: 0.18 }}
        onClick={e => e.stopPropagation()}
        className={asDrawer
          ? "bg-surface-paper shadow-[-24px_0_60px_rgba(17,17,20,0.22)] w-[472px] max-w-full h-full overflow-hidden flex flex-col"
          : "bg-surface-white rounded-2xl shadow-2xl border border-line-control w-full max-w-md overflow-hidden max-h-[90vh] flex flex-col"}
      >
        {/* Header */}
        <div className="px-6 pt-6 pb-4 border-b border-line-divider flex-shrink-0">
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="w-11 h-11 rounded-xl flex items-center justify-center flex-shrink-0 text-[13px] font-bold"
                style={{ background: iconStyle.bg, color: iconStyle.text }}>
                {getAgentInitials(agent.name)}
              </div>
              <div>
                <h2 className="text-[15px] font-bold text-ink-900 leading-tight">{agent.name}</h2>
                <p className="text-[11px] text-ink-500 mt-0.5">{agent.role}</p>
              </div>
            </div>
            <button onClick={onClose} className="h-7 w-7 flex items-center justify-center rounded-lg text-ink-400 hover:text-ink-700 hover:bg-surface-warm transition-all flex-shrink-0">
              <X className="h-4 w-4" />
            </button>
          </div>
          {/* SHELL-04: 4-tab inspector (Overview/Skills/Hooks/Config) — reuses
              the shipped per-agent sections, distributed across tabs. */}
          <Tabs
            className="mt-3"
            active={drawerTab}
            onChange={(id) => setDrawerTab(id as typeof drawerTab)}
            tabs={[
              { id: "overview", label: "Overview" },
              { id: "skills", label: "Skills" },
              { id: "hooks", label: "Hooks" },
              { id: "config", label: "Config" },
            ]}
          />
        </div>

        {/* Scrollable body */}
        <div className="overflow-y-auto flex-1 px-6 py-4 space-y-4">

          {/* Overview tab — what this agent does + pipeline step */}
          {drawerTab === "overview" && (
          <>
          {/* Meta chip row — duration · pipeline-type · skill-support. Matches the
              mock's Overview chip row (relocated out of the header, which now
              mirrors the mock: avatar/name/role + tab bar only). Skill-support is
              bound to the agent's REAL has_skill (SC-001/ND-D: never fabricate —
              the chip is omitted when the agent declares no skill support). */}
          <div className="flex items-center flex-wrap gap-2">
            <span className="flex items-center gap-1 text-[11px] font-medium text-ink-600 bg-surface-white border border-line-control px-2.5 py-1 rounded-full">
              <Clock className="h-3 w-3" />~{agent.estimated_duration}s
            </span>
            <span className="text-[11px] font-medium text-ink-700 bg-surface-white border border-line-control px-2.5 py-1 rounded-full">{pipelineLabel}</span>
            {agent.has_skill && (
              <span className="flex items-center gap-1 text-[11px] font-medium text-ink-700 bg-surface-white border border-line-control px-2.5 py-1 rounded-full">
                <BookMarked className="h-2.5 w-2.5" />Skill support
              </span>
            )}
          </div>

          {/* 1. What it does (mock heading) */}
          <div>
            <div className="flex items-center gap-2 mb-2.5">
              <Zap className="h-3.5 w-3.5 text-ink-400" />
              <p className="text-[10px] font-semibold text-ink-500 uppercase tracking-wide">What it does</p>
            </div>
            <div className="space-y-2">
              {capabilities.map((cap, i) => (
                <div key={i} className="flex items-start gap-2.5">
                  <CheckCircle2 className="h-3.5 w-3.5 text-ink-400 flex-shrink-0 mt-0.5" />
                  <p className="text-[12px] text-ink-700 leading-relaxed">{cap}</p>
                </div>
              ))}
            </div>
          </div>

          {/* 2. Role in pipeline — the agent's ROLE NAME (matches the mock's
              "ROLE IN PIPELINE" block; the generic step index is dropped). */}
          <div className="rounded-xl border border-line-divider bg-surface-warm px-4 py-3">
            <p className="text-[10px] font-semibold text-ink-400 uppercase tracking-wide mb-1.5">Role in pipeline</p>
            <div className="flex items-center gap-2">
              <span className="text-[11px] font-medium px-2 py-0.5 rounded-md border bg-line-faint-row text-ink-600 border-line-control">{pipelineLabel}</span>
              <ChevronRight className="h-3 w-3 text-ink-300" />
              <span className="text-[11px] text-ink-600 font-medium">{agent.role}</span>
            </div>
          </div>

          {/* 2b. Attached skills — the ticked set from the Skills tab, rendered
              as chips. Derives from `skillsAgent` (the local mirror) so a toggle
              in the Skills tab updates this live, no remount needed. */}
          {attachedSkillNames.length > 0 && (
            <div>
              <div className="flex items-center gap-2 mb-2.5">
                <Puzzle className="h-3.5 w-3.5 text-ink-400" />
                <p className="text-[10px] font-semibold text-ink-500 uppercase tracking-wide">Attached skills</p>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {attachedSkillNames.map((s) => (
                  <span
                    key={s.id}
                    title={s.name}
                    className="flex items-center gap-1 rounded-full border border-brand-border bg-brand-fill px-2.5 py-1 text-[11px] font-medium text-brand"
                  >
                    {s.name}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* 3. System Prompt (ND-7 / LOCK-E) — read-only surface showing the base
              agent prompt with optional override state. surfaceOnly hides write affordances. */}
          <AgentPromptSection agent={agent} surfaceOnly={true} />

          </>
          )}

          {/* Config tab — per-agent configuration levers (Model · Validator · Gate ·
              Retry) shown FLAT — no expand/collapse chrome. ND-7/LOCK-E: System
              Prompt surfaces READ-ONLY (surfaceOnly) in Config tab; durable override
              persistence is DEFERRED (no PUT/DELETE path reachable). */}
          {drawerTab === "config" && (
          <>
          <p className="text-[12px] text-ink-500 leading-relaxed">
            Overrides for this agent. Defaults inherit from the workflow.
          </p>

          {/* System Prompt (ND-7 / LOCK-E) — surfaceOnly hides the write affordances */}
          <AgentPromptSection agent={agent} surfaceOnly={true} />

          {/* Flat lever rows (reuse useAgentCapabilities + applyLeverPatch — same
              source as AdvancedExpander, no forked logic, INV-12). */}
          <ConfigLeversFlat
            key={resetKey}
            agentId={agent.id}
            agentName={agent.name}
            token={token ?? getToken()}
            selections={effectiveSelections}
            onSelectionsChange={effectiveOnSelectionsChange}
          />

          {/* Reset / Save agent buttons — match the design mock. */}
          <div className="flex items-center gap-3 pt-2 border-t border-line-border">
            <button
              type="button"
              onClick={() => {
                // Clear parent selections and increment resetKey so React
                // remounts ConfigLeversFlat with fresh empty localSel.
                setSaved(false);
                setLocalSelections({});
                onSelectionsChange?.({});
                setResetKey((k) => k + 1);
              }}
              className="flex-1 rounded-[10px] border border-line-control bg-surface-card px-4 py-2.5 font-sans text-[13px] font-medium text-ink-700 hover:bg-surface-warm"
            >
              Reset
            </button>
            <button
              type="button"
              onClick={() => {
                // Persist the current selections to the parent (e.g. LibraryPage
                // savedSelectionsRef) so reopening the drawer restores them.
                onSelectionsChange?.(localSelections);
                // Show "Saved ✓" briefly before closing.
                setSaved(true);
                setTimeout(() => {
                  setSaved(false);
                  onClose();
                }, 900);
              }}
              disabled={saved}
              className={`flex-[2] rounded-[10px] px-4 py-2.5 font-sans text-[13px] font-semibold text-white ${
                saved
                  ? "bg-status-done cursor-default"
                  : "bg-brand hover:bg-brand-pressed"
              }`}
            >
              {saved ? "✓ Saved" : "Save agent"}
            </button>
          </div>
          </>
          )}


          {/* Hooks tab — Suggested Hooks */}
          {drawerTab === "hooks" && (
          <>
          {/* Suggested Hooks */}
          {suggestedHooks.length > 0 ? (
            <div>
              <div className="flex items-center gap-2 mb-2.5">
                <Webhook className="h-3.5 w-3.5 text-ink-400" />
                <p className="text-[10px] font-semibold text-ink-500 uppercase tracking-wide">Suggested Hooks</p>
              </div>
              <div className="space-y-1.5">
                {suggestedHooks.map(hook => {
                  const attached = isHookAttached(hook.id);
                  return (
                    <div key={hook.id} className="flex items-center justify-between gap-3 rounded-lg border border-line-divider bg-surface-warm px-3 py-2">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-1.5 mb-0.5">
                          <p className="text-[11px] font-semibold text-ink-800 truncate">{hook.name}</p>
                          <span className="text-[9px] font-semibold px-1.5 py-0.5 rounded bg-line-control text-ink-500 flex-shrink-0">{hook.event}</span>
                        </div>
                        <p className="text-[10px] text-ink-500 leading-relaxed line-clamp-1">{hook.description}</p>
                      </div>
                      <button
                        onClick={() => handleAttachHook(hook)}
                        disabled={attached}
                        className={`flex-shrink-0 flex items-center gap-1 px-2.5 py-1 rounded-lg text-[10px] font-semibold transition-colors ${
                          attached
                            ? "bg-line-faint-row text-ink-400 cursor-default"
                            : "bg-brand text-white hover:bg-brand-pressed cursor-pointer"
                        }`}
                      >
                        {attached ? <><Check className="h-2.5 w-2.5" /> Added</> : <><Plus className="h-2.5 w-2.5" /> Attach</>}
                      </button>
                    </div>
                  );
                })}
              </div>
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center py-8 text-center">
              <Webhook className="h-8 w-8 text-ink-200 mb-3" />
              <p className="text-[13px] font-medium text-ink-500">No suggested hooks</p>
              <p className="text-[11px] text-ink-400 mt-1 leading-relaxed max-w-[220px]">
                There are no pre-built hooks recommended for this agent.
              </p>
            </div>
          )}
          </>
          )}

          {/* Skills tab — the SHARED per-agent picker (ADR-0010).

              This tab used to offer two RUN-LEVEL attach paths: a catalog list
              and a "write a custom skill" editor, both calling ctx.attachSkill
              so the skill landed on every agent in the launch rather than on
              this one. Both are gone.

              The custom-skill editor has no per-agent equivalent and was NOT
              ported: `Step.skills` is a list of catalog skill IDs, and there is
              nowhere to put ad-hoc inline `content`. Authoring a new skill is a
              skills-catalog concern, not an agent-inspector one. */}
          {drawerTab === "skills" && (
            <AgentSkillsPicker
              agent={skillsAgent}
              onSkillsChange={effectiveOnSkillsChange}
              readOnly={!onSkillsChange}
            />
          )}

        </div>
      </motion.div>
    </motion.div>
  );
}


// ─── HooksTab ─────────────────────────────────────────────────────────────────

// EXPORTED (41-04): the Composer's "Hooks" card reuses this whole section —
// bound to the shared SkillsHooksContext, so the modal and the composer share
// ONE attached-hooks source of truth.
//
// ADR-0010: this used to be `SkillsHooksTab` and rendered a SKILLS picker above
// the hooks picker. That picker attached skills at the RUN level — one bag
// applied to every agent in the launch — which is a second source of truth for
// the same thing as per-agent `Step.skills`. Skills are now attached to an agent
// via `composer/AgentSkillsPicker`, and this tab is hooks-only. Hooks stay
// run-level because no per-step hooks field exists in the manifest to move them
// to.
export function HooksTab({ pipelineType }: { pipelineType: WorkflowType }) {
  const { hooks: HOOKS, events: HOOK_EVENTS } = useHooksCatalog();
  const { attachedHooks, attachHook, detachHook } = useSkillsHooks();
  const [hooksOpen, setHooksOpen] = useState(false);
  const [hookSearch, setHookSearch] = useState("");
  const [hookEvent, setHookEvent] = useState("all");

  const isHookAttached = (id: string) => attachedHooks.some(h => h.id === id);

  const filteredHooks = HOOKS.filter(h => {
    const matchEvent = hookEvent === "all" || h.event === hookEvent;
    const matchSearch = !hookSearch ||
      h.name.toLowerCase().includes(hookSearch.toLowerCase()) ||
      h.description.toLowerCase().includes(hookSearch.toLowerCase());
    return matchEvent && matchSearch;
  });

  return (
    <div className="flex-1 overflow-y-auto p-5 space-y-5">

      {/* ── HOOKS SECTION ── */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Webhook className="h-4 w-4 text-ink-400" />
            <span className="text-[13px] font-semibold text-ink-800">Hooks</span>
            {attachedHooks.length > 0 && (
              <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded-full bg-brand text-white">{attachedHooks.length}</span>
            )}
          </div>
          <button
            onClick={() => setHooksOpen(v => !v)}
            className="flex items-center gap-1 text-[11px] font-semibold text-ink-500 hover:text-ink-900 transition-colors"
          >
            <Plus className="h-3.5 w-3.5" /> Add hook
          </button>
        </div>

        {/* Attached hooks */}
        {attachedHooks.length > 0 && (
          <div className="space-y-1.5 mb-3">
            {attachedHooks.map(hook => (
              <div key={hook.id} className="flex items-center justify-between gap-3 rounded-lg border border-line-control bg-surface-white px-3 py-2">
                <div className="flex items-center gap-2 min-w-0">
                  <CheckCircle2 className="h-3.5 w-3.5 text-ink-500 flex-shrink-0" />
                  <span className="text-[12px] font-semibold text-ink-800 truncate">{hook.name}</span>
                  <span className="text-[9px] font-semibold px-1.5 py-0.5 rounded bg-line-faint-row text-ink-500 flex-shrink-0">{hook.event}</span>
                </div>
                <button onClick={() => detachHook(hook.id)} className="flex-shrink-0 text-ink-300 hover:text-status-failed transition-colors">
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
            ))}
          </div>
        )}

        {attachedHooks.length === 0 && !hooksOpen && (
          <div className="rounded-lg border border-dashed border-line-control px-4 py-3 text-center">
            <p className="text-[11px] text-ink-400">No hooks attached · click &quot;Add hook&quot; to browse</p>
          </div>
        )}

        {/* Hooks picker */}
        {hooksOpen && (
          <motion.div
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            className="rounded-xl border border-line-control bg-surface-card overflow-hidden"
          >
            <div className="p-3 border-b border-line-divider space-y-2">
              <div className="relative">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3 w-3 text-ink-400" />
                <input
                  aria-label="Search hooks"
                  name="hook-search"
                  value={hookSearch}
                  onChange={e => setHookSearch(e.target.value)}
                  placeholder="Search hooks..."
                  className="w-full pl-7 pr-3 py-1.5 text-[11px] bg-surface-warm border border-line-control rounded-lg focus:outline-none focus:border-ink-400 placeholder-ink-400"
                />
              </div>
              <div className="flex gap-1 flex-wrap">
                {HOOK_EVENTS.map(ev => (
                  <button
                    key={ev.id}
                    onClick={() => setHookEvent(ev.id)}
                    className={`px-2 py-0.5 rounded-full text-[9px] font-semibold transition-colors ${
                      hookEvent === ev.id
                        ? "bg-brand text-white"
                        : "bg-line-faint-row text-ink-500 hover:bg-line-control"
                    }`}
                  >
                    {ev.label}
                  </button>
                ))}
              </div>
            </div>
            <div className="max-h-[240px] overflow-y-auto divide-y divide-line-divider">
              {filteredHooks.length === 0 ? (
                <p className="text-[11px] text-ink-400 text-center py-4">No hooks found</p>
              ) : filteredHooks.map(hook => {
                const attached = isHookAttached(hook.id);
                return (
                  <div key={hook.id} className="flex items-start justify-between gap-3 px-3 py-2.5 hover:bg-surface-warm transition-colors">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1.5 mb-0.5">
                        <p className="text-[11px] font-semibold text-ink-800">{hook.name}</p>
                        <span className="text-[9px] font-semibold px-1.5 py-0.5 rounded bg-line-faint-row text-ink-500">{hook.event}</span>
                      </div>
                      <p className="text-[10px] text-ink-500 leading-relaxed line-clamp-2">{hook.description}</p>
                      <p className="text-[9px] text-ink-400 mt-0.5 italic">{hook.trigger}</p>
                    </div>
                    <button
                      onClick={() => {
                        if (!attached) {
                          attachHook({ id: hook.id, name: hook.name, event: hook.event, trigger: hook.trigger, description: hook.description });
                        }
                      }}
                      disabled={attached}
                      className={`flex-shrink-0 flex items-center gap-1 px-2.5 py-1 rounded-lg text-[10px] font-semibold transition-colors mt-0.5 ${
                        attached ? "bg-line-faint-row text-ink-400 cursor-default" : "bg-brand text-white hover:bg-brand-pressed"
                      }`}
                    >
                      {attached ? <><Check className="h-2.5 w-2.5" /> Added</> : <><Plus className="h-2.5 w-2.5" /> Add</>}
                    </button>
                  </div>
                );
              })}
            </div>
            <div className="p-2 border-t border-line-divider flex justify-end">
              <button onClick={() => setHooksOpen(false)} className="text-[10px] text-ink-400 hover:text-ink-700 px-2 py-1">Done</button>
            </div>
          </motion.div>
        )}
      </div>

      {/* Info note */}
      <div className="rounded-xl border border-line-divider bg-surface-warm px-4 py-3">
        <p className="text-[10px] text-ink-500 leading-relaxed">
          <span className="font-semibold text-ink-700">Skills</span> inject domain-specific instructions into agent prompts.{" "}
          <span className="font-semibold text-ink-700">Hooks</span> define pre/post behaviours that guide agent execution.
        </p>
      </div>
    </div>
  );
}


// ─── CapabilityPaletteSection (SURF-01/03 + EMP-02) ───────────────────────────

/**
 * Title-case a capability `kind` for the per-group header. Derived ENTIRELY from
 * the payload `kind` (e.g. "context_provider" → "Context providers") — there is
 * NO hardcoded kind list anywhere (SC-001). `s` underscores become spaces; the
 * first letter is capitalised; a trailing pluralisation makes the group header
 * read naturally ("Validators", "Gates", "Strategies").
 */
function titleCaseKind(kind: string): string {
  const spaced = kind.replace(/_/g, " ").trim();
  if (!spaced) return kind;
  const base = spaced.charAt(0).toUpperCase() + spaced.slice(1);
  // Naive English pluralisation sufficient for capability kinds.
  if (/[^aeiou]y$/.test(base)) return base.slice(0, -1) + "ies";
  if (/(s|x|z|ch|sh)$/.test(base)) return base + "es";
  return base + "s";
}

/**
 * The embedded capability palette (D-01). Renders EVERY capability kind from the
 * live `GET /api/capabilities` registry payload, grouped by `kind`, reusing the
 * AgentModelPicker fetch/loading/error/empty shell (D-02). Each row is driven
 * entirely by the fetched payload — name, registry-authored description, the
 * trust state, the security-gated flag, and an expandable config-schema
 * affordance (only when `config_schema` is non-empty). `user_allowed=false` caps
 * render visible-but-LOCKED (EMP-02 / D-04): Lock icon, engineer-only microcopy,
 * `aria-disabled="true"`, non-selectable.
 *
 * Exported so it can be render-tested in isolation; it remains EMBEDDED in the
 * AgentsPopup composer (NOT a standalone CapabilityPalette.tsx — Pitfall 1).
 *
 * SURF-03: `declaredCapabilities` (optional) carries the opened launchable
 * workflow's compiled per-step capability projection so the composer shows what
 * the workflow already declares before the user composes — driven by the
 * projection, never a hardcoded description.
 */
export function CapabilityPaletteSection({
  token,
  declaredCapabilities,
}: {
  /** Optional JWT override (defaults to the stored token), mirroring the picker. */
  token?: string | null;
  /**
   * SURF-03 — the opened workflow's declared per-step capabilities (compiled
   * projection): `[{ step, capabilities: ["validator:code_test", ...] }]`.
   * Absent on compose-from-scratch; rendered as a read-only declared-caps strip.
   */
  declaredCapabilities?: { step: string; capabilities: string[] }[];
}) {
  const [capabilities, setCapabilities] = useState<CapabilityEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  useEffect(() => {
    let cancelled = false;
    const jwt = token ?? getToken();
    if (!jwt) {
      setError("Not authenticated.");
      setLoading(false);
      return;
    }
    setLoading(true);
    fetchCapabilities(jwt)
      .then((palette) => {
        if (cancelled) return;
        // Render the WHOLE registry payload — including user_allowed=false caps
        // (they render locked, never hidden; SURF-01 "every kind visible").
        setCapabilities(palette.capabilities);
        setError(null);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e?.message ?? "Failed to load capabilities.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  // Group rows by the payload `kind` — preserve first-seen order; NO hardcoded
  // kind list (SC-001). The group set is whatever the registry returns.
  const groups: { kind: string; rows: CapabilityEntry[] }[] = [];
  for (const cap of capabilities) {
    let g = groups.find((x) => x.kind === cap.kind);
    if (!g) {
      g = { kind: cap.kind, rows: [] };
      groups.push(g);
    }
    g.rows.push(cap);
  }

  const toggle = (key: string) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  return (
    <div className="flex flex-col">
      <div className="flex items-center gap-1.5 mb-2">
        <Sliders className="h-3.5 w-3.5 text-brand" />
        <p className="text-[10px] font-semibold text-ink-500 uppercase tracking-widest">
          Capabilities
        </p>
      </div>

      {/* SURF-03: declared per-step capabilities of the opened workflow (compiled
          projection) — read-only, shown before composing. */}
      {declaredCapabilities && declaredCapabilities.length > 0 && (
        <div className="mb-2 rounded-lg bg-brand/5 border border-brand/15 px-2.5 py-1.5">
          <p className="text-[9px] font-semibold text-brand uppercase tracking-widest mb-1">
            Declared by this workflow
          </p>
          <div className="space-y-0.5">
            {declaredCapabilities.map((d) => (
              <div key={d.step} className="flex items-start gap-1.5 text-[10px]">
                <span className="font-semibold text-ink-700 truncate max-w-[120px]">
                  {d.step}
                </span>
                <span className="text-ink-500 flex-1 min-w-0">
                  {d.capabilities.join(" · ")}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {loading && (
        <p className="text-[11px] text-ink-400 py-2">Loading capabilities…</p>
      )}

      {error && (
        <div className="flex items-center gap-1.5 text-[11px] text-status-failed bg-status-failed-fill rounded-lg px-2.5 py-1.5">
          <AlertCircle className="h-3 w-3 flex-shrink-0" />
          {error}
        </div>
      )}

      {!loading && !error && capabilities.length === 0 && (
        <div className="py-2">
          <p className="text-[11px] font-semibold text-ink-500">
            No capabilities available
          </p>
          <p className="text-[10px] text-ink-400">
            The capability registry returned nothing. Reload, or contact support
            if this persists.
          </p>
        </div>
      )}

      {!loading && !error && capabilities.length > 0 && (
        <div className="space-y-3 max-h-[200px] overflow-y-auto pr-1">
          {groups.map((group) => (
            <div key={group.kind} role="group" aria-label={titleCaseKind(group.kind)}>
              <p className="text-[10px] font-semibold text-ink-500 uppercase tracking-widest mb-1">
                {titleCaseKind(group.kind)}
              </p>
              <div className="space-y-1.5">
                {group.rows.map((cap) => {
                  const rowKey = `${cap.kind}:${cap.name}`;
                  // Locks are binary `user_allowed` (engineer-only). Minor #6's
                  // "Upgrade to use" tier-locked copy variant (UI-SPEC copywriting
                  // contract) is deliberately NOT implemented: there is no
                  // tier-gated capability yet — every lock is engineer-only. This
                  // is the forward hook to wire that variant when a tier-gated
                  // capability first appears (branch here on a future tier field).
                  const locked = !cap.user_allowed;
                  const hasSchema =
                    cap.config_schema &&
                    Object.keys(cap.config_schema).length > 0;
                  const isOpen = expanded.has(rowKey);
                  return (
                    <div
                      key={rowKey}
                      data-cap-row
                      aria-disabled={locked ? "true" : undefined}
                      // A11y (Top Fix #2): the lock reason must reach keyboard/SR
                      // users on this non-focusable div. Additive — only locked
                      // rows get an aria-label; non-locked rows stay labelled by
                      // their visible name. The visible pill + title tooltip are
                      // preserved alongside.
                      aria-label={
                        locked
                          ? `${cap.name} — Engineer-only, not available to compose`
                          : undefined
                      }
                      title={
                        locked
                          ? "This capability requires elevated trust and isn't available to compose. Contact your workspace admin."
                          : undefined
                      }
                      className={`rounded-lg border px-2.5 py-1.5 ${
                        locked
                          ? "bg-surface-warm border-line-divider opacity-80 cursor-not-allowed"
                          : "bg-surface-warm border-line-divider"
                      }`}
                    >
                      <div className="flex items-center gap-2">
                        {locked && (
                          <Lock className="h-3 w-3 text-ink-400 flex-shrink-0" />
                        )}
                        <p
                          className={`text-[11px] font-semibold truncate flex-1 min-w-0 ${
                            locked ? "text-ink-400" : "text-ink-800"
                          }`}
                        >
                          {cap.name}
                        </p>
                        {locked && (
                          <span className="text-[10px] text-ink-400 flex-shrink-0">
                            Engineer-only
                          </span>
                        )}
                        {cap.security_gated && !locked && (
                          <Lock className="h-3 w-3 text-ink-400 flex-shrink-0" />
                        )}
                        {hasSchema && (
                          <button
                            type="button"
                            onClick={() => toggle(rowKey)}
                            aria-expanded={isOpen}
                            aria-label={`Configuration for ${cap.name}`}
                            className="flex items-center justify-center h-5 w-5 rounded text-ink-400 hover:text-brand flex-shrink-0"
                          >
                            <Settings2 className="h-3 w-3" />
                            {isOpen ? (
                              <ChevronDown className="h-2.5 w-2.5" />
                            ) : (
                              <ChevronRight className="h-2.5 w-2.5" />
                            )}
                          </button>
                        )}
                      </div>
                      {cap.description && (
                        <p
                          className={`text-[11px] ${
                            locked ? "text-ink-400" : "text-ink-500"
                          }`}
                        >
                          {cap.description}
                        </p>
                      )}
                      {hasSchema && isOpen && (
                        <div className="mt-1 rounded-md bg-surface-card border border-line-divider px-2 py-1 space-y-0.5">
                          {Object.entries(cap.config_schema).map(
                            ([field, desc]) => {
                              // `desc` is typed `unknown` (config_schema is
                              // Record<string, unknown>) — narrow defensively;
                              // never assume keys (Minor #5). JSON-Schema-lite
                              // per-field descriptor: { type?: string;
                              // required?: boolean }.
                              const isObj =
                                typeof desc === "object" && desc !== null;
                              const fieldType =
                                isObj && "type" in desc &&
                                typeof (desc as { type?: unknown }).type ===
                                  "string"
                                  ? (desc as { type: string }).type
                                  : undefined;
                              const isRequired =
                                isObj &&
                                "required" in desc &&
                                (desc as { required?: unknown }).required ===
                                  true;
                              return (
                                <p
                                  key={field}
                                  className="text-[10px] text-ink-500 font-mono"
                                >
                                  {field}
                                  {/* Required marker — neutral ink scale only,
                                      never brand/red (preserve locked-row
                                      neutrality). */}
                                  {isRequired && (
                                    <span className="text-ink-400">*</span>
                                  )}
                                  {fieldType && (
                                    <span className="ml-1 text-[9px] text-ink-400">
                                      {fieldType}
                                    </span>
                                  )}
                                </p>
                              );
                            },
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}


// ─── AdvancedExpander (EMP-01 / EMP-04, D-05/D-06/D-07) ───────────────────────

/**
 * The compact per-step selections map the composer authors — the EXACT shape
 * 22-04 persists in `manifest_json` and `_apply_selections` overlays onto the
 * file-compiled plan BY AGENT_ID (generic, name-free; SC-001). An unselected
 * lever omits its key (parity with the "Default" model semantics).
 */
export type StepSelection = {
  validators?: string[];
  gates?: string[];
  model?: string;
  retry?: number;
  // ── Fan-out levers (51-06 / FANOUT-01, D6/§4a) ────────────────────────────
  // The composer persists a per-step fan-out selection generically (by
  // agent_id — no workflow/agent name literal, SC-001). The kernel already
  // owns spawn/isolation/merge; these three optional keys are the ONLY thing
  // the composer adds. `_apply_selections` overlays them onto the compiled
  // plan and the empty-selections path stays byte-identical (INV-3). The
  // shared `applyLeverPatch` reducer needs NO change — toggling ON writes
  // {strategy, task_source}, OFF clears them (undefined → key deleted).
  strategy?: "fanout_batch";
  task_source?: {
    kind: "parsed";
    parser: "heading_tasks" | "json_tasks";
    source_step: string;
  };
  fanout?: { mode?: "parallel"; max_parallel?: number };
  /** Per-step tool grants. Absent = the composer's defaults (read+write ON).
   *  Only `read_files`/`write_files` are author-editable: the untrusted cap
   *  (`permission_caps.PERMISSION_CAP_INDEX["untrusted"]`) forbids everything
   *  else for db-trust manifests, so offering them would grant nothing. */
  tools?: AgentToolGrants;
};
export type SelectionsMap = Record<string, StepSelection>;

/**
 * v1 known `## Task N:` producer allow-list (D7/§4e). A fan-out worker may
 * REUSE an upstream node as its `source_step` ONLY when that node is a known
 * task-list producer; otherwise the user is steered to INSERT a dedicated
 * producer (D2 — fan-out is a change to the workflow SHAPE, never a job bolted
 * onto a chained agent). `prototype-plan` is the shipped domain producer;
 * `task-list-planner` is the generic producer skill shipped in 51-03. Grows as
 * more producer skills ship. Keyed by agent id (name-free, SC-001).
 */
export const KNOWN_PRODUCERS: readonly string[] = ["prototype-plan", "task-list-planner"];

/**
 * EMP-04 (D-07) coupling — MIRRORS the server-side rule in
 * `backend/agents/workflows/selections.py`: a step that selects ≥1 validator
 * REQUIRES the `validation` gate (the registered seam that actually runs a
 * step's declared validators). The composer auto-attaches it here so the user
 * sees the coupling inline; the compiler's §13 coupling check stays the
 * authoritative server backstop (it RAISES on a missing gate — never
 * auto-injects, RESEARCH anti-pattern).
 */
const COUPLED_GATE = "validation";
const COUPLED_GATE_LABEL = "validation";

/** The retry lever options (max_attempts). 0/unset ⇒ no retry override. */
const RETRY_OPTIONS = [1, 2, 3];

/**
 * PURE lever-patch reducer — the SINGLE writer of the per-step selection shape,
 * extracted verbatim from `AdvancedExpander.updateLever` so any surface (the
 * modal expander AND the Canvas inline config rail) applies IDENTICAL selection
 * semantics (INV-3 — no forked lever logic). Applies `patch`, clears any unset
 * key (empty/undefined/`""`/`[]` → the "Default" parity), and auto-attaches the
 * coupled `validation` gate whenever validators are present (EMP-04 / D-07 — so
 * the validators actually fire at run time, mirroring selections.py). BEHAVIOR-
 * PRESERVING extraction: `updateLever` now delegates to this helper.
 */
export function applyLeverPatch(
  current: StepSelection | undefined,
  patch: Partial<StepSelection>,
): StepSelection {
  const cur: StepSelection = { ...(current ?? {}) };
  for (const [k, v] of Object.entries(patch)) {
    const key = k as keyof StepSelection;
    if (v === undefined || v === "" || (Array.isArray(v) && v.length === 0)) {
      delete cur[key];
    } else {
      // @ts-expect-error — keyed assignment across the union is safe here.
      cur[key] = v;
    }
  }
  // EMP-04 (D-07): a validator selection requires the `validation` gate. Auto-
  // attach it (deduped) so the validators actually fire at run time.
  if (cur.validators && cur.validators.length > 0) {
    const gates = new Set(cur.gates ?? []);
    gates.add(COUPLED_GATE);
    cur.gates = Array.from(gates);
  }
  return cur;
}

/**
 * The author-editable per-step tool grants, in render order — the SINGLE
 * definition every lever surface renders (the Canvas rail's Tools tab and the
 * expander below), so the two views can never disagree about which grants
 * exist or what "default" means (ISS-274). `exec`/`spawn_subagents` are
 * deliberately absent: the untrusted cap zeroes them for db-trust manifests,
 * so a toggle would grant nothing.
 */
export const TOOL_GRANT_LEVERS = [
  {
    key: "read_files",
    label: "Read files",
    desc: "List and read files in the run sandbox.",
  },
  {
    key: "write_files",
    label: "Write files",
    desc: "Create and edit files in the run sandbox. Off means this step produces no artifact for later steps to read.",
  },
] as const;

/**
 * The grants in effect for a step. Absent selection = the composer's defaults
 * (read + write ON), which is what `agentToManifestStep` also emits, so an
 * untouched step's saved manifest is unchanged by these controls existing.
 */
export function effectiveToolGrants(
  sel: StepSelection | undefined,
): Record<(typeof TOOL_GRANT_LEVERS)[number]["key"], boolean> {
  return {
    read_files: sel?.tools?.read_files ?? true,
    write_files: sel?.tools?.write_files ?? true,
  };
}

/** True when a step carries a RESTRICTED grant (one switched off) — what the
 *  Simple view's Overrides "Tools" chip reflects (ISS-274). */
export function hasToolOverride(sel: StepSelection | undefined): boolean {
  const grants = effectiveToolGrants(sel);
  return TOOL_GRANT_LEVERS.some(({ key }) => !grants[key]);
}

/**
 * Fetch + kind-filter the live `/api/capabilities` palette into the lever
 * OPTIONS: `user_allowed` validator/gate names + the whole `model_catalog`
 * (SC-001 — never a hardcoded option list). Extracted from `AdvancedExpander` so
 * the Canvas inline config rail sources the SAME options from the SAME endpoint
 * (INV-3). Returns the option arrays + the fetch loading/error state.
 */
export function useAgentCapabilities(token?: string | null) {
  const [validatorOptions, setValidatorOptions] = useState<string[]>([]);
  const [gateOptions, setGateOptions] = useState<string[]>([]);
  const [modelOptions, setModelOptions] = useState<CapabilityModelEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const jwt = token ?? getToken();
    if (!jwt) {
      setError("Not authenticated.");
      setLoading(false);
      return;
    }
    setLoading(true);
    fetchCapabilities(jwt)
      .then((palette) => {
        if (cancelled) return;
        // Lever OPTIONS come from the palette payload (kind-keyed), filtered to
        // user_allowed caps of the relevant kinds — NEVER a hardcoded list
        // (SC-001). A locked (user_allowed=false) cap is never an option.
        setValidatorOptions(
          palette.capabilities
            .filter((c) => c.kind === "validator" && c.user_allowed)
            .map((c) => c.name),
        );
        setGateOptions(
          palette.capabilities
            .filter((c) => c.kind === "gate" && c.user_allowed)
            .map((c) => c.name),
        );
        // DECIDE-02: the model lever offers the WHOLE catalog (all tiers).
        setModelOptions(palette.model_catalog);
        setError(null);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e?.message ?? "Failed to load capabilities.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  return { validatorOptions, gateOptions, modelOptions, loading, error };
}

/**
 * Per-agent "Advanced" expander (collapsed by default; D-05, agent ≈ step).
 * Exposes the representative lever-set — Validator → Gate → Model → Retry
 * (EMP-01) — sourced ENTIRELY from the live `/api/capabilities` palette payload
 * (user_allowed caps of the relevant kinds + the model catalog), never a
 * hardcoded option list (SC-001). Selecting a lever updates a per-step
 * selections map reported upward via `onSelectionsChange` (pure data — no new
 * run endpoint). Selecting a validator auto-attaches the `validation` gate
 * inline + announces it (EMP-04, `role="status"`).
 *
 * Exported so it can be render-tested in isolation; it remains EMBEDDED in the
 * AgentsPopup composer.
 */

// ─── Config lever sub-components ─────────────────────────────────────────────

/** Single config lever row — label + description on left, control on right. */
function ConfigLeverRow({
  label,
  description,
  children,
}: {
  label: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-4 rounded-[12px] border border-line-border bg-surface-card px-5 py-3.5 min-h-[64px]">
      <div className="min-w-0 flex-1">
        <p className="text-[13px] font-semibold text-ink-900 leading-tight">{label}</p>
        <p className="text-[11px] text-ink-400 mt-0.5 leading-tight">{description}</p>
      </div>
      {children}
    </div>
  );
}

/**
 * Styled config lever dropdown. Uses onPointerDown on options so the selection
 * fires BEFORE the document mousedown dismiss handler, solving the race.
 * Must be defined at module level (never inside a render function).
 */
function ConfigLeverSelect({
  leverId,
  openLever,
  setOpenLever,
  ariaLabel,
  value,
  options,
  onChange,
}: {
  leverId: string;
  openLever: string | null;
  setOpenLever: (id: string | null) => void;
  ariaLabel: string;
  value: string;
  options: { value: string; label: string }[];
  onChange: (v: string) => void;
}) {
  const isOpen = openLever === leverId;
  const displayLabel = options.find((o) => o.value === value)?.label ?? "Default";

  return (
    <div className="relative flex-shrink-0 w-[140px]">
      {/* Trigger */}
      <button
        type="button"
        aria-label={ariaLabel}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        onPointerDown={(e) => {
          e.preventDefault(); // stop document mousedown dismiss
          setOpenLever(isOpen ? null : leverId);
        }}
        className={`w-full flex items-center justify-between gap-1.5 rounded-[10px] border px-3 py-2 text-[13px] font-medium font-sans leading-none transition-colors ${
          isOpen
            ? "bg-surface-paper border-brand text-ink-900"
            : "bg-surface-warm border-line-border text-ink-700 hover:border-brand/50"
        }`}
      >
        <span className="truncate">{displayLabel}</span>
        <ChevronDown className={`h-3.5 w-3.5 flex-shrink-0 text-ink-400 transition-transform ${isOpen ? "rotate-180" : ""}`} />
      </button>

      {/* Styled option list */}
      {isOpen && (
        <div
          role="listbox"
          aria-label={ariaLabel}
          className="absolute right-0 top-[calc(100%+4px)] z-[300] w-[200px] rounded-[12px] border border-line-border bg-surface-paper py-1.5 shadow-[0_8px_32px_rgba(17,17,20,0.14)]"
        >
          {[{ value: "", label: "Default" }, ...options].map((opt) => {
            const isSelected = opt.value === value;
            return (
              <button
                key={opt.value}
                type="button"
                role="option"
                aria-selected={isSelected}
                onPointerDown={(e) => {
                  e.preventDefault(); // prevent document mousedown dismiss
                  onChange(opt.value);
                  setOpenLever(null);
                }}
                className={`w-full flex items-center justify-between gap-2 px-4 py-2.5 text-left font-sans text-[13px] transition-colors ${
                  isSelected
                    ? "bg-brand/5 text-brand font-semibold"
                    : "text-ink-800 hover:bg-surface-warm"
                }`}
              >
                <span className="truncate">{opt.label}</span>
                {isSelected && <Check className="h-3.5 w-3.5 flex-shrink-0 text-brand" />}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ─── ConfigLeversFlat ─────────────────────────────────────────────────────────
function ConfigLeversFlat({
  agentId,
  agentName,
  token,
  selections: initialSelectionsProp,
  onSelectionsChange,
}: {
  agentId: string;
  agentName: string;
  token?: string | null;
  selections: SelectionsMap;
  onSelectionsChange: (s: SelectionsMap) => void;
}) {
  const { validatorOptions, gateOptions, modelOptions, loading, error } =
    useAgentCapabilities(token);
  const [openLever, setOpenLever] = useState<string | null>(null);
  const [localSel, setLocalSel] = useState<SelectionsMap>(initialSelectionsProp);

  const sel = localSel[agentId] ?? {};

  const updateLever = (patch: Partial<StepSelection>) => {
    const cur = applyLeverPatch(sel, patch);
    const next: SelectionsMap = { ...localSel };
    if (Object.keys(cur).length === 0) delete next[agentId];
    else next[agentId] = cur;
    setLocalSel(next);
    onSelectionsChange(next);
  };

  // Dismiss on outside click — fires AFTER onPointerDown so selections go through first
  useEffect(() => {
    if (!openLever) return;
    const handler = () => setOpenLever(null);
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [openLever]);

  if (error) {
    return (
      <div className="flex items-center gap-1.5 text-[12px] text-red-600 bg-red-50 rounded-lg px-3 py-2">
        <AlertCircle className="h-3.5 w-3.5 flex-shrink-0" />{error}
      </div>
    );
  }
  // Note: we do NOT early-return on `loading` — doing so causes a height
  // change on every resetKey remount (loading→loaded) which makes the buttons
  // below flash. Rendering rows with empty options while loading is visually
  // identical ("Default" in every select) and avoids the layout shift.

  const selectedValidator = sel.validators?.[0] ?? "";
  // Phased, not one-of-N — see CanvasConfigRail's note. Pre-step gates
  // (security/approval/human) run BEFORE the agent generates, post-step
  // (validation/conditional) after, so a step can carry one of each. The single
  // select here had the same destructive rebuild: picking a gate replaced the
  // whole array and dropped the other phase's gate.
  const POST_STEP_GATES = ["validation", "conditional", "human"];
  const isPostGate = (g: string) => POST_STEP_GATES.includes(g);
  const HITL_GATES = ["before-human", "human", "approval"];
  const GATE_LABELS: Record<string, string> = {
    "before-human": "Human gate",
    human: "Human gate",
    approval: "Approval gate",
    security: "Security gate",
    conditional: "Conditional gate",
  };
  const declaredGates = sel.gates ?? [];
  const selectableGates = gateOptions.filter((g) => g !== COUPLED_GATE);
  const preGateChoices = selectableGates.filter((g) => !isPostGate(g));
  const postGateChoices = selectableGates.filter((g) => isPostGate(g));
  const toggleGate = (name: string, on: boolean) => {
    const keepCoupled = (sel.validators?.length ?? 0) > 0 ? [COUPLED_GATE] : [];
    let next = declaredGates.filter((g) => g !== name && g !== COUPLED_GATE);
    if (on) {
      if (HITL_GATES.includes(name)) next = next.filter((g) => !HITL_GATES.includes(g));
      next = [...next, name];
    }
    updateLever({ gates: [...keepCoupled, ...next] });
  };
  const selectedRetry = sel.retry !== undefined ? String(sel.retry) : "";

  return (
    <div className="space-y-2">
      <ConfigLeverRow label="Model" description="Reasoning model for this agent">
        <ConfigLeverSelect
          leverId="model" openLever={openLever} setOpenLever={setOpenLever}
          ariaLabel={`Model for ${agentName}`}
          value={sel.model ?? ""}
          options={modelOptions.map((m) => ({ value: m.id, label: m.label }))}
          onChange={(v) => updateLever({ model: v })}
        />
      </ConfigLeverRow>

      <ConfigLeverRow label="Validator" description="Output validation pass">
        <ConfigLeverSelect
          leverId="validator" openLever={openLever} setOpenLever={setOpenLever}
          ariaLabel={`Validator for ${agentName}`}
          value={selectedValidator}
          options={validatorOptions.map((n) => ({ value: n, label: n }))}
          onChange={(v) => updateLever({ validators: v ? [v] : [] })}
        />
      </ConfigLeverRow>

      {/* `gates:` is a LIST — checkboxes, grouped by the phase the engine evaluates
          them in. One human-review gate per step (shared durable gate_key). */}
      {[
        { key: "pre", title: "Before execute", names: preGateChoices },
        { key: "post", title: "After execute", names: postGateChoices },
      ].map((group) =>
        group.names.length === 0 ? null : (
          <div key={group.key} className="py-1">
            <p className="mb-0.5 text-[10px] font-semibold uppercase tracking-[0.1em] text-ink-400">
              {group.title}
            </p>
            {group.names.map((name) => {
              const checked = declaredGates.includes(name);
              const blocked =
                !checked &&
                HITL_GATES.includes(name) &&
                declaredGates.some((g) => HITL_GATES.includes(g));
              return (
                <label
                  key={name}
                  title={blocked ? "Only one human-review gate per step" : undefined}
                  className={`flex items-center gap-2 py-0.5 text-[12px] ${blocked ? "opacity-40" : "cursor-pointer"}`}
                >
                  <input
                    type="checkbox"
                    aria-label={`${group.title}: ${GATE_LABELS[name] ?? name} for ${agentName}`}
                    checked={checked}
                    disabled={blocked}
                    onChange={(e) => toggleGate(name, e.target.checked)}
                    className="h-3.5 w-3.5 accent-brand"
                  />
                  <span className="text-ink-700">{GATE_LABELS[name] ?? name}</span>
                </label>
              );
            })}
          </div>
        ),
      )}

      <ConfigLeverRow label="Retry" description="Auto-retry on failure">
        <ConfigLeverSelect
          leverId="retry" openLever={openLever} setOpenLever={setOpenLever}
          ariaLabel={`Retry for ${agentName}`}
          value={selectedRetry}
          options={RETRY_OPTIONS.map((n) => ({ value: String(n), label: `${n} ${n === 1 ? "attempt" : "attempts"}` }))}
          onChange={(v) => updateLever({ retry: v ? Number(v) : undefined })}
        />
      </ConfigLeverRow>
    </div>
  );
}

export function AdvancedExpander({
  agents,
  onSelectionsChange,
  token,
  initialSelections,
  priorAgents,
}: {
  agents: { id: string; name: string }[];
  /** Reports the compact per-step selections map upward (the 22-04 shape). */
  onSelectionsChange?: (selections: SelectionsMap) => void;
  /** Optional JWT override (defaults to the stored token), mirroring the picker. */
  token?: string | null;
  /** WR-01 — seed the per-step selections when launching a saved workflow. */
  initialSelections?: SelectionsMap;
  /**
   * 51-06 (D7/§4e) — the pipeline agents that precede THIS expander's block, so
   * the fan-out "Source list from" picker can offer earlier steps even when the
   * expander renders a single agent (the per-agent config surface passes one
   * agent). Combined with `agents.slice(0, idx)` for the intra-block order. When
   * omitted (or empty for the first agent) the fan-out toggle is disabled.
   */
  priorAgents?: { id: string; name: string }[];
}) {
  // Lever OPTIONS + fetch state come from the SHARED hook (SC-001) — the same
  // source the Canvas inline config rail uses (INV-3, no forked fetch/filter).
  const { validatorOptions, gateOptions, modelOptions, loading, error } =
    useAgentCapabilities(token);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [selections, setSelections] = useState<SelectionsMap>(initialSelections ?? {});

  const toggle = (agentId: string) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(agentId)) next.delete(agentId);
      else next.add(agentId);
      return next;
    });

  // Apply a lever change → rebuild the selection for one agent, omitting any
  // unset key (parity with "Default"), and report the whole map upward.
  const updateLever = (
    agentId: string,
    patch: Partial<StepSelection>,
  ) => {
    // Delegate to the shared pure reducer (patch + clear-unset + validator→gate
    // coupling) — the single writer of the selection shape (INV-3). A lever toggle
    // is a single discrete click event, so the current-render `selections` closure
    // is already the latest committed value (no functional-updater `prev` needed).
    const cur = applyLeverPatch(selections[agentId], patch);
    const next: SelectionsMap = { ...selections };
    if (Object.keys(cur).length === 0) delete next[agentId];
    else next[agentId] = cur;
    setSelections(next);
    // Notify the parent OUTSIDE the setState updater — the parent notify no longer
    // fires during this child's render pass (setState-in-render cleanup).
    onSelectionsChange?.(next);
  };

  if (loading) {
    return (
      <div className="flex flex-col">
        <p className="text-[11px] text-ink-300 py-2">Loading levers…</p>
      </div>
    );
  }
  if (error) {
    return (
      <div className="flex items-center gap-1.5 text-[11px] text-status-failed bg-status-failed-fill rounded-lg px-2.5 py-1.5">
        <AlertCircle className="h-3 w-3 flex-shrink-0" />
        {error}
      </div>
    );
  }
  if (agents.length === 0) {
    return (
      <p className="text-[11px] text-ink-300 py-2">
        Add agents to assign per-agent levers.
      </p>
    );
  }

  return (
    <div className="flex flex-col space-y-1.5 max-h-[200px] overflow-y-auto pr-1">
      {agents.map((agent, idx) => {
        const isOpen = expanded.has(agent.id);
        const region = `advanced-${agent.id}`;
        const sel = selections[agent.id] ?? {};
        const grants = effectiveToolGrants(sel);
        const autoAttached =
          (sel.validators?.length ?? 0) > 0 &&
          (sel.gates ?? []).includes(COUPLED_GATE);
        return (
          <div key={agent.id} className="flex flex-col">
            <button
              type="button"
              onClick={() => toggle(agent.id)}
              aria-expanded={isOpen}
              aria-controls={region}
              className="flex items-center gap-1.5 text-left text-[11px] font-semibold text-ink-700 hover:text-brand py-1"
            >
              {isOpen ? (
                <ChevronDown className="h-3 w-3 flex-shrink-0" />
              ) : (
                <ChevronRight className="h-3 w-3 flex-shrink-0" />
              )}
              <Settings2 className="h-3 w-3 flex-shrink-0 text-brand" />
              <span className="truncate flex-1 min-w-0">
                Advanced — {agent.name}
              </span>
              <span className="text-[9px] text-ink-300 flex-shrink-0">
                Validator · Gate · Model · Retry
              </span>
            </button>

            {/* Tool grants (ISS-274) — the SAME `tools` field the Canvas rail's
                Tools tab writes, through the SAME `applyLeverPatch` reducer and
                the SAME shared lever list, so a grant restricted in one view is
                visible and editable in the other. Rendered OUTSIDE the collapsed
                disclosure: an existing restriction has to be visible when the
                config panel opens, not one more click away. */}
            <div className="space-y-1 pl-4 pt-0.5">
              <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-ink-400">
                Tool grants
              </p>
              {TOOL_GRANT_LEVERS.map(({ key, label, desc }) => (
                <div
                  key={key}
                  title={desc}
                  className="flex items-center gap-2 bg-surface-warm border border-line-faint-row rounded-lg px-2.5 py-1.5"
                >
                  <label
                    htmlFor={`${region}-${key}`}
                    className="text-[11px] font-semibold text-ink-700 flex-1 min-w-0"
                  >
                    {label}
                  </label>
                  <input
                    type="checkbox"
                    id={`${region}-${key}`}
                    aria-label={`${label} for ${agent.name}`}
                    checked={grants[key]}
                    onChange={(e) =>
                      updateLever(agent.id, {
                        tools: { ...grants, [key]: e.target.checked },
                      })
                    }
                    className="h-3.5 w-3.5 accent-brand"
                  />
                </div>
              ))}
              {/* exec stays fixed OFF — the untrusted cap zeroes it for
                  db-trust manifests, so the switch would grant nothing (same
                  disabled row the Canvas rail shows). */}
              <div
                title="Not available to custom workflows."
                className="flex items-center gap-2 bg-surface-warm border border-line-faint-row rounded-lg px-2.5 py-1.5"
              >
                <label
                  htmlFor={`${region}-exec`}
                  className="text-[11px] font-semibold text-ink-300 flex-1 min-w-0"
                >
                  Execute commands
                </label>
                <input
                  type="checkbox"
                  id={`${region}-exec`}
                  aria-label={`Execute commands for ${agent.name}`}
                  checked={false}
                  disabled
                  readOnly
                  className="h-3.5 w-3.5 accent-brand disabled:cursor-not-allowed disabled:opacity-40"
                />
              </div>
            </div>

            {isOpen && (
              <div id={region} className="space-y-1.5 pl-4">
                {/* Validator lever (EMP-01) */}
                <div className="flex items-center gap-2 bg-surface-warm border border-line-faint-row rounded-lg px-2.5 py-1.5">
                  <label
                    htmlFor={`${region}-validator`}
                    className="text-[11px] font-semibold text-ink-700 flex-1 min-w-0"
                  >
                    Validator
                  </label>
                  <select
                    id={`${region}-validator`}
                    aria-label={`Validator for ${agent.name}`}
                    value={sel.validators?.[0] ?? ""}
                    onChange={(e) =>
                      updateLever(agent.id, {
                        validators: e.target.value ? [e.target.value] : [],
                      })
                    }
                    className="text-[10px] text-ink-700 bg-surface-white border border-line-control rounded-md px-1.5 py-1 focus:outline-none focus:border-brand max-w-[140px]"
                  >
                    <option value="">Default</option>
                    {validatorOptions.map((name) => (
                      <option key={name} value={name}>
                        {name}
                      </option>
                    ))}
                  </select>
                </div>

                {/* Gate lever (EMP-01) */}
                <div className="flex items-center gap-2 bg-surface-warm border border-line-faint-row rounded-lg px-2.5 py-1.5">
                  <label
                    htmlFor={`${region}-gate`}
                    className="text-[11px] font-semibold text-ink-700 flex-1 min-w-0"
                  >
                    Gate
                  </label>
                  <select
                    id={`${region}-gate`}
                    aria-label={`Gate for ${agent.name}`}
                    value={
                      // Show the user-picked gate (the one that is NOT the
                      // auto-attached coupling gate) as the select value.
                      (sel.gates ?? []).find((g) => g !== COUPLED_GATE) ?? ""
                    }
                    onChange={(e) => {
                      const picked = e.target.value;
                      const keepCoupled =
                        (sel.validators?.length ?? 0) > 0 ? [COUPLED_GATE] : [];
                      const gates = picked
                        ? [...keepCoupled, picked]
                        : keepCoupled;
                      updateLever(agent.id, { gates });
                    }}
                    className="text-[10px] text-ink-700 bg-surface-white border border-line-control rounded-md px-1.5 py-1 focus:outline-none focus:border-brand max-w-[140px]"
                  >
                    <option value="">Default</option>
                    {gateOptions.map((name) => (
                      <option key={name} value={name}>
                        {name}
                      </option>
                    ))}
                  </select>
                </div>

                {/* Model lever (EMP-01 / DECIDE-02) */}
                <div className="flex flex-col gap-1.5 bg-surface-warm border border-line-faint-row rounded-lg px-2.5 py-1.5">
                  <div className="flex items-center gap-2">
                    <label
                      htmlFor={`${region}-model`}
                      className="text-[11px] font-semibold text-ink-700 flex-1 min-w-0"
                    >
                      Model
                    </label>
                    <select
                      id={`${region}-model`}
                      aria-label={`Model for ${agent.name}`}
                      value={sel.model ?? ""}
                      onChange={(e) =>
                        updateLever(agent.id, { model: e.target.value })
                      }
                      className="text-[10px] text-ink-700 bg-surface-white border border-line-control rounded-md px-1.5 py-1 focus:outline-none focus:border-brand min-w-[160px] max-w-[200px]"
                    >
                      <option value="">Default</option>
                      {modelOptions.map((m) => (
                        <option key={m.id} value={m.id}>
                          {m.label} ({m.tier})
                        </option>
                      ))}
                    </select>
                  </div>
                  {/* Rich model info — shown for the selected model */}
                  {(() => {
                    const picked = sel.model ? modelOptions.find(m => m.id === sel.model) : null;
                    if (!picked) return null;
                    const ctxK = picked.context_window >= 1_000_000
                      ? `${(picked.context_window / 1_000_000).toFixed(0)}M`
                      : `${Math.round(picked.context_window / 1000)}K`;
                    const tierColor: Record<string, string> = {
                      fast: "bg-brand-fill text-brand border-brand-border",
                      balanced: "bg-brand-fill text-brand border-brand-border",
                      powerful: "bg-brand-fill text-brand border-brand-border",
                    };
                    return (
                      <div className="flex items-start gap-1.5 pt-0.5">
                        <span className={`text-[9px] font-semibold px-1.5 py-0.5 rounded border flex-shrink-0 uppercase tracking-wide ${tierColor[picked.tier] ?? "bg-surface-warm text-ink-500 border-line-control"}`}>
                          {picked.tier}
                        </span>
                        <span className="text-[9px] text-ink-300 flex-shrink-0">
                          {ctxK} ctx
                        </span>
                        <span className="text-[9px] text-ink-400 leading-tight line-clamp-2 min-w-0">
                          {picked.description}
                        </span>
                      </div>
                    );
                  })()}
                </div>

                {/* Retry lever (EMP-01) */}
                <div className="flex items-center gap-2 bg-surface-warm border border-line-faint-row rounded-lg px-2.5 py-1.5">
                  <label
                    htmlFor={`${region}-retry`}
                    className="text-[11px] font-semibold text-ink-700 flex-1 min-w-0"
                  >
                    Retry
                  </label>
                  <select
                    id={`${region}-retry`}
                    aria-label={`Retry for ${agent.name}`}
                    value={sel.retry ?? ""}
                    onChange={(e) =>
                      updateLever(agent.id, {
                        retry: e.target.value
                          ? Number(e.target.value)
                          : undefined,
                      })
                    }
                    className="text-[10px] text-ink-700 bg-surface-white border border-line-control rounded-md px-1.5 py-1 focus:outline-none focus:border-brand max-w-[140px]"
                  >
                    <option value="">Default</option>
                    {RETRY_OPTIONS.map((n) => (
                      <option key={n} value={n}>
                        {n} {n === 1 ? "attempt" : "attempts"}
                      </option>
                    ))}
                  </select>
                </div>

                {/* Fan-out lever (51-06 / FANOUT-01, D6/§4c) — "Fan out over a
                    list": one worker per `## Task N:` heading the source step
                    emits. The kernel owns spawn/isolation/merge; the composer
                    only persists {strategy, task_source} via the SHARED reducer
                    (no reducer change). GUARDRAILS (D9/§5b): the source picker
                    lists ONLY earlier agents; the toggle is disabled for a step
                    with no upstream; a non-blocking warning steers the user to a
                    known `## Task N:` producer (INSERT-A-NODE, D2/D7). */}
                {(() => {
                  // Earlier steps = the pipeline agents before THIS block
                  // (priorAgents, from the per-agent config surface) followed by
                  // any earlier agents WITHIN this expander's block (multi-agent
                  // render). Either alone is empty in the two live mounts, so the
                  // union is what makes "earlier agents only" real.
                  const earlier = [
                    ...(priorAgents ?? []),
                    ...agents.slice(0, idx),
                  ];
                  const canFanout = earlier.length > 0;
                  const fanoutOn = sel.strategy === "fanout_batch";
                  const currentSource = sel.task_source?.source_step ?? "";
                  // Default source (D7): the nearest earlier KNOWN producer if
                  // one exists, else the immediately-preceding step (still valid
                  // — the unknown-producer warning then steers to INSERT one).
                  const defaultSource =
                    [...earlier].reverse().find((a) =>
                      KNOWN_PRODUCERS.includes(a.id),
                    )?.id ?? earlier[earlier.length - 1]?.id;
                  const sourceKnown =
                    !!currentSource && KNOWN_PRODUCERS.includes(currentSource);
                  return (
                    <div className="flex flex-col gap-1.5 bg-surface-warm border border-line-faint-row rounded-lg px-2.5 py-1.5">
                      <div className="flex items-center gap-2">
                        <label
                          htmlFor={`${region}-fanout`}
                          className="text-[11px] font-semibold text-ink-700 flex-1 min-w-0"
                        >
                          Fan out over a list
                        </label>
                        <input
                          type="checkbox"
                          id={`${region}-fanout`}
                          aria-label={`Fan out over a list for ${agent.name}`}
                          checked={fanoutOn}
                          disabled={!canFanout}
                          onChange={(e) => {
                            if (e.target.checked) {
                              updateLever(agent.id, {
                                strategy: "fanout_batch",
                                task_source: {
                                  kind: "parsed",
                                  parser: "heading_tasks",
                                  source_step: defaultSource ?? "",
                                },
                              });
                            } else {
                              updateLever(agent.id, {
                                strategy: undefined,
                                task_source: undefined,
                                fanout: undefined,
                              });
                            }
                          }}
                          className="h-3.5 w-3.5 accent-brand disabled:opacity-40 disabled:cursor-not-allowed"
                        />
                      </div>

                      {/* No upstream → the toggle can't source a list (D9). */}
                      {!canFanout && (
                        <p className="text-[10px] text-ink-300 leading-tight">
                          Add an earlier step that outputs a task list to fan out
                          over.
                        </p>
                      )}

                      {/* Source picker — earlier steps ONLY (D9/§5b). */}
                      {fanoutOn && canFanout && (
                        <>
                          <div className="flex items-center gap-2">
                            <label
                              htmlFor={`${region}-fanout-source`}
                              className="text-[11px] text-ink-500 flex-1 min-w-0"
                            >
                              Source list from
                            </label>
                            <select
                              id={`${region}-fanout-source`}
                              aria-label={`Source list for ${agent.name}`}
                              value={currentSource}
                              onChange={(e) =>
                                updateLever(agent.id, {
                                  task_source: {
                                    kind: "parsed",
                                    parser: "heading_tasks",
                                    source_step: e.target.value,
                                  },
                                })
                              }
                              className="text-[10px] text-ink-700 bg-surface-white border border-line-control rounded-md px-1.5 py-1 focus:outline-none focus:border-brand max-w-[140px]"
                            >
                              {earlier.map((a) => (
                                <option key={a.id} value={a.id}>
                                  {a.name}
                                </option>
                              ))}
                            </select>
                          </div>

                          {/* Non-blocking unknown-producer warning (D7/§4e) —
                              steer to INSERT a dedicated `## Task N:` producer;
                              the compile guard (51-02) is the server backstop. */}
                          {!sourceKnown && (
                            <p className="flex items-start gap-1.5 text-[10px] text-status-amber bg-status-amber-fill border border-status-amber-border rounded-md px-2 py-1 leading-tight">
                              <AlertCircle className="h-3 w-3 flex-shrink-0 mt-0.5" />
                              <span>
                                This step fans out one worker per{" "}
                                <code>## Task N:</code> heading its source
                                outputs — pick or insert a step that emits a task
                                list.
                              </span>
                            </p>
                          )}
                        </>
                      )}
                    </div>
                  );
                })()}

                {/* EMP-04 (D-07): auto-attach inline notice — a polite live
                    region so the gate-added message is announced. */}
                {autoAttached && (
                  <div
                    role="status"
                    className="flex items-center gap-1.5 text-[10px] text-brand bg-brand/5 border border-brand/15 rounded-md px-2 py-1"
                  >
                    <Info className="h-3 w-3 flex-shrink-0" />
                    Added required {COUPLED_GATE_LABEL} gate — this capability
                    needs it.
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ─── AgentsPopup (main) ───────────────────────────────────────────────────────

export function AgentsPopup({
  isOpen, onClose, onOpenInCanvas, debugLabel, agents, pipelineType,
  onAddAgent, onRemoveAgent, onReorder, canAddMore = true,
  allowCustomAgentTemplate = true,
  onSelectionsChange, initialSelections, selections: controlledSelections,
  declaredCapabilities,
  userWorkflowId, savedName, savedDescription,
  overrideAvailable, overrideActive, onToggleOverride, runConfig,
}: AgentsPopupProps) {
  const { attachedHooks } = useSkillsHooks();
  const workflows = useAppSelector((state) => state.global.workflows);
  const workflow = workflows.find((w) => w.id === pipelineType);
  const workflowName = workflow?.name || workflow?.display_name || pipelineType;

  const [libraryOpen, setLibraryOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<"agents" | "skills-hooks">("agents");
  // Bumped by the Save button — see CanvasView's resetLayoutSignal doc.
  const [canvasResetLayoutSignal, setCanvasResetLayoutSignal] = useState(0);
  // The Canvas's Brief node is purely a display affordance in this modal — the
  // real run instruction lives on IdeaInputPage outside this popup — so its
  // text is local-only, never read or persisted from here.
  const [canvasBriefText, setCanvasBriefText] = useState("");
  // Local-only, same reason as canvasBriefText above — decorative in this
  // modal, not read/persisted from here.
  const canvasBriefAttachments = useBriefAttachments();
  // Mirrors ComposerPage's CanvasView "+ Sub-agent" wiring (Spec 012/R-35):
  // set by onRequestAddSubAgent, consumed by addSubAgent, cleared whenever
  // the library closes without a pick.
  const [subAgentParentId, setSubAgentParentId] = useState<string | null>(null);
  // Where the canvas "+" that opened the library wants the new node to land.
  // CanvasView reports it; without holding it here the argument was dropped on
  // the floor and every add appended, so a mid-chain "+" (and the head one) put
  // the agent somewhere the user did not click.
  const [insertBeforeId, setInsertBeforeId] = useState<string | undefined>(undefined);

  // ── Save-to-catalogue (Phase 21 / ND-12) ──────────────────────────────────
  // The footer "Save workflow" persists the composed workflow to the OWNER-scoped
  // /api/user-workflows via the existing NameWorkflowModal (REUSE — no new
  // persistence; owner-only CRUD is the whole surface, ND-12 controls DECLARED
  // OUT). The live per-step selections edited in AgentCapabilitiesModal are
  // mirrored here so the save payload carries the composed `selections` map
  // (agentId -> {validators?, gates?, model?, retry?}), the EXACT 22-04 shape.
  const [saveModalOpen, setSaveModalOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [ownSelections, setOwnSelections] = useState<SelectionsMap>(() => {
    // Runs ONCE per mount — the whole reason IdeaInputPage keys this component on
    // whether the manifest has landed.
    console.log("[wf] 5. AgentsPopup mount", debugLabel, {
      seededSelections: initialSelections ?? {},
      agents: agents.map((a) => a.id),
    });
    return initialSelections ?? {};
  });
  // ISS-247: a caller that owns the map wins — the checklist outside this modal
  // and the Gate combobox inside it must read one store, not two.
  const liveSelections = controlledSelections ?? ownSelections;

  // ISS-258 / ISS-363 — "Cancel" has to DISCARD what was edited in this modal
  // session. Every edit inside it writes the HOST's state live: the canvas's
  // route/outcome editor, add, remove and reorder all round-trip through
  // `onTreeChange` -> `onReorder` -> the host's `pipelineAgents` (which is the
  // `agents` prop below), and the per-agent levers through
  // `onSelectionsChange`. Nothing ever snapshotted either, so Cancel only hid
  // the modal and a never-saved edit — e.g. a conditional gate's outcome
  // re-pointed at another workflow, and the divert node it adds — survived the
  // reopen. Snapshot the host's state and re-emit it on dismiss.
  //
  // Staged at the FIRST edit of the session, NOT on the `isOpen` edge: both
  // hosts keep re-deriving `pipelineAgents` asynchronously while the modal is
  // already up (`IdeaInputPage.tsx`'s roster effect re-runs when the manifest
  // fetch lands), so an open-edge snapshot of a workflow opened before its
  // roster arrived captured the still-EMPTY array and Cancel then wiped every
  // agent. Arming on the first edit can only ever capture the tree the user is
  // actually editing. No edit means no snapshot, so an untouched session
  // re-emits nothing at all.
  const openSnapshot = useRef<{ agents: AgentDef[]; selections: SelectionsMap } | null>(null);
  const stageEdit = useCallback(() => {
    if (!openSnapshot.current) openSnapshot.current = { agents, selections: liveSelections };
  }, [agents, liveSelections]);
  useEffect(() => {
    // A closed modal starts a fresh session — including after "Save workflow"
    // and "Open in full canvas", both of which keep what they were handed.
    if (!isOpen) openSnapshot.current = null;
  }, [isOpen]);

  const handleSelectionsChange = useCallback(
    (next: SelectionsMap) => {
      stageEdit();
      setOwnSelections(next);
      onSelectionsChange?.(next);
    },
    [stageEdit, onSelectionsChange],
  );

  /** Every in-modal write to the host's agent tree — the canvas route/outcome
   *  editor, rename, reorder, remove and "+ Sub-agent" all land here. */
  const handleTreeChange = useCallback(
    (next: AgentDef[]) => {
      stageEdit();
      onReorder?.(next);
    },
    [stageEdit, onReorder],
  );

  /** Dismiss without saving — the Cancel button, the header X and the backdrop.
   *  NOT the post-save close in `handleSaveWorkflow`, which keeps the edit. */
  const handleCancel = useCallback(() => {
    const snapshot = openSnapshot.current;
    if (snapshot) {
      onReorder?.(snapshot.agents);
      handleSelectionsChange(snapshot.selections);
    }
    // Last, not first: the restore above goes through `handleSelectionsChange`,
    // which would otherwise re-arm the snapshot with the edit being undone.
    openSnapshot.current = null;
    onClose();
  }, [onReorder, handleSelectionsChange, onClose]);

  const handleSaveWorkflow = useCallback(
    async (name: string, description: string) => {
      const token = getToken();
      if (!token) {
        setSaveError("Not authenticated.");
        return;
      }
      setSaving(true);
      setSaveError(null);
      setCanvasResetLayoutSignal((n) => n + 1);
      try {
        // ISS-167 (follow-up): saveUserWorkflow updates the reopened row in
        // place when userWorkflowId is known, instead of always minting a
        // new one — same dispatch LaunchWizard's page-level save uses.
        await saveUserWorkflow(token, userWorkflowId, {
          name,
          ...(description ? { description } : {}),
          base_pipeline_type: pipelineType,
          agent_ids: agents.map((a) => a.id),
          // WR-03: per-agent model lives in `selections[id].model` (the inline
          // Model lever) — the single source of truth the backend re-applies via
          // `_apply_selections`. No separate `model_overrides` key: emitting the
          // static seed alongside the live selections persisted a divergent
          // model on reload. Omit the empty map → payload byte-identical (INV-3).
          ...(Object.keys(liveSelections).length > 0
            ? { selections: liveSelections }
            : {}),
        });
        setSaveModalOpen(false);
        onClose();
      } catch (e) {
        setSaveError((e as Error)?.message ?? "Failed to save workflow.");
      } finally {
        setSaving(false);
      }
    },
    [agents, pipelineType, liveSelections, onClose, userWorkflowId],
  );

  const handleRemove = useCallback((agentId: string) => {
    if (getRole(agentId, pipelineType) !== "optional") return;
    stageEdit();
    onRemoveAgent?.(agentId);
  }, [onRemoveAgent, pipelineType, stageEdit]);

  // ComposerPage's addSubAgent (Spec 012/R-35), reused here so the embedded
  // canvas's "+ Sub-agent" opens the library to pick a real agent instead of
  // falling back to CanvasView's blank-node mint.
  const addSubAgent = useCallback(
    (agent: AgentDef) => {
      if (!subAgentParentId) return;
      const node = instantiateIfTemplate(agent, collectAgentIds(agents));
      handleTreeChange(addChildInTree(agents, subAgentParentId, node));
      setSubAgentParentId(null);
      setLibraryOpen(false);
    },
    [subAgentParentId, agents, handleTreeChange],
  );

  // CanvasView reports the whole selections map already keyed by agent —
  // ComposerPage's handleAgentSelection pattern, reused here.
  const handleCanvasSelection = useCallback(
    (agentId: string, sel: StepSelection | undefined) => {
      const next = { ...liveSelections };
      if (sel && Object.keys(sel).length > 0) next[agentId] = sel;
      else delete next[agentId];
      handleSelectionsChange(next);
    },
    [liveSelections, handleSelectionsChange],
  );

  const pipelineLabel = PIPELINE_LABEL[pipelineType] || pipelineType;
  const flatDeclaredCapabilities = useMemo(() => {
    const set = new Set<string>();
    (declaredCapabilities ?? []).forEach((d) => d.capabilities.forEach((c) => set.add(c)));
    return Array.from(set);
  }, [declaredCapabilities]);

  // ADR-0010: hooks only — run-level skill attachment is retired.
  const totalAttached = attachedHooks.length;

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 flex items-center justify-center py-3"
        >
          <motion.div className="absolute inset-0 bg-black/30 backdrop-blur-[2px]" onClick={handleCancel} />

          <motion.div
            initial={{ opacity: 0, y: 10, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 10, scale: 0.98 }}
            transition={{ duration: 0.18 }}
            className="relative w-[96vw] bg-surface-white rounded-2xl shadow-2xl flex flex-col"
            style={{ height: "95vh" }}
          >
            {/* Header — ONE line. The eyebrow ("Advanced"), the workflow name and a
                20px "Workflow configuration" heading each used to take their own row,
                spending ~90px of a 95vh modal on three restatements of where you are.
                Folded into a single title so that height goes to the canvas, which is
                the thing the modal exists to show. */}
            <div className="px-8 pt-4 pb-0 flex-shrink-0">
              <div className="flex items-center justify-between gap-4 mb-2">
                <h2 className="text-[14px] font-semibold text-ink-900 truncate">
                  Advanced Workflow Configuration
                  {workflowName ? (
                    <span className="font-normal text-ink-500"> — {workflowName}</span>
                  ) : null}
                </h2>
                <div className="flex items-center gap-1.5 flex-shrink-0">
                  {/* Spec 016 — swap between this user's saved override and the
                      system workflow. Only rendered when an override exists. */}
                  {overrideAvailable && onToggleOverride && (
                    <label
                      title={
                        overrideActive
                          ? "Showing your saved version. Untick to use the original."
                          : "Showing the original. Tick to use your saved version."
                      }
                      className="h-7 px-2.5 flex items-center gap-1.5 rounded-lg border border-line-border text-[11px] font-medium text-ink-600 hover:bg-surface-warm hover:text-ink-900 transition-all cursor-pointer select-none"
                    >
                      <input
                        type="checkbox"
                        checked={!!overrideActive}
                        onChange={(e) => onToggleOverride(e.target.checked)}
                        className="h-3 w-3 accent-brand cursor-pointer"
                      />
                      Use my version
                    </label>
                  )}
                  {onOpenInCanvas && (
                    <button
                      type="button"
                      onClick={onOpenInCanvas}
                      title="Open this workflow in the full-page canvas"
                      className="h-7 px-2.5 flex items-center gap-1.5 rounded-lg border border-line-border text-[11px] font-medium text-ink-600 hover:bg-surface-warm hover:text-ink-900 transition-all"
                    >
                      <Maximize2 className="h-3 w-3" />
                      Open in full canvas
                    </button>
                  )}
                  <button onClick={handleCancel} className="h-7 w-7 flex items-center justify-center rounded-lg text-ink-400 hover:text-ink-700 hover:bg-surface-warm transition-all">
                    <X className="h-4 w-4" />
                  </button>
                </div>
              </div>

              {/* Tabs */}
              <div className="flex items-center gap-1 pb-0 border-b border-line-divider">
                <button
                  onClick={() => setActiveTab("agents")}
                  className={`flex items-center gap-1.5 px-4 py-2.5 text-[12px] font-semibold transition-colors border-b-2 -mb-px ${
                    activeTab === "agents"
                      ? "border-ink-900 text-ink-900"
                      : "border-transparent text-ink-400 hover:text-ink-700"
                  }`}
                >
                  <GripVertical className="h-3.5 w-3.5" />
                  Agents
                  <span className="text-[10px] font-medium text-ink-400 ml-0.5">({agents.length})</span>
                </button>
                <button
                  onClick={() => setActiveTab("skills-hooks")}
                  className={`flex items-center gap-1.5 px-4 py-2.5 text-[12px] font-semibold transition-colors border-b-2 -mb-px ${
                    activeTab === "skills-hooks"
                      ? "border-ink-900 text-ink-900"
                      : "border-transparent text-ink-400 hover:text-ink-700"
                  }`}
                >
                  <Puzzle className="h-3.5 w-3.5" />
                  Workflow
                  {totalAttached > 0 && (
                    <span className="text-[9px] font-bold px-1.5 py-0.5 rounded-full bg-brand text-white ml-0.5">{totalAttached}</span>
                  )}
                </button>
              </div>
            </div>

            {/* Tab content */}
            {activeTab === "agents" ? (
              <>
                {/* Agents sub-header */}
                <div className="px-8 pt-3 pb-2 flex-shrink-0 flex items-center justify-between">
                  <div className="flex items-center gap-3 text-[10px] font-semibold text-ink-400 uppercase tracking-widest flex-wrap">
                    <span>{agents.length} agents · {pipelineLabel}</span>
                    <span className="flex items-center gap-1 text-ink-300"><Lock className="h-2.5 w-2.5" /> Core = locked</span>
                  </div>
                  <button onClick={() => { setSubAgentParentId(null); setLibraryOpen(true); }} className="text-[10px] font-semibold text-ink-400 hover:text-brand uppercase tracking-widest transition-colors flex-shrink-0 ml-4">
                    Browse agent library →
                  </button>
                </div>

                {/* Same node-graph editor as the Composer's Canvas view (D-04),
                    embedded here without its page-level header (name/description/
                    save/run — this modal's own header + footer already cover
                    those). flex-1 so it fills the rest of the now-fixed-height
                    modal instead of a fixed vh guess. */}
                <div className="mx-8 mb-6 min-h-0 flex-1 overflow-hidden rounded-xl border border-line-control">
                  <CanvasView
                    pipelineAgents={agents}
                    selections={liveSelections}
                    pipelineType={pipelineType}
                    onSelection={handleCanvasSelection}
                    onRemoveAgent={handleRemove}
                    onAddAgent={(beforeId) => {
                      setSubAgentParentId(null);
                      setInsertBeforeId(beforeId);
                      setLibraryOpen(true);
                    }}
                    canAddMore={canAddMore}
                    declaredCapabilities={flatDeclaredCapabilities}
                    onTreeChange={handleTreeChange}
                    onRequestAddSubAgent={(parentId) => { setSubAgentParentId(parentId); setLibraryOpen(true); }}
                    briefText={canvasBriefText}
                    onBriefTextChange={setCanvasBriefText}
                    resetLayoutSignal={canvasResetLayoutSignal}
                    briefAttachments={canvasBriefAttachments}
                    runConfig={runConfig}
                  />
                </div>
              </>
            ) : (
              /* Workflow tab: Skills, Hooks, and Capabilities */
              <div className="flex-1 overflow-y-auto min-h-0">
                <HooksTab pipelineType={pipelineType} />
                {/* Capabilities palette at the bottom of the Workflow tab */}
                <div className="mx-5 mb-5 px-1">
                  <CapabilityPaletteSection
                    declaredCapabilities={declaredCapabilities}
                  />
                </div>
              </div>
            )}

            {/* Footer */}
            <div className="px-8 pb-6 flex-shrink-0 flex items-center justify-end gap-3 border-t border-line-divider pt-4">
              {saveError && (
                <span role="alert" className="text-[11px] text-status-failed mr-auto">
                  {saveError}
                </span>
              )}
              <button onClick={handleCancel} className="px-5 py-2.5 rounded-xl border border-line-border text-[12px] font-medium text-ink-600 hover:bg-surface-warm transition-colors">
                Cancel
              </button>
              <button
                onClick={() => {
                  setSaveError(null);
                  // ISS-167 (follow-up): editing an already-saved workflow updates
                  // it in place under its existing name — only a brand-new save
                  // needs one asked.
                  if (userWorkflowId && savedName) {
                    handleSaveWorkflow(savedName, savedDescription ?? "");
                  } else {
                    setSaveModalOpen(true);
                  }
                }}
                className="px-5 py-2.5 rounded-xl bg-brand text-[12px] font-semibold text-surface-white hover:bg-brand-pressed transition-colors"
              >
                Save workflow
              </button>
            </div>
          </motion.div>

          {/* Save-to-catalogue modal (REUSE — owner-scoped saveUserWorkflow;
              ND-12 controls DECLARED OUT — owner-only CRUD is the whole surface). */}
          <AnimatePresence>
            {saveModalOpen && (
              <NameWorkflowModal
                title="Save workflow"
                onSave={handleSaveWorkflow}
                onCancel={() => { if (!saving) setSaveModalOpen(false); }}
              />
            )}
          </AnimatePresence>

          <AgentLibrary
            allowCustomAgentTemplate={allowCustomAgentTemplate}
            isOpen={libraryOpen}
            onClose={() => {
              setLibraryOpen(false);
              setSubAgentParentId(null);
              setInsertBeforeId(undefined);
            }}
            onAddAgent={
              onAddAgent
                ? (agent: AgentDef) => {
                    stageEdit();
                    onAddAgent(agent, insertBeforeId);
                    setInsertBeforeId(undefined);
                  }
                : undefined
            }
            onAddAsSubAgent={subAgentParentId ? addSubAgent : undefined}
            subAgentParentName={
              subAgentParentId ? findAgentInTree(agents, subAgentParentId)?.name : undefined
            }
            currentPipelineType={pipelineType}
            canAddMore={canAddMore}
            existingAgentIds={collectAgentIds(agents)}
          />
        </motion.div>
      )}
    </AnimatePresence>
  );
}
