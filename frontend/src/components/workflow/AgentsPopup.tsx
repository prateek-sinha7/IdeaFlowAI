"use client";

import { useCallback, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import {
  X, Plus, ArrowRight, Lock, GripVertical, Info,
  Clock, Zap, BookMarked, CheckCircle2, ChevronRight,
  Puzzle, Webhook, Search, Check,
} from "lucide-react";
import { AgentLibrary } from "./AgentLibrary";
import { AgentModelPicker } from "./AgentModelPicker";
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
    ppt: ["ppt-content-strategist", "ppt-slide-architect", "ppt-code-generator", "ppt-assembler"],
    prototype: ["requirements-analyst", "html-prototype-builder", "prototype-polisher", "prototype-finalizer"],
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
  { bg: "#E8EDF5", text: "#1B2A4A" }, { bg: "#F0EDE8", text: "#5C4A2A" },
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


// ─── AgentCapabilitiesModal ───────────────────────────────────────────────────

export function AgentCapabilitiesModal({
  agent, agentIndex, onClose,
  attachedSkills: propSkills, attachedHooks: propHooks,
  onAttachSkill: propAttachSkill, onAttachHook: propAttachHook,
}: {
  agent: AgentDef;
  agentIndex: number;
  onClose: () => void;
  attachedSkills?: AttachedSkill[];
  attachedHooks?: AttachedHook[];
  onAttachSkill?: (skill: AttachedSkill) => void;
  onAttachHook?: (hook: AttachedHook) => void;
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
          {/* Capabilities */}
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

          {/* Suggested Skills */}
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
                          attachHook({ id: hook.id, name: hook.name, source: hook.source, sourceLabel: hook.sourceLabel, event: hook.event, trigger: hook.trigger });
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


// ─── AgentsPopup (main) ───────────────────────────────────────────────────────

const COLS = 3;

export function AgentsPopup({
  isOpen, onClose, agents, pipelineType,
  onAddAgent, onRemoveAgent, onReorder, canAddMore = true,
  onModelOverridesChange,
}: AgentsPopupProps) {
  const { attachedSkills, attachedHooks } = useSkillsHooks();
  const [libraryOpen, setLibraryOpen] = useState(false);
  const [draggedIdx, setDraggedIdx] = useState<number | null>(null);
  const [dragOverIdx, setDragOverIdx] = useState<number | null>(null);
  const [capAgent, setCapAgent] = useState<{ agent: AgentDef; index: number } | null>(null);
  const [activeTab, setActiveTab] = useState<"agents" | "skills-hooks">("agents");

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
                  Skills & Hooks
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
                  <button onClick={() => setLibraryOpen(true)} className="text-[10px] font-semibold text-gray-400 hover:text-[#1B2A4A] uppercase tracking-widest transition-colors flex-shrink-0 ml-4">
                    Browse agent library →
                  </button>
                </div>

                {/* Flow grid */}
                <div className="mx-6 mb-4 rounded-xl overflow-y-auto flex-1" style={{
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
                                  isDragOver ? "border-[#1B2A4A] shadow-md" :
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
                                      title="View capabilities"
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
                <div className="mx-6 mb-4 px-1 flex-shrink-0">
                  <AgentModelPicker
                    agents={agents.map((a) => ({ id: a.id, name: a.name }))}
                    onChange={onModelOverridesChange}
                  />
                </div>
              </>
            ) : (
              <SkillsHooksTab pipelineType={pipelineType} />
            )}

            {/* Footer */}
            <div className="px-8 pb-6 flex-shrink-0 flex items-center justify-end gap-3 border-t border-gray-100 pt-4">
              <button onClick={onClose} className="px-5 py-2.5 rounded-xl border border-gray-200 text-[12px] font-medium text-gray-600 hover:bg-gray-50 transition-colors">
                Cancel
              </button>
              <button onClick={onClose} className="px-5 py-2.5 rounded-xl bg-gray-900 text-[12px] font-semibold text-white hover:bg-gray-800 transition-colors">
                Save changes
              </button>
            </div>
          </motion.div>

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
              />
            )}
          </AnimatePresence>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
