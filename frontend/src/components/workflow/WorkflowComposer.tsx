"use client";

import { useState, useCallback } from "react";
import { Plus, X, Play, AlertCircle, CheckCircle2, GripVertical } from "lucide-react";
import type { ValidationIssue, WaveGroup } from "@/types/index";
import { CapabilityPalette } from "./CapabilityPalette";
import { AgentModelPicker } from "./AgentModelPicker";
import { ValidatorIssuePanel } from "../results/ValidatorIssuePanel";
import { WaveTreePanel } from "./WaveTreePanel";

// Available agents for custom workflow composition
// In a full implementation this would be fetched from /api/agents
const AVAILABLE_AGENTS = [
  // Spec Kit Agents
  { id: "constitution-agent", name: "Constitution Agent", role: "Governance Principles Author", category: "Spec Kit" },
  { id: "specify-agent", name: "Specify Agent", role: "Feature Specification Author", category: "Spec Kit" },
  { id: "clarify-agent", name: "Clarify Agent", role: "Ambiguity Resolver", category: "Spec Kit" },
  { id: "research-agent", name: "Research Agent", role: "Technical Decision Researcher", category: "Spec Kit" },
  { id: "plan-agent", name: "Plan Agent", role: "Implementation Plan Author", category: "Spec Kit" },
  { id: "tasks-agent", name: "Tasks Agent", role: "Implementation Task Generator", category: "Spec Kit" },
  { id: "analyze-agent", name: "Analyze Agent", role: "Cross-Artifact Consistency Analyzer", category: "Spec Kit" },
  // Custom utility agents
  { id: "market-research-agent", name: "Market Research", role: "Market Research Analyst", category: "Custom" },
  { id: "swot-analyst", name: "SWOT Analyst", role: "Strategic Analysis", category: "Custom" },
  { id: "roadmap-planner", name: "Roadmap Planner", role: "Product Roadmap Planning", category: "Custom" },
  { id: "security-auditor", name: "Security Auditor", role: "Security Review", category: "Custom" },
  { id: "test-case-generator", name: "Test Case Generator", role: "Test Planning", category: "Custom" },
  { id: "performance-optimizer", name: "Performance Optimizer", role: "Performance Analysis", category: "Custom" },
  { id: "documentation-agent", name: "Documentation Agent", role: "Technical Writing", category: "Custom" },
  { id: "report-generator", name: "Report Generator", role: "Report Compilation", category: "Custom" },
];

const MAX_AGENTS = 50;

interface WorkflowComposerProps {
  /** Called when the user submits the composed workflow */
  onSubmit: (agentIds: string[], brief: string) => void;
  /** Whether a pipeline is currently running */
  isRunning?: boolean;
  /**
   * Per-agent model overrides selected in the AgentModelPicker (agentId ->
   * modelId). Reported upward so the caller feeds the run's model_overrides
   * path. Additive — omit to ignore per-agent model selection.
   */
  onModelOverridesChange?: (modelOverrides: Record<string, string>) => void;
  /**
   * Live validator/issue feed parsed from the run's `validator_result` /
   * `validation_warning` WS events (API-03). Additive — defaults to empty.
   */
  validatorIssues?: ValidationIssue[];
  /**
   * Live wave/subagent tree assembled from the run's `wave_*` / `subagent_*`
   * lifecycle events (Phase 12 / §22). The parent's WS handler routes the events
   * into this list (deduped by `event_id`). Additive — defaults to empty (an
   * existing non-wave workflow renders an empty tree).
   */
  waves?: WaveGroup[];
}

/**
 * T065a — Custom Workflow Composition UI (FR-013).
 *
 * Allows users to compose arbitrary agent DAGs (1–50 agents) from the arsenal.
 * The Deep_Planner_Agent is automatically prepended by the engine and does NOT
 * count toward the 1–50 agent limit.
 *
 * Features:
 * - Searchable agent selector
 * - Ordered list (drag-to-reorder via up/down buttons)
 * - Submit button that sends run_pipeline with the composed agent list
 * - Shows workflow_validated result (green/red per edge) before allowing submission
 */
