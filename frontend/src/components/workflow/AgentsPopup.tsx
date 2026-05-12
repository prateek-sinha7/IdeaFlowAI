"use client";

import { useCallback, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { X, Plus, ArrowRight, Lock, GripVertical } from "lucide-react";
import { AgentLibrary } from "./AgentLibrary";
import type { AgentDef, WorkflowType } from "@/types/index";

interface AgentsPopupProps {
  isOpen: boolean;
  onClose: () => void;
  agents: AgentDef[];
  pipelineType: WorkflowType;
  onAddAgent?: (agent: AgentDef) => void;
  onRemoveAgent?: (agentId: string) => void;
  onReorder?: (agents: AgentDef[]) => void;
  canAddMore?: boolean;
}

const LOCKED_AGENT_IDS = new Set([
  "domain-analyst", "backlog-compiler",
  "ppt-content-strategist", "ppt-assembler",
  "requirements-analyst", "prototype-finalizer",
  // App Builder: architecture (first) and SDLC governance (last) are locked.
  "material-analyzer", "app-sdlc-governance",
  "repo-scanner", "documentation-generator",
  // Migration: inventory (first) and SDLC governance (last) are locked.
  "mulesoft-inventory", "mulesoft-sdlc-governance",
  "dotnet-inventory", "dotnet-sdlc-governance",
]);

const REQUIRED_AGENT_IDS = new Set([
  "epic-architect", "story-estimator", "nfr-specialist", "backlog-reviewer",
  "ppt-slide-architect", "ppt-code-generator",
  "html-prototype-builder", "prototype-polisher",
  // App Builder middle agents — required but reorderable.
  "app-user-stories", "app-system-design", "app-security-architecture",
  "app-ux-design", "app-api-design", "app-database-design",
  "app-code-generator", "app-feature-implementation", "app-infra-generator",
  "app-code-compliance", "app-test-implementation",
  "app-test-compliance", "app-devops",
  "deep-analyzer", "modernization-planner",
  // Migration: middle agents (requirements → design → implementation →
  // gates → validation) are required but reorderable. Inventory and
  // governance are locked above.
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
  // An agent is only locked/required if it belongs to the current pipeline
  // Agents from other pipelines added as extras are always optional (removable)
  const isNativeLocked = LOCKED_AGENT_IDS.has(agentId);
  const isNativeRequired = REQUIRED_AGENT_IDS.has(agentId);

  if (!isNativeLocked && !isNativeRequired) return "optional";

  // Check if this agent actually belongs to the current pipeline type
  // by checking if its ID prefix matches the pipeline
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
      "mulesoft-inventory", "mulesoft-user-stories",
      "mulesoft-decomposition", "mulesoft-security-architecture",
      "mulesoft-springboot-scaffold", "mulesoft-feature-coding",
      "mulesoft-dataweave-translator", "mulesoft-aws-infra",
      "mulesoft-code-compliance", "mulesoft-test-implementation",
      "mulesoft-test-compliance", "mulesoft-validation",
      "mulesoft-sdlc-governance",
    ],
    dotnet_to_azure: [
      "dotnet-inventory", "dotnet-user-stories",
      "dotnet-azure-target-mapping", "dotnet-security-architecture",
      "dotnet-modernization", "dotnet-feature-coding",
      "dotnet-azure-bicep", "dotnet-azure-ai",
      "dotnet-code-compliance", "dotnet-test-implementation",
      "dotnet-test-compliance", "dotnet-validation",
      "dotnet-sdlc-governance",
    ],
    custom: [],
  };

  const nativeAgents = pipelinePrefixes[pipelineType] || [];
  const isNativeToThisPipeline = nativeAgents.includes(agentId);

  if (!isNativeToThisPipeline) return "optional"; // cross-pipeline agent = always removable

  if (isNativeLocked) return "locked";
  if (isNativeRequired) return "required";
  return "optional";
}

const PIPELINE_LABEL: Record<string, string> = {
  user_stories: "User Stories",
  ppt: "Presentation",
  prototype: "Prototype",
  app_builder: "App Builder",
  custom: "Custom",
  mulesoft_to_springboot: "Mulesoft → Spring Boot",
  dotnet_to_azure: ".NET → Azure",
};

