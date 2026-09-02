"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { X, Search, Info } from "lucide-react";
import type { AgentDef } from "@/types/index";
import { AgentCapabilitiesModal } from "./AgentsPopup";
import { useAgentLibrary } from "@/hooks/useAgentLibrary";
import { getWorkflowTypeIcon, getPrimaryPipelineType, agentMatchesPipelineType } from "@/lib/workflowIcons";
import { useAppSelector } from "@/store/hooks";
import { isCustomAgentTemplate } from "@/store/api/userWorkflows";

interface AgentLibraryProps {
  isOpen: boolean;
  onClose: () => void;
  onAddAgent?: (agent: AgentDef) => void;
  /**
   * When provided, every card offers a SECOND action: "+ Sub-agent", which
   * nests the picked agent under `subAgentParentName`'s node instead of
   * appending it to the top-level chain. Any library agent can be a sub-agent —
   * the distinction is where it lands in the tree, not what it is.
   */
  onAddAsSubAgent?: (agent: AgentDef) => void;
  /** Display name of the node a sub-agent would nest under (header context). */
  subAgentParentName?: string;
  /**
   * Spec 012 — write-through for the Skills tab in the per-agent drawer. When
   * supplied the drawer's skills picker is LIVE (the composer stages each change
   * onto the step at add time); when omitted it renders read-only — a catalog
   * agent with nowhere to write back. See AgentCapabilitiesModal.onSkillsChange.
   */
  onSkillsChange?: (agentId: string, skills: string[]) => void;
  currentPipelineType?: string;
  canAddMore?: boolean;
  existingAgentIds?: string[];
  /**
   * Offer the blank `custom-agent` template? Default true (the composer canvas,
   * where a user-defined step is the whole point).
   *
   * The LaunchWizard passes false. A step added there ends up in a run of a
   * BUILT-IN — either directly or through a saved override — and a blank
   * template compiles to a dynamic `custom-agent:<instance_id>` id that has no
   * AGENT.md on disk and is absent from the static roster the launch's
   * `agent_ids` allow-list is built from. Such a run is rejected at ingress with
   * `invalid_agent_ids` (reproduced live on a ppt override carrying one), so
   * offering the template there advertises a step that can be saved and drawn
   * but never run. An override may only reuse agents that exist as files.
   */
  allowCustomAgentTemplate?: boolean;
}

const CATEGORIES_FALLBACK = [
  { id: "all", label: "All" },
  { id: "user_stories", label: "User Stories" },
  { id: "ppt", label: "Presentation" },
  { id: "prototype", label: "Prototype" },
  { id: "app_builder", label: "App Builder" },
  { id: "mulesoft_to_springboot", label: "Mulesoft → Spring Boot" },
  { id: "dotnet_to_azure", label: ".NET → Azure" },
  { id: "custom", label: "Custom" },
];

const HIDDEN_FROM_CUSTOM = new Set([
  "ppt-assembler", "backlog-compiler", "prototype-finalizer", "app-sdlc-governance",
  "ppt-content-strategist", "domain-analyst", "requirements-analyst", "material-analyzer",
]);

const BETA_WORKFLOWS = new Set(["user_stories_revision", "ppt_revision", "prototype_revision", "app_builder_revision", "mulesoft_to_springboot", "dotnet_to_azure", "sample_brownfield", "sample_fanout", "sample_wave", "reverse_engineer"]);

// Monochrome icon — no colors, just gray
function getInitials(name: string): string {
  const words = name.replace(/\s+agent$/i, "").split(" ");
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[1][0]).toUpperCase();
}

