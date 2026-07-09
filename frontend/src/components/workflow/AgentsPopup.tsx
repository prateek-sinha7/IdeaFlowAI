"use client";

import { useCallback, useEffect, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import {
  X, Plus, ArrowRight, Lock, GripVertical, Info,
  Clock, Zap, BookMarked, CheckCircle2, ChevronRight, ChevronDown,
  Puzzle, Webhook, Search, Check, Sliders, AlertCircle, Settings2, Cpu,
  FileText, Edit3, RotateCcw,
} from "lucide-react";
import { AgentLibrary } from "./AgentLibrary";
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
  createUserWorkflow,
  type CapabilityEntry,
  type CapabilityModelEntry,
  type AgentPromptData,
} from "@/lib/api";
import { NameWorkflowModal } from "@/components/catalog/NameWorkflowModal";
import type { AgentDef, WorkflowType, AttachedSkill, AttachedHook } from "@/types/index";
import { SKILLS, SKILL_CATEGORIES, type SkillDef } from "@/data/skills";
import { HOOKS, HOOK_EVENTS, type HookDef } from "@/data/hooks";
import { useSkillsHooks } from "@/context/SkillsHooksContext";

// ─── Props ────────────────────────────────────────────────────────────────────

interface AgentsPopupProps {
  isOpen: boolean;
  onClose: () => void;
  agents: AgentDef[];
  pipelineType: WorkflowType;
  onAddAgent?: (agent: AgentDef) => void;
  onRemoveAgent?: (agentId: string) => void;
  onReorder?: (agents: AgentDef[]) => void;
  canAddMore?: boolean;
  attachedSkills?: AttachedSkill[];
  attachedHooks?: AttachedHook[];
  onAttachSkill?: (skill: AttachedSkill) => void;
  onDetachSkill?: (skillId: string) => void;
  onAttachHook?: (hook: AttachedHook) => void;
  onDetachHook?: (hookId: string) => void;
  /**
   * ISS-014 (MODEL-03): per-agent model overrides selected in the relocated
   * AgentModelPicker (agentId -> modelId). Reported upward so IdeaInputPage can
   * thread it into the run_pipeline payload as `model_overrides`. Additive —
   * omit to ignore per-agent model selection (payload stays byte-identical).
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
   * WR-01 (LAUNCH-EXISTING-PATH §4.6) — seed the AgentModelPicker's internal
   * overrides map when launching a saved workflow, so editing one agent's model
   * MERGES into (not replaces) the persisted overrides for the others. Absent ⇒
   * the picker starts empty (the normal compose-from-scratch default).
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
  "od-ppt-brief-analyst", "od-ppt-composer", "od-ppt-validator",
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

function getRole(agentId: string, pipelineType: WorkflowType): AgentRole {
  const isNativeLocked = LOCKED_AGENT_IDS.has(agentId);
  const isNativeRequired = REQUIRED_AGENT_IDS.has(agentId);
  if (!isNativeLocked && !isNativeRequired) return "optional";
  const pipelinePrefixes: Record<string, string[]> = {
    user_stories: ["domain-analyst", "epic-architect", "story-estimator", "nfr-specialist", "backlog-reviewer", "backlog-compiler"],
    ppt: ["ppt-content-strategist", "ppt-slide-architect", "ppt-code-generator", "ppt-assembler",
          "od-ppt-brief-analyst", "od-ppt-composer", "od-ppt-validator"],
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

const PIPELINE_LABEL: Record<string, string> = {
  user_stories: "User Stories", ppt: "Presentation", prototype: "Prototype",
  app_builder: "App Builder", custom: "Custom",
  mulesoft_to_springboot: "Mulesoft → Spring Boot", dotnet_to_azure: ".NET → Azure",
};

const ICON_STYLES = [
  { bg: "var(--brand-fill)", text: "var(--brand)" }, { bg: "#F0EDE8", text: "#5C4A2A" },
  { bg: "#EAF0EA", text: "#2A5C2A" }, { bg: "#F0E8EE", text: "#5C2A4A" },
  { bg: "#E8EEF0", text: "#2A4A5C" }, { bg: "#F0EEE8", text: "#5C5A2A" },
];

function getAgentInitials(name: string): string {
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
// Displays the base AGENT.md prompt body; allows viewing and optionally editing
// a per-user prompt override (stored server-side; AGENT.md is never mutated).

function AgentPromptSection({ agent }: { agent: AgentDef }) {
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
    <div className="rounded-xl border border-gray-200 overflow-hidden">
      {/* Collapsible header */}
      <button
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-gray-50 transition-colors text-left"
      >
        <div className="flex items-center gap-2.5">
          <FileText className="h-4 w-4 text-gray-400 flex-shrink-0" />
          <div>
            <p className="text-[11px] font-semibold text-gray-700">System Prompt</p>
            <p className="text-[10px] text-gray-400">
              {promptData?.has_override ? "Custom override active" : "Base AGENT.md prompt"}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {promptData?.has_override && (
            <span className="text-[9px] font-semibold px-1.5 py-0.5 rounded bg-brand-fill text-brand">overridden</span>
          )}
          <ChevronDown className={`h-3.5 w-3.5 text-gray-400 transition-transform ${open ? "rotate-180" : ""}`} />
        </div>
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.18 }}
            className="overflow-hidden border-t border-gray-200"
          >
            <div className="bg-white">
              {loading && (
                <p className="text-[11px] text-gray-400 px-4 py-3">Loading prompt…</p>
              )}
              {error && (
                <p className="text-[11px] text-red-500 px-4 py-3">{error}</p>
              )}
              {!loading && !error && promptData && (
                <>
                  {/* Source badge */}
                  <div className="flex items-center justify-between px-4 pt-3 pb-2 gap-2">
                    <span className={`text-[9px] font-semibold px-2 py-0.5 rounded-full border ${
                      promptData.has_override
                        ? "bg-brand-fill text-brand border-brand-border"
                        : "bg-gray-100 text-gray-500 border-gray-200"
                    }`}>
                      {promptData.has_override ? "Your override" : "Default AGENT.md"}
                    </span>
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
                          className="flex items-center gap-1 text-[10px] font-semibold text-gray-500 hover:text-gray-900 transition-colors px-2 py-0.5 rounded-md hover:bg-gray-100"
                        >
                          <Edit3 className="h-3 w-3" /> Edit
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Prompt content */}
                  {editMode ? (
                    <div className="px-4 pb-3 space-y-2">
                      <textarea
                        value={draftContent}
                        onChange={e => setDraftContent(e.target.value)}
                        rows={12}
                        className="w-full px-3 py-2 text-[11px] font-mono bg-gray-50 border border-gray-200 rounded-lg focus:outline-none focus:border-gray-400 resize-none leading-relaxed transition-colors"
                        placeholder="Enter custom prompt instructions…"
                      />
                      <p className="text-[9px] text-gray-400">{draftContent.length} chars · max 32,768</p>
                      {saveError && (
                        <p className="text-[11px] text-red-500">{saveError}</p>
                      )}
                      <div className="flex items-center gap-2 justify-end">
                        <button
                          onClick={() => { setEditMode(false); setSaveError(null); }}
                          className="px-3 py-1.5 rounded-lg text-[11px] font-medium text-gray-500 hover:bg-gray-100 transition-colors"
                        >
                          Cancel
                        </button>
                        <button
                          onClick={handleSave}
                          disabled={saving || !draftContent.trim()}
                          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-gray-900 text-white text-[11px] font-semibold hover:bg-gray-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                        >
                          {saving ? "Saving…" : <><Check className="h-3 w-3" /> Save override</>}
                        </button>
                      </div>
                    </div>
                  ) : (
                    <pre className="px-4 pb-4 text-[10.5px] text-gray-600 leading-relaxed whitespace-pre-wrap font-mono overflow-x-auto max-h-64 overflow-y-auto">
                      {displayContent || <span className="text-gray-400 italic">No prompt body found.</span>}
                    </pre>
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
  attachedSkills: propSkills, attachedHooks: propHooks,
  onAttachSkill: propAttachSkill, onAttachHook: propAttachHook,
  onSelectionsChange, initialSelections, token,
}: {
  agent: AgentDef;
  agentIndex: number;
  onClose: () => void;
  attachedSkills?: AttachedSkill[];
  attachedHooks?: AttachedHook[];
  onAttachSkill?: (skill: AttachedSkill) => void;
  onAttachHook?: (hook: AttachedHook) => void;
  /** Pass-through to AdvancedExpander for per-agent config levers */
  onSelectionsChange?: (selections: SelectionsMap) => void;
  initialSelections?: SelectionsMap;
  token?: string | null;
}) {
  // Always use context — works from Library page, Add agent modal, and AgentsPopup
  const ctx = useSkillsHooks();
  const attachedSkills = ctx.attachedSkills;
  const attachedHooks = ctx.attachedHooks;
  const onAttachSkill = ctx.attachSkill;
  const onAttachHook = ctx.attachHook;

  // Custom skill editor state
  const [customSkillOpen, setCustomSkillOpen] = useState(false);
  const [customSkillName, setCustomSkillName] = useState("");
  const [customSkillContent, setCustomSkillContent] = useState("");
  const [customAttached, setCustomAttached] = useState(false);
  const iconStyle = ICON_STYLES[agentIndex % ICON_STYLES.length];
  const capabilities = getCapabilities(agent);
  const pipelineLabel = PIPELINE_LABEL[agent.pipeline_type] ?? agent.pipeline_type;

  const suggestedSkills = SKILLS.filter(s => s.compatible_agents.includes(agent.id)).slice(0, 3);
  const suggestedHooks = HOOKS.filter(h => h.compatible_agents.includes(agent.id)).slice(0, 3);

  const isSkillAttached = (id: string) => attachedSkills.some(s => s.id === id);
  const isHookAttached = (id: string) => attachedHooks.some(h => h.id === id);

  const handleAttachSkill = (skill: SkillDef) => {
    if (isSkillAttached(skill.id)) return;
    onAttachSkill?.({
      id: skill.id, name: skill.name, source: skill.source,
      sourceLabel: skill.sourceLabel, category: skill.category, content: skill.content,
    });
  };

  const handleAttachHook = (hook: HookDef) => {
    if (isHookAttached(hook.id)) return;
    onAttachHook?.({
      id: hook.id, name: hook.name, source: hook.source,
      sourceLabel: hook.sourceLabel, event: hook.event, trigger: hook.trigger,
      description: hook.description,
    });
  };

  return (
    <motion.div
      initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      className="fixed inset-0 z-[80] flex items-center justify-center p-6 bg-black/30 backdrop-blur-sm"
      onClick={onClose}
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.96, y: 12 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.96, y: 12 }}
        transition={{ duration: 0.18 }}
        onClick={e => e.stopPropagation()}
        className="bg-white rounded-2xl shadow-2xl border border-gray-200 w-full max-w-md overflow-hidden max-h-[90vh] flex flex-col"
      >
        {/* Header */}
        <div className="px-6 pt-6 pb-4 border-b border-gray-100 flex-shrink-0">
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="w-11 h-11 rounded-xl flex items-center justify-center flex-shrink-0 text-[13px] font-bold"
                style={{ background: iconStyle.bg, color: iconStyle.text }}>
                {getAgentInitials(agent.name)}
              </div>
              <div>
                <h2 className="text-[15px] font-bold text-gray-900 leading-tight">{agent.name}</h2>
                <p className="text-[11px] text-gray-500 mt-0.5">{agent.role}</p>
              </div>
            </div>
            <button onClick={onClose} className="h-7 w-7 flex items-center justify-center rounded-lg text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-all flex-shrink-0">
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="flex items-center gap-2 mt-3">
            <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full border bg-gray-100 text-gray-600 border-gray-200">{pipelineLabel}</span>
            <span className="flex items-center gap-1 text-[10px] text-gray-400"><Clock className="h-3 w-3" />~{agent.estimated_duration}s</span>
            {agent.has_skill && (
              <span className="flex items-center gap-1 text-[10px] text-gray-600 bg-gray-100 border border-gray-200 px-2 py-0.5 rounded-full">
                <BookMarked className="h-2.5 w-2.5" />Skill support
              </span>
            )}
          </div>
        </div>

        {/* Scrollable body */}
        <div className="overflow-y-auto flex-1 px-6 py-4 space-y-4">

          {/* 1. What this agent does */}
          <div>
            <div className="flex items-center gap-2 mb-2.5">
              <Zap className="h-3.5 w-3.5 text-gray-400" />
              <p className="text-[10px] font-semibold text-gray-500 uppercase tracking-wide">What this agent does</p>
            </div>
            <div className="space-y-2">
              {capabilities.map((cap, i) => (
                <div key={i} className="flex items-start gap-2.5">
                  <CheckCircle2 className="h-3.5 w-3.5 text-gray-400 flex-shrink-0 mt-0.5" />
                  <p className="text-[12px] text-gray-700 leading-relaxed">{cap}</p>
                </div>
              ))}
            </div>
          </div>

          {/* Pipeline step */}
          <div className="rounded-xl border border-gray-100 bg-gray-50 px-4 py-3">
            <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wide mb-1.5">Pipeline</p>
            <div className="flex items-center gap-2">
              <span className="text-[11px] font-medium px-2 py-0.5 rounded-md border bg-gray-100 text-gray-600 border-gray-200">{pipelineLabel}</span>
              <ChevronRight className="h-3 w-3 text-gray-300" />
              <span className="text-[11px] text-gray-600 font-medium">Step {agent.order}</span>
            </div>
          </div>

          {/* 2. System Prompt (KAN-76) */}
          <AgentPromptSection agent={agent} />

          {/* 3. Advanced Configuration levers (Model · Validator · Gate · Retry) */}
          {onSelectionsChange && (
            <div>
              <div className="flex items-center gap-2 mb-2.5">
                <Settings2 className="h-3.5 w-3.5 text-gray-400" />
                <p className="text-[10px] font-semibold text-gray-500 uppercase tracking-wide">Configuration</p>
                <span className="text-[9px] text-gray-400">Model · Validator · Gate · Retry</span>
              </div>
              <AdvancedExpander
                agents={[{ id: agent.id, name: agent.name }]}
                onSelectionsChange={onSelectionsChange}
                initialSelections={initialSelections}
                token={token}
              />
            </div>
          )}

          {/* 4. Skills — Suggested Skills */}
          {suggestedSkills.length > 0 && (
            <div>
              <div className="flex items-center gap-2 mb-2.5">
                <Puzzle className="h-3.5 w-3.5 text-gray-400" />
                <p className="text-[10px] font-semibold text-gray-500 uppercase tracking-wide">Suggested Skills</p>
              </div>
              <div className="space-y-1.5">
                {suggestedSkills.map(skill => {
                  const attached = isSkillAttached(skill.id);
                  return (
                    <div key={skill.id} className="flex items-center justify-between gap-3 rounded-lg border border-gray-100 bg-gray-50 px-3 py-2">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-1.5 mb-0.5">
                          <p className="text-[11px] font-semibold text-gray-800 truncate">{skill.name}</p>
                        </div>
                        <p className="text-[10px] text-gray-500 leading-relaxed line-clamp-1">{skill.description}</p>
                      </div>
                      <button
                        onClick={() => handleAttachSkill(skill)}
                        disabled={attached}
                        className={`flex-shrink-0 flex items-center gap-1 px-2.5 py-1 rounded-lg text-[10px] font-semibold transition-colors ${
                          attached
                            ? "bg-gray-100 text-gray-400 cursor-default"
                            : "bg-gray-900 text-white hover:bg-gray-700 cursor-pointer"
                        }`}
                      >
                        {attached ? <><Check className="h-2.5 w-2.5" /> Added</> : <><Plus className="h-2.5 w-2.5" /> Attach</>}
                      </button>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Suggested Hooks */}
          {suggestedHooks.length > 0 && (
            <div>
              <div className="flex items-center gap-2 mb-2.5">
                <Webhook className="h-3.5 w-3.5 text-gray-400" />
                <p className="text-[10px] font-semibold text-gray-500 uppercase tracking-wide">Suggested Hooks</p>
              </div>
              <div className="space-y-1.5">
                {suggestedHooks.map(hook => {
                  const attached = isHookAttached(hook.id);
                  return (
                    <div key={hook.id} className="flex items-center justify-between gap-3 rounded-lg border border-gray-100 bg-gray-50 px-3 py-2">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-1.5 mb-0.5">
                          <p className="text-[11px] font-semibold text-gray-800 truncate">{hook.name}</p>
                          <span className="text-[9px] font-semibold px-1.5 py-0.5 rounded bg-gray-200 text-gray-500 flex-shrink-0">{hook.event}</span>
                        </div>
                        <p className="text-[10px] text-gray-500 leading-relaxed line-clamp-1">{hook.description}</p>
                      </div>
                      <button
                        onClick={() => handleAttachHook(hook)}
                        disabled={attached}
                        className={`flex-shrink-0 flex items-center gap-1 px-2.5 py-1 rounded-lg text-[10px] font-semibold transition-colors ${
                          attached
                            ? "bg-gray-100 text-gray-400 cursor-default"
                            : "bg-gray-900 text-white hover:bg-gray-700 cursor-pointer"
                        }`}
                      >
                        {attached ? <><Check className="h-2.5 w-2.5" /> Added</> : <><Plus className="h-2.5 w-2.5" /> Attach</>}
                      </button>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Custom skill */}
          {agent.has_skill && (
            <div className="rounded-xl border border-gray-200 bg-gray-50 overflow-hidden">
              {/* Header — always visible, clickable to expand */}
              <button
                onClick={() => { setCustomSkillOpen(v => !v); setCustomAttached(false); }}
                className="w-full flex items-center justify-between px-4 py-3 hover:bg-gray-100 transition-colors text-left"
              >
                <div className="flex items-center gap-2.5">
                  <BookMarked className="h-4 w-4 text-gray-500 flex-shrink-0" />
                  <div>
                    <p className="text-[11px] font-semibold text-gray-700">Custom skill</p>
                    <p className="text-[10px] text-gray-400">Write your own SKILL.md instructions for this agent</p>
                  </div>
                </div>
                <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-md transition-colors ${
                  customSkillOpen ? "text-gray-400" : "text-gray-500 hover:text-gray-800"
                }`}>
                  {customSkillOpen ? "cancel" : "+ add custom"}
                </span>
              </button>

              {/* Inline editor — expands when open */}
              <AnimatePresence>
                {customSkillOpen && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.18 }}
                    className="overflow-hidden border-t border-gray-200"
                  >
                    <div className="px-4 py-3 space-y-3 bg-white">
                      {/* Skill name */}
                      <div>
                        <label className="text-[10px] font-semibold text-gray-500 uppercase tracking-wide block mb-1">Skill name</label>
                        <input
                          type="text"
                          value={customSkillName}
                          onChange={e => setCustomSkillName(e.target.value)}
                          placeholder={`e.g. ${agent.name} domain rules`}
                          className="w-full px-3 py-2 text-[12px] bg-gray-50 border border-gray-200 rounded-lg focus:outline-none focus:border-gray-400 placeholder-gray-400 transition-colors"
                        />
                      </div>
                      {/* Skill content */}
                      <div>
                        <label className="text-[10px] font-semibold text-gray-500 uppercase tracking-wide block mb-1">
                          Instructions <span className="text-gray-400 normal-case font-normal">(paste your SKILL.md content or write custom instructions)</span>
                        </label>
                        <textarea
                          value={customSkillContent}
                          onChange={e => setCustomSkillContent(e.target.value)}
                          placeholder={`# ${agent.name} Custom Skill\n\nWrite domain-specific instructions here.\nThese will be injected into this agent's prompt.\n\n## Rules\n- Rule 1\n- Rule 2`}
                          rows={7}
                          className="w-full px-3 py-2 text-[11px] font-mono bg-gray-50 border border-gray-200 rounded-lg focus:outline-none focus:border-gray-400 placeholder-gray-400 resize-none leading-relaxed transition-colors"
                        />
                        <p className="text-[9px] text-gray-400 mt-1">{customSkillContent.length} characters</p>
                      </div>
                      {/* Attach button */}
                      <div className="flex items-center justify-between">
                        <p className="text-[10px] text-gray-400 leading-relaxed max-w-[200px]">
                          This skill will be injected into the agent&apos;s prompt when the pipeline runs.
                        </p>
                        <button
                          onClick={() => {
                            if (!customSkillName.trim() || !customSkillContent.trim()) return;
                            onAttachSkill({
                              id: `custom-${agent.id}-${Date.now()}`,
                              name: customSkillName.trim(),
                              source: "ecc",
                              sourceLabel: "Custom",
                              category: "workflow",
                              content: customSkillContent.trim(),
                            });
                            setCustomAttached(true);
                            setCustomSkillOpen(false);
                            setCustomSkillName("");
                            setCustomSkillContent("");
                          }}
                          disabled={!customSkillName.trim() || !customSkillContent.trim()}
                          className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-gray-900 text-white text-[11px] font-semibold hover:bg-gray-700 transition-colors disabled:opacity-30 disabled:cursor-not-allowed flex-shrink-0"
                        >
                          {customAttached ? <><Check className="h-3 w-3" /> Attached</> : <><Plus className="h-3 w-3" /> Attach skill</>}
                        </button>
                      </div>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>

              {/* Success state */}
              {customAttached && !customSkillOpen && (
                <div className="px-4 py-2 border-t border-gray-200 bg-white flex items-center gap-2">
                  <Check className="h-3.5 w-3.5 text-gray-500" />
                  <p className="text-[11px] text-gray-600 font-medium">Custom skill attached</p>
                </div>
              )}
            </div>
          )}

        </div>
      </motion.div>
    </motion.div>
  );
}


// ─── SkillsHooksTab ───────────────────────────────────────────────────────────

function SkillsHooksTab({ pipelineType }: { pipelineType: WorkflowType }) {
  const { attachedSkills, attachedHooks, attachSkill, detachSkill, attachHook, detachHook } = useSkillsHooks();
  const [skillsOpen, setSkillsOpen] = useState(false);
  const [hooksOpen, setHooksOpen] = useState(false);
  const [skillSearch, setSkillSearch] = useState("");
  const [skillCategory, setSkillCategory] = useState("all");
  const [hookSearch, setHookSearch] = useState("");
  const [hookEvent, setHookEvent] = useState("all");

  const isSkillAttached = (id: string) => attachedSkills.some(s => s.id === id);
  const isHookAttached = (id: string) => attachedHooks.some(h => h.id === id);

  const filteredSkills = SKILLS.filter(s => {
    const matchCat = skillCategory === "all" || s.category === skillCategory;
    const matchSearch = !skillSearch ||
      s.name.toLowerCase().includes(skillSearch.toLowerCase()) ||
      s.description.toLowerCase().includes(skillSearch.toLowerCase());
    return matchCat && matchSearch;
  });

  const filteredHooks = HOOKS.filter(h => {
    const matchEvent = hookEvent === "all" || h.event === hookEvent;
    const matchSearch = !hookSearch ||
      h.name.toLowerCase().includes(hookSearch.toLowerCase()) ||
      h.description.toLowerCase().includes(hookSearch.toLowerCase());
    return matchEvent && matchSearch;
  });

  return (
    <div className="flex-1 overflow-y-auto p-5 space-y-5">

      {/* ── SKILLS SECTION ── */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Puzzle className="h-4 w-4 text-gray-400" />
            <span className="text-[13px] font-semibold text-gray-800">Skills</span>
            {attachedSkills.length > 0 && (
              <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded-full bg-gray-900 text-white">{attachedSkills.length}</span>
            )}
          </div>
          <button
            onClick={() => setSkillsOpen(v => !v)}
            className="flex items-center gap-1 text-[11px] font-semibold text-gray-500 hover:text-gray-900 transition-colors"
          >
            <Plus className="h-3.5 w-3.5" /> Add skill
          </button>
        </div>

        {/* Attached skills */}
        {attachedSkills.length > 0 && (
          <div className="space-y-1.5 mb-3">
            {attachedSkills.map(skill => (
              <div key={skill.id} className="flex items-center justify-between gap-3 rounded-lg border border-gray-200 bg-white px-3 py-2">
                <div className="flex items-center gap-2 min-w-0">
                  <CheckCircle2 className="h-3.5 w-3.5 text-gray-500 flex-shrink-0" />
                  <span className="text-[12px] font-semibold text-gray-800 truncate">{skill.name}</span>
                </div>
                <button onClick={() => detachSkill(skill.id)} className="flex-shrink-0 text-gray-300 hover:text-red-400 transition-colors">
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
            ))}
          </div>
        )}

        {attachedSkills.length === 0 && !skillsOpen && (
          <div className="rounded-lg border border-dashed border-gray-200 px-4 py-3 text-center">
            <p className="text-[11px] text-gray-400">No skills attached · click &quot;Add skill&quot; to browse</p>
          </div>
        )}

        {/* Skills picker */}
        {skillsOpen && (
          <motion.div
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            className="rounded-xl border border-gray-200 bg-white overflow-hidden"
          >
            {/* Search + filter */}
            <div className="p-3 border-b border-gray-100 space-y-2">
              <div className="relative">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3 w-3 text-gray-400" />
                <input
                  value={skillSearch}
                  onChange={e => setSkillSearch(e.target.value)}
                  placeholder="Search skills..."
                  className="w-full pl-7 pr-3 py-1.5 text-[11px] bg-gray-50 border border-gray-200 rounded-lg focus:outline-none focus:border-gray-400 placeholder-gray-400"
                />
              </div>
              <div className="flex gap-1 flex-wrap">
                {SKILL_CATEGORIES.map(cat => (
                  <button
                    key={cat.id}
                    onClick={() => setSkillCategory(cat.id)}
                    className={`px-2 py-0.5 rounded-full text-[9px] font-semibold transition-colors ${
                      skillCategory === cat.id
                        ? "bg-gray-900 text-white"
                        : "bg-gray-100 text-gray-500 hover:bg-gray-200"
                    }`}
                  >
                    {cat.label}
                  </button>
                ))}
              </div>
            </div>
            {/* Skill list */}
            <div className="max-h-[240px] overflow-y-auto divide-y divide-gray-50">
              {filteredSkills.length === 0 ? (
                <p className="text-[11px] text-gray-400 text-center py-4">No skills found</p>
              ) : filteredSkills.map(skill => {
                const attached = isSkillAttached(skill.id);
                return (
                  <div key={skill.id} className="flex items-start justify-between gap-3 px-3 py-2.5 hover:bg-gray-50 transition-colors">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1.5 mb-0.5">
                        <p className="text-[11px] font-semibold text-gray-800">{skill.name}</p>
                        <span className="text-[9px] text-gray-400 capitalize">{skill.category}</span>
                      </div>
                      <p className="text-[10px] text-gray-500 leading-relaxed line-clamp-2">{skill.description}</p>
                    </div>
                    <button
                      onClick={() => {
                        if (!attached) {
                          attachSkill({ id: skill.id, name: skill.name, source: skill.source, sourceLabel: skill.sourceLabel, category: skill.category, content: skill.content });
                        }
                      }}
                      disabled={attached}
                      className={`flex-shrink-0 flex items-center gap-1 px-2.5 py-1 rounded-lg text-[10px] font-semibold transition-colors mt-0.5 ${
                        attached ? "bg-gray-100 text-gray-400 cursor-default" : "bg-gray-900 text-white hover:bg-gray-700"
                      }`}
                    >
                      {attached ? <><Check className="h-2.5 w-2.5" /> Added</> : <><Plus className="h-2.5 w-2.5" /> Add</>}
                    </button>
                  </div>
                );
              })}
            </div>
            <div className="p-2 border-t border-gray-100 flex justify-end">
              <button onClick={() => setSkillsOpen(false)} className="text-[10px] text-gray-400 hover:text-gray-700 px-2 py-1">Done</button>
            </div>
          </motion.div>
        )}
      </div>

      {/* ── HOOKS SECTION ── */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Webhook className="h-4 w-4 text-gray-400" />
            <span className="text-[13px] font-semibold text-gray-800">Hooks</span>
            {attachedHooks.length > 0 && (
              <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded-full bg-gray-900 text-white">{attachedHooks.length}</span>
            )}
          </div>
          <button
            onClick={() => setHooksOpen(v => !v)}
            className="flex items-center gap-1 text-[11px] font-semibold text-gray-500 hover:text-gray-900 transition-colors"
          >
            <Plus className="h-3.5 w-3.5" /> Add hook
          </button>
        </div>

        {/* Attached hooks */}
        {attachedHooks.length > 0 && (
          <div className="space-y-1.5 mb-3">
            {attachedHooks.map(hook => (
              <div key={hook.id} className="flex items-center justify-between gap-3 rounded-lg border border-gray-200 bg-white px-3 py-2">
                <div className="flex items-center gap-2 min-w-0">
                  <CheckCircle2 className="h-3.5 w-3.5 text-gray-500 flex-shrink-0" />
                  <span className="text-[12px] font-semibold text-gray-800 truncate">{hook.name}</span>
                  <span className="text-[9px] font-semibold px-1.5 py-0.5 rounded bg-gray-100 text-gray-500 flex-shrink-0">{hook.event}</span>
                </div>
                <button onClick={() => detachHook(hook.id)} className="flex-shrink-0 text-gray-300 hover:text-red-400 transition-colors">
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
            ))}
          </div>
        )}

        {attachedHooks.length === 0 && !hooksOpen && (
          <div className="rounded-lg border border-dashed border-gray-200 px-4 py-3 text-center">
            <p className="text-[11px] text-gray-400">No hooks attached · click &quot;Add hook&quot; to browse</p>
          </div>
        )}

        {/* Hooks picker */}
        {hooksOpen && (
          <motion.div
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            className="rounded-xl border border-gray-200 bg-white overflow-hidden"
          >
            <div className="p-3 border-b border-gray-100 space-y-2">
              <div className="relative">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3 w-3 text-gray-400" />
                <input
                  value={hookSearch}
                  onChange={e => setHookSearch(e.target.value)}
                  placeholder="Search hooks..."
                  className="w-full pl-7 pr-3 py-1.5 text-[11px] bg-gray-50 border border-gray-200 rounded-lg focus:outline-none focus:border-gray-400 placeholder-gray-400"
                />
              </div>
              <div className="flex gap-1 flex-wrap">
                {HOOK_EVENTS.map(ev => (
                  <button
                    key={ev.id}
                    onClick={() => setHookEvent(ev.id)}
                    className={`px-2 py-0.5 rounded-full text-[9px] font-semibold transition-colors ${
                      hookEvent === ev.id
                        ? "bg-gray-900 text-white"
                        : "bg-gray-100 text-gray-500 hover:bg-gray-200"
                    }`}
                  >
                    {ev.label}
                  </button>
                ))}
              </div>
            </div>
            <div className="max-h-[240px] overflow-y-auto divide-y divide-gray-50">
              {filteredHooks.length === 0 ? (
                <p className="text-[11px] text-gray-400 text-center py-4">No hooks found</p>
              ) : filteredHooks.map(hook => {
                const attached = isHookAttached(hook.id);
                return (
                  <div key={hook.id} className="flex items-start justify-between gap-3 px-3 py-2.5 hover:bg-gray-50 transition-colors">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1.5 mb-0.5">
                        <p className="text-[11px] font-semibold text-gray-800">{hook.name}</p>
                        <span className="text-[9px] font-semibold px-1.5 py-0.5 rounded bg-gray-100 text-gray-500">{hook.event}</span>
                      </div>
                      <p className="text-[10px] text-gray-500 leading-relaxed line-clamp-2">{hook.description}</p>
                      <p className="text-[9px] text-gray-400 mt-0.5 italic">{hook.trigger}</p>
                    </div>
                    <button
                      onClick={() => {
                        if (!attached) {
                          attachHook({ id: hook.id, name: hook.name, source: hook.source, sourceLabel: hook.sourceLabel, event: hook.event, trigger: hook.trigger, description: hook.description });
                        }
                      }}
                      disabled={attached}
                      className={`flex-shrink-0 flex items-center gap-1 px-2.5 py-1 rounded-lg text-[10px] font-semibold transition-colors mt-0.5 ${
                        attached ? "bg-gray-100 text-gray-400 cursor-default" : "bg-gray-900 text-white hover:bg-gray-700"
                      }`}
                    >
                      {attached ? <><Check className="h-2.5 w-2.5" /> Added</> : <><Plus className="h-2.5 w-2.5" /> Add</>}
                    </button>
                  </div>
                );
              })}
            </div>
            <div className="p-2 border-t border-gray-100 flex justify-end">
              <button onClick={() => setHooksOpen(false)} className="text-[10px] text-gray-400 hover:text-gray-700 px-2 py-1">Done</button>
            </div>
          </motion.div>
        )}
      </div>

      {/* Info note */}
      <div className="rounded-xl border border-gray-100 bg-gray-50 px-4 py-3">
        <p className="text-[10px] text-gray-500 leading-relaxed">
          <span className="font-semibold text-gray-700">Skills</span> inject domain-specific instructions into agent prompts.{" "}
          <span className="font-semibold text-gray-700">Hooks</span> define pre/post behaviours that guide agent execution.
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
        <p className="text-[10px] font-semibold text-gray-500 uppercase tracking-widest">
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
                <span className="font-semibold text-gray-700 truncate max-w-[120px]">
                  {d.step}
                </span>
                <span className="text-gray-500 flex-1 min-w-0">
                  {d.capabilities.join(" · ")}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {loading && (
        <p className="text-[11px] text-gray-400 py-2">Loading capabilities…</p>
      )}

      {error && (
        <div className="flex items-center gap-1.5 text-[11px] text-red-600 bg-red-50 rounded-lg px-2.5 py-1.5">
          <AlertCircle className="h-3 w-3 flex-shrink-0" />
          {error}
        </div>
      )}

      {!loading && !error && capabilities.length === 0 && (
        <div className="py-2">
          <p className="text-[11px] font-semibold text-gray-500">
            No capabilities available
          </p>
          <p className="text-[10px] text-gray-400">
            The capability registry returned nothing. Reload, or contact support
            if this persists.
          </p>
        </div>
      )}

      {!loading && !error && capabilities.length > 0 && (
        <div className="space-y-3 max-h-[200px] overflow-y-auto pr-1">
          {groups.map((group) => (
            <div key={group.kind} role="group" aria-label={titleCaseKind(group.kind)}>
              <p className="text-[10px] font-semibold text-gray-500 uppercase tracking-widest mb-1">
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
                          ? "bg-gray-50 border-gray-100 opacity-80 cursor-not-allowed"
                          : "bg-gray-50 border-gray-100"
                      }`}
                    >
                      <div className="flex items-center gap-2">
                        {locked && (
                          <Lock className="h-3 w-3 text-gray-400 flex-shrink-0" />
                        )}
                        <p
                          className={`text-[11px] font-semibold truncate flex-1 min-w-0 ${
                            locked ? "text-gray-400" : "text-gray-800"
                          }`}
                        >
                          {cap.name}
                        </p>
                        {locked && (
                          <span className="text-[10px] text-gray-400 flex-shrink-0">
                            Engineer-only
                          </span>
                        )}
                        {cap.security_gated && !locked && (
                          <Lock className="h-3 w-3 text-gray-400 flex-shrink-0" />
                        )}
                        {hasSchema && (
                          <button
                            type="button"
                            onClick={() => toggle(rowKey)}
                            aria-expanded={isOpen}
                            aria-label={`Configuration for ${cap.name}`}
                            className="flex items-center justify-center h-5 w-5 rounded text-gray-400 hover:text-brand flex-shrink-0"
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
                            locked ? "text-gray-400" : "text-gray-500"
                          }`}
                        >
                          {cap.description}
                        </p>
                      )}
                      {hasSchema && isOpen && (
                        <div className="mt-1 rounded-md bg-white border border-gray-100 px-2 py-1 space-y-0.5">
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
                                  className="text-[10px] text-gray-500 font-mono"
                                >
                                  {field}
                                  {/* Required marker — gray scale only, never
                                      navy/red (preserve locked-row neutrality). */}
                                  {isRequired && (
                                    <span className="text-gray-400">*</span>
                                  )}
                                  {fieldType && (
                                    <span className="ml-1 text-[9px] text-gray-400">
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
};
export type SelectionsMap = Record<string, StepSelection>;

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
export function AdvancedExpander({
  agents,
  onSelectionsChange,
  token,
  initialSelections,
}: {
  agents: { id: string; name: string }[];
  /** Reports the compact per-step selections map upward (the 22-04 shape). */
  onSelectionsChange?: (selections: SelectionsMap) => void;
  /** Optional JWT override (defaults to the stored token), mirroring the picker. */
  token?: string | null;
  /** WR-01 — seed the per-step selections when launching a saved workflow. */
  initialSelections?: SelectionsMap;
}) {
  const [validatorOptions, setValidatorOptions] = useState<string[]>([]);
  const [gateOptions, setGateOptions] = useState<string[]>([]);
  const [modelOptions, setModelOptions] = useState<CapabilityModelEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [selections, setSelections] = useState<SelectionsMap>(initialSelections ?? {});

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
  ) =>
    setSelections((prev) => {
      const cur: StepSelection = { ...(prev[agentId] ?? {}) };
      // Apply the patch; an empty/undefined value clears the key (no override).
      for (const [k, v] of Object.entries(patch)) {
        const key = k as keyof StepSelection;
        if (v === undefined || v === "" || (Array.isArray(v) && v.length === 0)) {
          delete cur[key];
        } else {
          // @ts-expect-error — keyed assignment across the union is safe here.
          cur[key] = v;
        }
      }
      // EMP-04 (D-07): a validator selection requires the `validation` gate.
      // Auto-attach it (deduped) so the validators actually fire at run time —
      // mirroring selections.py. Removing all validators drops the auto gate
      // unless the user explicitly picked it.
      if (cur.validators && cur.validators.length > 0) {
        const gates = new Set(cur.gates ?? []);
        gates.add(COUPLED_GATE);
        cur.gates = Array.from(gates);
      }
      const next: SelectionsMap = { ...prev };
      if (Object.keys(cur).length === 0) delete next[agentId];
      else next[agentId] = cur;
      onSelectionsChange?.(next);
      return next;
    });

  if (loading) {
    return (
      <div className="flex flex-col">
        <p className="text-[11px] text-gray-400 py-2">Loading levers…</p>
      </div>
    );
  }
  if (error) {
    return (
      <div className="flex items-center gap-1.5 text-[11px] text-red-600 bg-red-50 rounded-lg px-2.5 py-1.5">
        <AlertCircle className="h-3 w-3 flex-shrink-0" />
        {error}
      </div>
    );
  }
  if (agents.length === 0) {
    return (
      <p className="text-[11px] text-gray-400 py-2">
        Add agents to assign per-agent levers.
      </p>
    );
  }

  return (
    <div className="flex flex-col space-y-1.5 max-h-[200px] overflow-y-auto pr-1">
      {agents.map((agent) => {
        const isOpen = expanded.has(agent.id);
        const region = `advanced-${agent.id}`;
        const sel = selections[agent.id] ?? {};
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
              className="flex items-center gap-1.5 text-left text-[11px] font-semibold text-gray-700 hover:text-brand py-1"
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
              <span className="text-[9px] text-gray-400 flex-shrink-0">
                Validator · Gate · Model · Retry
              </span>
            </button>

            {isOpen && (
              <div id={region} className="space-y-1.5 pl-4">
                {/* Validator lever (EMP-01) */}
                <div className="flex items-center gap-2 bg-gray-50 border border-gray-100 rounded-lg px-2.5 py-1.5">
                  <label
                    htmlFor={`${region}-validator`}
                    className="text-[11px] font-semibold text-gray-700 flex-1 min-w-0"
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
                    className="text-[10px] text-gray-700 bg-white border border-gray-200 rounded-md px-1.5 py-1 focus:outline-none focus:border-brand max-w-[140px]"
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
                <div className="flex items-center gap-2 bg-gray-50 border border-gray-100 rounded-lg px-2.5 py-1.5">
                  <label
                    htmlFor={`${region}-gate`}
                    className="text-[11px] font-semibold text-gray-700 flex-1 min-w-0"
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
                    className="text-[10px] text-gray-700 bg-white border border-gray-200 rounded-md px-1.5 py-1 focus:outline-none focus:border-brand max-w-[140px]"
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
                <div className="flex flex-col gap-1.5 bg-gray-50 border border-gray-100 rounded-lg px-2.5 py-1.5">
                  <div className="flex items-center gap-2">
                    <label
                      htmlFor={`${region}-model`}
                      className="text-[11px] font-semibold text-gray-700 flex-1 min-w-0"
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
                      className="text-[10px] text-gray-700 bg-white border border-gray-200 rounded-md px-1.5 py-1 focus:outline-none focus:border-brand min-w-[160px] max-w-[200px]"
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
                      fast: "bg-green-50 text-green-700 border-green-200",
                      balanced: "bg-blue-50 text-blue-700 border-blue-200",
                      powerful: "bg-purple-50 text-purple-700 border-purple-200",
                    };
                    return (
                      <div className="flex items-start gap-1.5 pt-0.5">
                        <span className={`text-[9px] font-semibold px-1.5 py-0.5 rounded border flex-shrink-0 uppercase tracking-wide ${tierColor[picked.tier] ?? "bg-gray-50 text-gray-600 border-gray-200"}`}>
                          {picked.tier}
                        </span>
                        <span className="text-[9px] text-gray-400 flex-shrink-0">
                          {ctxK} ctx
                        </span>
                        <span className="text-[9px] text-gray-500 leading-tight line-clamp-2 min-w-0">
                          {picked.description}
                        </span>
                      </div>
                    );
                  })()}
                </div>

                {/* Retry lever (EMP-01) */}
                <div className="flex items-center gap-2 bg-gray-50 border border-gray-100 rounded-lg px-2.5 py-1.5">
                  <label
                    htmlFor={`${region}-retry`}
                    className="text-[11px] font-semibold text-gray-700 flex-1 min-w-0"
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
                    className="text-[10px] text-gray-700 bg-white border border-gray-200 rounded-md px-1.5 py-1 focus:outline-none focus:border-brand max-w-[140px]"
                  >
                    <option value="">Default</option>
                    {RETRY_OPTIONS.map((n) => (
                      <option key={n} value={n}>
                        {n} {n === 1 ? "attempt" : "attempts"}
                      </option>
                    ))}
                  </select>
                </div>

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

const COLS = 3;

export function AgentsPopup({
  isOpen, onClose, agents, pipelineType,
  onAddAgent, onRemoveAgent, onReorder, canAddMore = true,
  onModelOverridesChange, initialModelOverrides,
  onSelectionsChange, initialSelections,
  declaredCapabilities,
}: AgentsPopupProps) {
  const { attachedSkills, attachedHooks } = useSkillsHooks();
  const [libraryOpen, setLibraryOpen] = useState(false);
  const [draggedIdx, setDraggedIdx] = useState<number | null>(null);
  const [dragOverIdx, setDragOverIdx] = useState<number | null>(null);
  const [capAgent, setCapAgent] = useState<{ agent: AgentDef; index: number } | null>(null);
  const [activeTab, setActiveTab] = useState<"agents" | "skills-hooks">("agents");

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
  const [liveSelections, setLiveSelections] = useState<SelectionsMap>(
    initialSelections ?? {},
  );
  const handleSelectionsChange = useCallback(
    (next: SelectionsMap) => {
      setLiveSelections(next);
      onSelectionsChange?.(next);
    },
    [onSelectionsChange],
  );

  const handleSaveWorkflow = useCallback(
    async (name: string, description: string) => {
      const token = getToken();
      if (!token) {
        setSaveError("Not authenticated.");
        return;
      }
      setSaving(true);
      setSaveError(null);
      try {
        await createUserWorkflow(token, {
          name,
          ...(description ? { description } : {}),
          base_pipeline_type: pipelineType,
          agent_ids: agents.map((a) => a.id),
          // Additive — omit empty maps so the payload stays byte-identical (INV-3).
          ...(initialModelOverrides &&
          Object.keys(initialModelOverrides).length > 0
            ? { model_overrides: initialModelOverrides }
            : {}),
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
    [agents, pipelineType, initialModelOverrides, liveSelections, onClose],
  );

  const handleRemove = useCallback((agentId: string) => {
    if (getRole(agentId, pipelineType) !== "optional") return;
    onRemoveAgent?.(agentId);
  }, [onRemoveAgent, pipelineType]);

  const handleDragStart = useCallback((idx: number) => {
    if (getRole(agents[idx].id, pipelineType) === "locked") return;
    setDraggedIdx(idx);
  }, [agents, pipelineType]);

  const handleDragOver = useCallback((e: React.DragEvent, idx: number) => {
    e.preventDefault();
    if (getRole(agents[idx].id, pipelineType) === "locked") return;
    setDragOverIdx(idx);
  }, [agents, pipelineType]);

  const handleDrop = useCallback((idx: number) => {
    if (draggedIdx === null || draggedIdx === idx) { setDraggedIdx(null); setDragOverIdx(null); return; }
    if (getRole(agents[idx].id, pipelineType) === "locked") { setDraggedIdx(null); setDragOverIdx(null); return; }
    const updated = [...agents];
    const [moved] = updated.splice(draggedIdx, 1);
    updated.splice(idx, 0, moved);
    onReorder?.(updated);
    setDraggedIdx(null);
    setDragOverIdx(null);
  }, [draggedIdx, agents, onReorder, pipelineType]);

  const handleDragEnd = useCallback(() => { setDraggedIdx(null); setDragOverIdx(null); }, []);

  const pipelineLabel = PIPELINE_LABEL[pipelineType] || pipelineType;
  const defaultAgentIds = new Set(
    agents.filter(a => {
      const pipelinePrefixes: Record<string, string[]> = {
        user_stories: ["domain-analyst", "epic-architect", "story-estimator", "nfr-specialist", "backlog-reviewer", "backlog-compiler"],
        ppt: ["ppt-content-strategist", "ppt-slide-architect", "ppt-code-generator", "ppt-assembler"],
        prototype: ["requirements-analyst", "html-prototype-builder", "prototype-polisher", "prototype-finalizer"],
        app_builder: [
          "material-analyzer", "app-user-stories", "app-system-design", "app-security-architecture",
          "app-ux-design", "app-api-design", "app-database-design", "app-code-generator",
          "app-feature-implementation", "app-infra-generator", "app-code-compliance",
          "app-test-implementation", "app-test-compliance", "app-devops", "app-sdlc-governance",
        ],
        custom: [],
      };
      return (pipelinePrefixes[pipelineType] || []).includes(a.id);
    }).map(a => a.id)
  );
  const optionalCount = agents.filter(a => !defaultAgentIds.has(a.id) && getRole(a.id, pipelineType) === "optional").length;
  const maxOptional = pipelineType === "custom" ? 8 : 5;
  const slotsLeft = maxOptional - optionalCount;
  const allCells: Array<AgentDef | "add"> = [...agents, ...(canAddMore ? ["add" as const] : [])];
  const rows: Array<Array<AgentDef | "add">> = [];
  for (let i = 0; i < allCells.length; i += COLS) rows.push(allCells.slice(i, i + COLS));

  const totalAttached = attachedSkills.length + attachedHooks.length;

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
        >
          <motion.div className="absolute inset-0 bg-black/30 backdrop-blur-[2px]" onClick={onClose} />

          <motion.div
            initial={{ opacity: 0, y: 10, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 10, scale: 0.98 }}
            transition={{ duration: 0.18 }}
            className="relative w-full max-w-[780px] bg-white rounded-2xl shadow-2xl flex flex-col"
            style={{ maxHeight: "90vh" }}
          >
            {/* Header */}
            <div className="px-8 pt-6 pb-0 flex-shrink-0">
              <div className="flex items-start justify-between mb-1">
                <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-[0.18em]">Advanced</p>
                <button onClick={onClose} className="h-7 w-7 flex items-center justify-center rounded-lg text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-all">
                  <X className="h-4 w-4" />
                </button>
              </div>
              <h2 className="text-[20px] font-bold text-gray-900 mb-3">Workflow configuration</h2>

              {/* Tabs */}
              <div className="flex items-center gap-1 pb-0 border-b border-gray-100">
                <button
                  onClick={() => setActiveTab("agents")}
                  className={`flex items-center gap-1.5 px-4 py-2.5 text-[12px] font-semibold transition-colors border-b-2 -mb-px ${
                    activeTab === "agents"
                      ? "border-gray-900 text-gray-900"
                      : "border-transparent text-gray-400 hover:text-gray-700"
                  }`}
                >
                  <GripVertical className="h-3.5 w-3.5" />
                  Agents
                  <span className="text-[10px] font-medium text-gray-400 ml-0.5">({agents.length})</span>
                </button>
                <button
                  onClick={() => setActiveTab("skills-hooks")}
                  className={`flex items-center gap-1.5 px-4 py-2.5 text-[12px] font-semibold transition-colors border-b-2 -mb-px ${
                    activeTab === "skills-hooks"
                      ? "border-gray-900 text-gray-900"
                      : "border-transparent text-gray-400 hover:text-gray-700"
                  }`}
                >
                  <Puzzle className="h-3.5 w-3.5" />
                  Workflow
                  {totalAttached > 0 && (
                    <span className="text-[9px] font-bold px-1.5 py-0.5 rounded-full bg-gray-900 text-white ml-0.5">{totalAttached}</span>
                  )}
                </button>
              </div>
            </div>

            {/* Tab content */}
            {activeTab === "agents" ? (
              <>
                {/* Agents sub-header */}
                <div className="px-8 pt-3 pb-2 flex-shrink-0 flex items-center justify-between">
                  <div className="flex items-center gap-3 text-[10px] font-semibold text-gray-400 uppercase tracking-widest flex-wrap">
                    <span>{agents.length} agents · {pipelineLabel}</span>
                    <span className="flex items-center gap-1 text-gray-300"><Lock className="h-2.5 w-2.5" /> Core = locked</span>
                    <span className="text-gray-300">· Drag to reorder · × to remove</span>
                  </div>
                  <button onClick={() => setLibraryOpen(true)} className="text-[10px] font-semibold text-gray-400 hover:text-brand uppercase tracking-widest transition-colors flex-shrink-0 ml-4">
                    Browse agent library →
                  </button>
                </div>

                {/* Single scrollable body — flow grid + model picker + advanced + capabilities.
                    All four sections share one overflow-y-auto flex-1 region so they are
                    always reachable regardless of screen height (KAN-68 fix). */}
                <div className="flex-1 overflow-y-auto min-h-0">

                {/* Flow grid — capped to a responsive max-height so it never eats the
                    full available space and squeezes out the sections below. */}
                <div className="mx-6 mb-4 rounded-xl overflow-y-auto flex-shrink-0" style={{
                  maxHeight: "min(45vh, 240px)",
                  background: "#f7f6f3",
                  backgroundImage: "radial-gradient(#d4d0ca 1px, transparent 1px)",
                  backgroundSize: "20px 20px",
                }}>
                  <div className="p-4 space-y-2.5">
                    {rows.map((row, rowIdx) => (
                      <div key={rowIdx} className="flex items-stretch">
                        {row.map((cell, colIdx) => {
                          const globalIdx = rowIdx * COLS + colIdx;
                          const isLastInRow = colIdx === row.length - 1;
                          const isLastCell = globalIdx === allCells.length - 1;

                          if (cell === "add") {
                            return (
                              <div key="add" className="flex items-center">
                                {colIdx > 0 && (
                                  <div className="flex items-center w-7 flex-shrink-0">
                                    <div className="flex-1 border-t-2 border-dashed border-gray-300" />
                                    <ArrowRight className="h-3 w-3 text-gray-300 -ml-1" />
                                  </div>
                                )}
                                <button
                                  onClick={() => setLibraryOpen(true)}
                                  className="flex flex-col items-center justify-center gap-1 bg-white border-2 border-dashed border-gray-300 rounded-lg text-[10px] font-medium text-gray-400 hover:text-gray-700 hover:border-gray-400 hover:bg-gray-50 transition-all"
                                  style={{ width: "130px", height: "68px" }}
                                >
                                  <Plus className="h-3.5 w-3.5" />
                                  {slotsLeft > 0 ? `+ Add agent (${slotsLeft} left)` : "Limit reached"}
                                </button>
                              </div>
                            );
                          }

                          const agent = cell as AgentDef;
                          const role = getRole(agent.id, pipelineType);
                          const locked = role === "locked";
                          const optional = role === "optional";
                          const isDragging = draggedIdx === globalIdx;
                          const isDragOver = dragOverIdx === globalIdx;

                          return (
                            <div key={agent.id} className="flex items-center">
                              {colIdx > 0 && (
                                <div className="flex items-center w-7 flex-shrink-0">
                                  <div className="flex-1 border-t-2 border-dashed border-gray-300" />
                                  <ArrowRight className="h-3 w-3 text-gray-300 -ml-1" />
                                </div>
                              )}
                              <motion.div
                                initial={{ opacity: 0, scale: 0.96 }}
                                animate={{ opacity: isDragging ? 0.4 : 1, scale: isDragOver ? 1.02 : 1 }}
                                transition={{ delay: globalIdx * 0.03 }}
                                draggable={!locked}
                                onDragStart={() => handleDragStart(globalIdx)}
                                onDragOver={e => handleDragOver(e, globalIdx)}
                                onDrop={() => handleDrop(globalIdx)}
                                onDragEnd={handleDragEnd}
                                className={`group relative bg-white rounded-lg border px-3 py-2.5 shadow-sm transition-all ${
                                  isDragOver ? "border-brand shadow-md" :
                                  locked ? "border-gray-200 opacity-80" :
                                  "border-gray-200 hover:border-gray-300 hover:shadow-md"
                                } ${!locked ? "cursor-grab active:cursor-grabbing" : ""}`}
                                style={{ width: "130px" }}
                              >
                                <div className="flex items-center justify-between mb-1.5">
                                  <div>
                                    {locked ? <Lock className="h-2.5 w-2.5 text-gray-300" /> : <GripVertical className="h-3 w-3 text-gray-400" />}
                                  </div>
                                  <div className="flex items-center gap-1">
                                    {locked && <span className="text-[7px] font-semibold text-gray-400 bg-gray-100 px-1.5 py-0.5 rounded uppercase tracking-wide">Core</span>}
                                    {role === "required" && <span className="text-[7px] font-semibold text-gray-400 bg-gray-100 px-1.5 py-0.5 rounded uppercase tracking-wide">Required</span>}
                                <button
                                      onClick={e => { e.stopPropagation(); setCapAgent({ agent, index: globalIdx }); }}
                                      className="flex items-center justify-center w-5 h-5 rounded bg-gray-50 border border-gray-200 hover:bg-gray-100 transition-colors"
                                      title="View capabilities & configure"
                                    >
                                      <Info className="h-3 w-3 text-gray-400" />
                                    </button>
                                    {optional && (
                                      <button
                                        onClick={e => { e.stopPropagation(); handleRemove(agent.id); }}
                                        className="flex items-center justify-center w-5 h-5 rounded bg-red-50 border border-red-200 hover:bg-red-100 transition-colors"
                                        title="Remove agent"
                                      >
                                        <X className="h-3 w-3 text-red-500" />
                                      </button>
                                    )}
                                  </div>
                                </div>
                                <div className="w-6 h-6 rounded-md bg-gray-100 border border-gray-200 flex items-center justify-center mb-2">
                                  <span className="text-[9px] font-bold text-gray-500 select-none">
                                    {agent.name.split(" ").map(w => w[0]).slice(0, 2).join("")}
                                  </span>
                                </div>
                                <p className="text-[11px] font-semibold text-gray-900 leading-snug mb-0.5 line-clamp-2">{agent.name}</p>
                                <p className="text-[8px] font-semibold text-gray-400 uppercase tracking-wider">{pipelineLabel}</p>
                              </motion.div>
                              {isLastInRow && !isLastCell && (
                                <div className="w-4 flex-shrink-0 ml-1 border-t-2 border-dashed border-gray-300" />
                              )}
                            </div>
                          );
                        })}
                      </div>
                    ))}
                  </div>
                </div>

                {/* ISS-014 (MODEL-03): per-agent model picker, relocated here
                    from the deleted WorkflowComposer. Populated from the live
                    /api/capabilities model catalog (user_allowed only). A
                    selection threads up via onModelOverridesChange →
                    IdeaInputPage extraParams → run_pipeline model_overrides. */}

                {/* End of shared scroll container (KAN-68 fix) */}
                </div>
              </>
            ) : (
              /* Workflow tab: Skills, Hooks, and Capabilities */
              <div className="flex-1 overflow-y-auto min-h-0">
                <SkillsHooksTab pipelineType={pipelineType} />
                {/* Capabilities palette at the bottom of the Workflow tab */}
                <div className="mx-5 mb-5 px-1">
                  <CapabilityPaletteSection
                    declaredCapabilities={declaredCapabilities}
                  />
                </div>
              </div>
            )}

            {/* Footer */}
            <div className="px-8 pb-6 flex-shrink-0 flex items-center justify-end gap-3 border-t border-gray-100 pt-4">
              {saveError && (
                <span role="alert" className="text-[11px] text-status-failed mr-auto">
                  {saveError}
                </span>
              )}
              <button onClick={onClose} className="px-5 py-2.5 rounded-xl border border-line-border text-[12px] font-medium text-ink-600 hover:bg-surface-warm transition-colors">
                Cancel
              </button>
              <button
                onClick={() => { setSaveError(null); setSaveModalOpen(true); }}
                className="px-5 py-2.5 rounded-xl bg-ink-900 text-[12px] font-semibold text-surface-white hover:bg-ink-800 transition-colors"
              >
                Save workflow
              </button>
            </div>
          </motion.div>

          {/* Save-to-catalogue modal (REUSE — owner-scoped createUserWorkflow;
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
            isOpen={libraryOpen}
            onClose={() => setLibraryOpen(false)}
            onAddAgent={onAddAgent}
            currentPipelineType={pipelineType}
            canAddMore={canAddMore}
            existingAgentIds={agents.map(a => a.id)}
          />

          <AnimatePresence>
            {capAgent && (
              <AgentCapabilitiesModal
                agent={capAgent.agent}
                agentIndex={capAgent.index}
                onClose={() => setCapAgent(null)}
                onSelectionsChange={handleSelectionsChange}
                initialSelections={initialSelections}
              />
            )}
          </AnimatePresence>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