const COLS = 3;

export function AgentsPopup({
  isOpen, onClose, agents, pipelineType,
  onAddAgent, onRemoveAgent, onReorder, canAddMore = true,
}: AgentsPopupProps) {
  const [libraryOpen, setLibraryOpen] = useState(false);
  const [draggedIdx, setDraggedIdx] = useState<number | null>(null);
  const [dragOverIdx, setDragOverIdx] = useState<number | null>(null);

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
      "material-analyzer", "app-user-stories", "app-system-design",
      "app-security-architecture", "app-ux-design", "app-api-design",
      "app-database-design", "app-code-generator", "app-feature-implementation",
      "app-infra-generator", "app-code-compliance", "app-test-implementation",
      "app-test-compliance", "app-devops", "app-sdlc-governance",
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
  for (let i = 0; i < allCells.length; i += COLS) {
    rows.push(allCells.slice(i, i + COLS));
  }

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
        >
          <motion.div
            className="absolute inset-0 bg-black/30 backdrop-blur-[2px]"
            onClick={onClose}
          />

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
              <h2 className="text-[20px] font-bold text-gray-900 mb-3">Workflow agents</h2>
              <div className="flex items-center justify-between pb-4 border-b border-gray-100">
                <div className="flex items-center gap-3 text-[10px] font-semibold text-gray-400 uppercase tracking-widest flex-wrap">
                  <span>{agents.length} agents · {pipelineLabel}</span>
                  <span className="flex items-center gap-1 text-gray-300"><Lock className="h-2.5 w-2.5" /> Core = locked</span>
                  <span className="text-gray-300">· Drag to reorder · × to remove</span>
                </div>
                <button onClick={() => setLibraryOpen(true)} className="text-[10px] font-semibold text-gray-400 hover:text-[#1B2A4A] uppercase tracking-widest transition-colors flex-shrink-0 ml-4">
                  Browse agent library →
                </button>
              </div>
            </div>

            {/* Flow grid canvas */}
            <div className="mx-6 my-4 rounded-xl overflow-y-auto flex-1" style={{
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
                            onDragOver={(e) => handleDragOver(e, globalIdx)}
                            onDrop={() => handleDrop(globalIdx)}
                            onDragEnd={handleDragEnd}
                            className={`group relative bg-white rounded-lg border px-3 py-2.5 shadow-sm transition-all ${
                              isDragOver ? "border-[#1B2A4A] shadow-md" :
                              locked ? "border-gray-200 opacity-80" :
                              "border-gray-200 hover:border-gray-300 hover:shadow-md"
                            } ${!locked ? "cursor-grab active:cursor-grabbing" : ""}`}
                            style={{ width: "130px" }}
                          >
                            {/* Top row: drag/lock + role badge + remove */}
                            <div className="flex items-center justify-between mb-1.5">
                              <div>
                                {locked
                                  ? <Lock className="h-2.5 w-2.5 text-gray-300" />
                                  : <GripVertical className="h-3 w-3 text-gray-400" />
                                }
                              </div>
                              <div className="flex items-center gap-1">
                                {locked && (
                                  <span className="text-[7px] font-semibold text-gray-400 bg-gray-100 px-1.5 py-0.5 rounded uppercase tracking-wide">Core</span>
                                )}
                                {role === "required" && (
                                  <span className="text-[7px] font-semibold text-gray-400 bg-gray-100 px-1.5 py-0.5 rounded uppercase tracking-wide">Required</span>
                                )}
                                {optional && (
                                  <button
                                    onClick={(e) => { e.stopPropagation(); handleRemove(agent.id); }}
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

                            <p className="text-[11px] font-semibold text-gray-900 leading-snug mb-0.5 line-clamp-2">
                              {agent.name}
                            </p>
                            <p className="text-[8px] font-semibold text-gray-400 uppercase tracking-wider">
                              {pipelineLabel}
                            </p>
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

            {/* Footer */}
            <div className="px-8 pb-6 flex-shrink-0 flex items-center justify-end gap-3">
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
            existingAgentIds={agents.map((a) => a.id)}
          />
        </motion.div>
      )}
    </AnimatePresence>
  );
}