export function AgentLibrary({
  isOpen, onClose, onAddAgent, onAddAsSubAgent, subAgentParentName,
  onSkillsChange, currentPipelineType, canAddMore = true, existingAgentIds = [],
  allowCustomAgentTemplate = true,
}: AgentLibraryProps) {
  // Fetch agents from Redux (populated by GET /api/agents/library via listenerMiddleware)
  const { allAgents: ALL_AGENTS } = useAgentLibrary();
  const workflows = useAppSelector((state) => state.global.workflows);
  const [searchQuery, setSearchQuery] = useState("");
  // ISS-420 / ISS-421: `currentPipelineType` can be a sub-pipeline type that
  // CATEGORIES_FALLBACK does not know (e.g. "migration"), causing `activeCategory`
  // to default to an unrecognised value — no tab highlights and the panel opens on
  // "No agents found" because nothing in CATEGORIES_FALLBACK matches it. Validate
  // against the static fallback list before accepting it as a default; unrecognised
  // values fall back to "all". "all" and "custom" are always valid.
  const KNOWN_CATEGORY_IDS = new Set(CATEGORIES_FALLBACK.map(c => c.id));
  const [activeCategory, setActiveCategory] = useState(
    currentPipelineType && KNOWN_CATEGORY_IDS.has(currentPipelineType)
      ? currentPipelineType
      : "all",
  );

  // Build CATEGORIES dynamically from workflows, using short_name when available
  const CATEGORIES = [
    { id: "all", label: "All" },
    ...CATEGORIES_FALLBACK.slice(1, -1).map(cat => {
      const workflow = workflows.find(w => w.id === cat.id);
      return {
        id: cat.id,
        label: workflow?.short_name || workflow?.display_name || cat.label,
      };
    }),
    { id: "custom", label: "Custom" },
  ];
  const [capAgent, setCapAgent] = useState<{ agent: AgentDef; index: number } | null>(null);

  // Use only existingAgentIds from parent — no local tracking
  // This ensures removed agents reappear in the library
  const categoryAgents = ALL_AGENTS.filter((agent) => {
    const matchesCategory = activeCategory === "all" || agentMatchesPipelineType(agent.pipeline_type, activeCategory);
    const matchesSearch =
      !searchQuery ||
      agent.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      agent.description.toLowerCase().includes(searchQuery.toLowerCase()) ||
      agent.role.toLowerCase().includes(searchQuery.toLowerCase());
    const notHidden = currentPipelineType !== "custom" || !HIDDEN_FROM_CUSTOM.has(agent.id);
    const templateAllowed = allowCustomAgentTemplate || !isCustomAgentTemplate(agent);
    return matchesCategory && matchesSearch && notHidden && templateAllowed;
  });

  const filteredAgents = categoryAgents.filter((agent) => {
    // The blank custom-agent template is reusable N times, so "already added"
    // must never hide it — every add mints a new instance id.
    const notAlreadyAdded =
      isCustomAgentTemplate(agent) || !existingAgentIds.includes(agent.id);
    return notAlreadyAdded;
  }).sort((a, b) => {
    // Sort beta workflows to the end
    const aPt = getPrimaryPipelineType(a.pipeline_type);
    const bPt = getPrimaryPipelineType(b.pipeline_type);
    const aBeta = BETA_WORKFLOWS.has(aPt) ? 1 : 0;
    const bBeta = BETA_WORKFLOWS.has(bPt) ? 1 : 0;
    if (aBeta !== bBeta) return aBeta - bBeta;
    return aPt.localeCompare(bPt) || a.order - b.order;
  });

  // A category can be empty because it holds no agents at all, or because every
  // agent it holds is already on the canvas — the default tab is the current
  // pipeline's own, where the second case is the norm (ISS-311). The generic
  // copy reads as "this category has none", so name the real reason.
  const allAlreadyAdded = filteredAgents.length === 0 && categoryAgents.length > 0;
  const activeCategoryLabel = CATEGORIES.find((c) => c.id === activeCategory && c.id !== "all")?.label;
  const emptyMessage = allAlreadyAdded
    ? `All ${activeCategoryLabel ? `${activeCategoryLabel} ` : ""}agents are already on your canvas`
    : "No agents found";

  const categoryCounts: Record<string, number> = { all: 0 };
  ALL_AGENTS.forEach((a) => {
    // Mirror the list's own template gate, or the Custom badge counts a card
    // the user cannot see.
    if (!allowCustomAgentTemplate && isCustomAgentTemplate(a)) return;
    if (isCustomAgentTemplate(a) || !existingAgentIds.includes(a.id)) {
      categoryCounts.all = (categoryCounts.all || 0) + 1;
      const pt = getPrimaryPipelineType(a.pipeline_type);
      categoryCounts[pt] = (categoryCounts[pt] || 0) + 1;
    }
  });

  const handleAddSub = (agent: AgentDef) => {
    onAddAsSubAgent?.(agent);
    onClose();
  };

  const handleAdd = (agent: AgentDef) => {
    if (!canAddMore) return;
    onAddAgent?.(agent);
    onClose(); // Close library so user sees the agent added to the flow
  };

  return (
    <>
    <AnimatePresence>
      {isOpen && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-[70] flex items-center justify-center p-6"
        >
          {/* Backdrop */}
          <motion.div
            className="absolute inset-0 bg-scrim backdrop-blur-[2px]"
            onClick={onClose}
          />

          {/* Modal */}
          <motion.div
            initial={{ opacity: 0, scale: 0.97, y: 12 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.97, y: 12 }}
            transition={{ duration: 0.18 }}
            className="relative w-full max-w-[820px] rounded-2xl shadow-2xl overflow-hidden flex"
            style={{ height: "640px", background: "var(--surface-warm)" }}          >
            {/* Left sidebar — categories */}
            <div className="w-[180px] flex-shrink-0 border-r border-line-divider flex flex-col bg-surface-white">
              <div className="px-5 pt-6 pb-4 border-b border-line-divider">
                <h2 className="text-[16px] font-bold text-ink-900">Add agent</h2>
              </div>
              <nav className="flex-1 overflow-y-auto py-2">
                {CATEGORIES.map((cat) => {
                  const count = categoryCounts[cat.id] || 0;
                  const isActive = activeCategory === cat.id;
                  const IconComponent = cat.id !== "all" ? getWorkflowTypeIcon(cat.id) : null;
                  return (
                    <button
                      key={cat.id}
                      onClick={() => setActiveCategory(cat.id)}
                      className={`w-full flex items-center gap-2.5 px-5 py-2 text-[13px] transition-colors text-left ${
                        isActive
                          ? "bg-line-faint-row text-ink-900 font-medium"
                          : "text-ink-500 hover:text-ink-900 hover:bg-surface-warm"
                      }`}
                    >
                      {IconComponent && <IconComponent className="h-3.5 w-3.5 flex-shrink-0" />}
                      <span>{cat.label}</span>
                    </button>
                  );
                })}
              </nav>
            </div>

            {/* Right content */}
            <div className="flex-1 flex flex-col min-w-0">
              {/* Header */}
              <div className="flex items-center justify-between px-6 pt-5 pb-4 border-b border-line-divider flex-shrink-0 bg-surface-white">
                <div className="relative flex-1 max-w-xs">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-ink-400" />
                  <input
                    type="text"
                    aria-label="Search agents"
                    name="agent-search"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Search agents..."
                    className="w-full pl-9 pr-4 py-2 text-[12px] bg-surface-warm border border-line-control rounded-lg focus:outline-none focus:border-ink-400 transition-colors placeholder-ink-400"
                  />
                </div>
                <button
                  onClick={onClose}
                  className="h-8 w-8 flex items-center justify-center rounded-lg text-ink-400 hover:text-ink-700 hover:bg-surface-warm transition-all ml-4"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>

              {/* Agent grid */}
              <div className="flex-1 overflow-y-auto p-4" style={{ background: "var(--surface-warm)" }}>
                {filteredAgents.length === 0 ? (
                  <div className="flex items-center justify-center h-full">
                    <p className="text-[13px] text-ink-400">{emptyMessage}</p>
                  </div>
                ) : (
                  <div className="grid grid-cols-2 gap-2">
                    {filteredAgents.map((agent, idx) => {
                      const initials = getInitials(agent.name);
                      const pt = getPrimaryPipelineType(agent.pipeline_type);
                      const categoryLabel = CATEGORIES.find(c => c.id === pt)?.label?.toUpperCase() || pt.toUpperCase();
                      const isBeta = BETA_WORKFLOWS.has(pt);
                      const WorkflowIconComponent = getWorkflowTypeIcon(pt);

                      return (
                        <motion.div
                          key={`${pt}-${agent.id}`}
                          data-testid={`library-card-${agent.id}`}
                          initial={{ opacity: 0 }}
                          animate={{ opacity: 1 }}
                          transition={{ delay: idx * 0.02 }}
                          className={`relative flex flex-col rounded-xl border px-4 py-3.5 transition-all group ${
                            isBeta || !canAddMore
                              ? "border-line-divider bg-surface-warm opacity-60"
                              : "border-line-control bg-surface-warm hover:bg-surface-white hover:border-line-faint hover:shadow-sm"
                          }`}
                        >
                          {/* ℹ️ button — top right corner */}
                          <button
                            onClick={(e) => { e.stopPropagation(); !isBeta && setCapAgent({ agent, index: idx }); }}
                            disabled={isBeta}
                            className={`absolute top-3 right-3 flex items-center justify-center w-6 h-6 rounded-md border transition-colors ${
                              isBeta
                                ? "bg-surface-warm border-line-divider cursor-not-allowed"
                                : "bg-surface-white border-line-control hover:bg-line-faint-row"
                            }`}
                            title={isBeta ? "Coming soon" : "View capabilities"}
                          >
                            <Info className={`h-3 w-3 ${isBeta ? "text-ink-300" : "text-ink-400"}`} />
                          </button>

                          {/* Icon + name */}
                          <div className="flex items-center gap-3 mb-2 pr-8">
                            <div className="w-9 h-9 rounded-lg bg-brand-fill border border-brand-border flex items-center justify-center flex-shrink-0">
                              <WorkflowIconComponent className="h-4.5 w-4.5 text-brand" />
                            </div>
                            <div className="flex-1 min-w-0">
                              <p className={`text-[13px] font-semibold leading-tight ${isBeta ? "text-ink-500" : "text-ink-900"}`}>
                                {agent.name}
                              </p>
                              <p className="text-[10px] font-semibold text-ink-400 uppercase tracking-wide mt-0.5">
                                {categoryLabel}
                              </p>
                            </div>
                          </div>

                          {/* Description */}
                          <p className={`text-[11px] leading-relaxed line-clamp-2 flex-1 mb-3 ${isBeta ? "text-ink-400" : "text-ink-500"}`}>
                            {agent.description}
                          </p>

                          {/* Actions — bottom right. Two when a sub-agent
                              parent is in play, so the same catalog serves both
                              placements without a second dialog. */}
                          <div className="flex justify-end gap-1.5">
                            <button
                              onClick={() => canAddMore && !isBeta && handleAdd(agent)}
                              disabled={!canAddMore || isBeta}
                              className={`flex items-center gap-1 px-3 py-1.5 rounded-lg border transition-colors text-[11px] font-semibold ${
                                isBeta || !canAddMore
                                  ? "bg-surface-warm border-line-divider text-ink-300 cursor-not-allowed"
                                  : "bg-line-faint-row border-line-control text-ink-600 hover:bg-line-control cursor-pointer"
                              }`}
                              title={isBeta ? "Coming soon" : "Add agent"}
                            >
                              {isBeta ? "Coming Soon" : "+ Add"}
                            </button>
                            {onAddAsSubAgent && !isBeta && (
                              <button
                                onClick={() => handleAddSub(agent)}
                                title={
                                  subAgentParentName
                                    ? `Add as sub-agent of ${subAgentParentName}`
                                    : "Add as sub-agent"
                                }
                                data-testid={`library-add-sub-${agent.id}`}
                                className="flex items-center gap-1 px-3 py-1.5 rounded-lg border border-brand/25 bg-brand/5 text-brand hover:bg-brand/10 transition-colors text-[11px] font-semibold cursor-pointer"
                              >
                                + Sub-agent
                              </button>
                            )}
                          </div>
                        </motion.div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>

    {/* Agent capabilities modal */}
    <AnimatePresence>
      {capAgent && (
        <AgentCapabilitiesModal
          agent={capAgent.agent}
          agentIndex={capAgent.index}
          onClose={() => setCapAgent(null)}
          onSkillsChange={onSkillsChange}
        />
      )}
    </AnimatePresence>
    </>
  );
}