export function WorkflowComposer({
  onSubmit,
  isRunning,
  onModelOverridesChange,
  validatorIssues = [],
  waves = [],
}: WorkflowComposerProps) {
  const [selectedAgents, setSelectedAgents] = useState<string[]>([]);
  const [brief, setBrief] = useState("");
  const [search, setSearch] = useState("");
  const [error, setError] = useState<string | null>(null);

  const filteredAgents = AVAILABLE_AGENTS.filter(
    (a) =>
      !selectedAgents.includes(a.id) &&
      (a.name.toLowerCase().includes(search.toLowerCase()) ||
        a.role.toLowerCase().includes(search.toLowerCase()) ||
        a.category.toLowerCase().includes(search.toLowerCase()))
  );

  const addAgent = useCallback((agentId: string) => {
    if (selectedAgents.length >= MAX_AGENTS) {
      setError(`Maximum ${MAX_AGENTS} agents allowed.`);
      return;
    }
    setSelectedAgents((prev) => [...prev, agentId]);
    setError(null);
  }, [selectedAgents.length]);

  const removeAgent = useCallback((agentId: string) => {
    setSelectedAgents((prev) => prev.filter((id) => id !== agentId));
    setError(null);
  }, []);

  const moveUp = useCallback((idx: number) => {
    if (idx === 0) return;
    setSelectedAgents((prev) => {
      const next = [...prev];
      [next[idx - 1], next[idx]] = [next[idx], next[idx - 1]];
      return next;
    });
  }, []);

  const moveDown = useCallback((idx: number) => {
    setSelectedAgents((prev) => {
      if (idx >= prev.length - 1) return prev;
      const next = [...prev];
      [next[idx], next[idx + 1]] = [next[idx + 1], next[idx]];
      return next;
    });
  }, []);

  const handleSubmit = useCallback(() => {
    if (selectedAgents.length === 0) {
      setError("Select at least 1 agent.");
      return;
    }
    if (!brief.trim()) {
      setError("Enter a brief for the workflow.");
      return;
    }
    setError(null);
    onSubmit(selectedAgents, brief.trim());
  }, [selectedAgents, brief, onSubmit]);

  const agentMap = Object.fromEntries(AVAILABLE_AGENTS.map((a) => [a.id, a]));

  return (
    <div className="flex flex-col h-full bg-white">
      {/* Header */}
      <div className="px-5 pt-5 pb-3 border-b border-gray-100 flex-shrink-0">
        <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-widest mb-1">
          Custom Workflow
        </p>
        <p className="text-[13px] font-semibold text-gray-900">Compose Agent Pipeline</p>
        <p className="text-[11px] text-gray-400 mt-0.5">
          Select 1–{MAX_AGENTS} agents. Deep Planner runs automatically first.
        </p>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-4">
        {/* Brief input */}
        <div>
          <label className="text-[10px] font-semibold text-gray-500 uppercase tracking-widest block mb-1.5">
            Brief
          </label>
          <textarea
            value={brief}
            onChange={(e) => setBrief(e.target.value)}
            placeholder="Describe what you want to build or analyze…"
            className="w-full text-[12px] text-gray-800 bg-gray-50 border border-gray-200 rounded-lg px-3 py-2 resize-none focus:outline-none focus:border-[#1B2A4A] transition-colors"
            rows={3}
          />
        </div>

        {/* Selected agents */}
        <div>
          <div className="flex items-center justify-between mb-1.5">
            <label className="text-[10px] font-semibold text-gray-500 uppercase tracking-widest">
              Pipeline ({selectedAgents.length}/{MAX_AGENTS})
            </label>
            {selectedAgents.length > 0 && (
              <button
                onClick={() => setSelectedAgents([])}
                className="text-[9px] text-gray-400 hover:text-red-500 transition-colors"
              >
                Clear all
              </button>
            )}
          </div>
          {selectedAgents.length === 0 ? (
            <div className="border border-dashed border-gray-200 rounded-lg px-3 py-4 text-center">
              <p className="text-[11px] text-gray-400">No agents selected. Add from the list below.</p>
            </div>
          ) : (
            <div className="space-y-1">
              {selectedAgents.map((agentId, idx) => {
                const agent = agentMap[agentId];
                if (!agent) return null;
                return (
                  <div
                    key={agentId}
                    className="flex items-center gap-2 bg-gray-50 border border-gray-100 rounded-lg px-2.5 py-1.5"
                  >
                    <GripVertical className="h-3 w-3 text-gray-300 flex-shrink-0" />
                    <div className="flex-1 min-w-0">
                      <p className="text-[11px] font-semibold text-gray-800 truncate">{agent.name}</p>
                      <p className="text-[9px] text-gray-400 truncate">{agent.role}</p>
                    </div>
                    <div className="flex items-center gap-0.5 flex-shrink-0">
                      <button
                        onClick={() => moveUp(idx)}
                        disabled={idx === 0}
                        className="p-0.5 text-gray-300 hover:text-gray-600 disabled:opacity-30 transition-colors"
                        title="Move up"
                      >
                        ▲
                      </button>
                      <button
                        onClick={() => moveDown(idx)}
                        disabled={idx === selectedAgents.length - 1}
                        className="p-0.5 text-gray-300 hover:text-gray-600 disabled:opacity-30 transition-colors"
                        title="Move down"
                      >
                        ▼
                      </button>
                      <button
                        onClick={() => removeAgent(agentId)}
                        className="p-0.5 text-gray-300 hover:text-red-500 transition-colors ml-0.5"
                        title="Remove"
                      >
                        <X className="h-3 w-3" />
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Agent selector */}
        <div>
          <label className="text-[10px] font-semibold text-gray-500 uppercase tracking-widest block mb-1.5">
            Add Agents
          </label>
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search agents…"
            className="w-full text-[11px] bg-gray-50 border border-gray-200 rounded-lg px-3 py-1.5 mb-2 focus:outline-none focus:border-[#1B2A4A] transition-colors"
          />
          <div className="space-y-1 max-h-[200px] overflow-y-auto">
            {filteredAgents.map((agent) => (
              <button
                key={agent.id}
                onClick={() => addAgent(agent.id)}
                className="w-full flex items-center gap-2 text-left bg-white border border-gray-100 hover:border-[#1B2A4A] hover:bg-[#f8faff] rounded-lg px-2.5 py-1.5 transition-all group"
              >
                <Plus className="h-3 w-3 text-gray-300 group-hover:text-[#1B2A4A] flex-shrink-0 transition-colors" />
                <div className="flex-1 min-w-0">
                  <p className="text-[11px] font-semibold text-gray-700 truncate">{agent.name}</p>
                  <p className="text-[9px] text-gray-400 truncate">{agent.role}</p>
                </div>
                <span className="text-[8px] text-gray-300 bg-gray-50 px-1.5 py-0.5 rounded flex-shrink-0">
                  {agent.category}
                </span>
              </button>
            ))}
            {filteredAgents.length === 0 && (
              <p className="text-[11px] text-gray-400 text-center py-3">
                {search ? "No agents match your search." : "All agents added."}
              </p>
            )}
          </div>
        </div>

        {/* --- Phase 8 capability surface (API-06): live palette + per-agent
            model picker + validator/issue panel. Additive sibling panels reusing
            the existing composer surface. Subagent/wave-tree + repo-diff viewers
            are DEFERRED (no backing data) and intentionally absent. --- */}

        {/* Capability palette (live /api/capabilities) */}
        <div className="pt-1 border-t border-gray-100">
          <CapabilityPalette />
        </div>

        {/* Per-agent model picker (model catalog from the palette) */}
        <div className="pt-1 border-t border-gray-100">
          <AgentModelPicker
            agents={selectedAgents
              .map((id) => agentMap[id])
              .filter(Boolean)
              .map((a) => ({ id: a.id, name: a.name }))}
            onChange={onModelOverridesChange}
          />
        </div>

        {/* Validator / issue panel (live validator_result / validation_warning WS events) */}
        <div className="pt-1 border-t border-gray-100">
          <ValidatorIssuePanel issues={validatorIssues} />
        </div>

        {/* Wave / subagent tree panel (live wave + subagent lifecycle events — Phase 12 §22) */}
        <div className="pt-1 border-t border-gray-100">
          <WaveTreePanel waves={waves} />
        </div>
      </div>

      {/* Footer */}
      <div className="px-4 py-3 border-t border-gray-100 flex-shrink-0 space-y-2">
        {error && (
          <div className="flex items-center gap-1.5 text-[11px] text-red-600 bg-red-50 rounded-lg px-2.5 py-1.5">
            <AlertCircle className="h-3 w-3 flex-shrink-0" />
            {error}
          </div>
        )}
        {selectedAgents.length > 0 && !error && (
          <div className="flex items-center gap-1.5 text-[11px] text-emerald-600 bg-emerald-50 rounded-lg px-2.5 py-1.5">
            <CheckCircle2 className="h-3 w-3 flex-shrink-0" />
            {selectedAgents.length} agent{selectedAgents.length !== 1 ? "s" : ""} ready
          </div>
        )}
        <button
          onClick={handleSubmit}
          disabled={isRunning || selectedAgents.length === 0 || !brief.trim()}
          className="w-full flex items-center justify-center gap-2 rounded-xl bg-[#1B2A4A] px-4 py-2.5 text-[12px] font-semibold text-white hover:bg-[#2a3d5e] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          <Play className="h-3.5 w-3.5" />
          {isRunning ? "Running…" : "Run Custom Workflow"}
        </button>
      </div>
    </div>
  );
}
