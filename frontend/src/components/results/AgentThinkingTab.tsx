"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { ChevronDown, ChevronRight, Clock, CheckCircle2, Loader2 } from "lucide-react";
import type { AgentThinkingEntry, AgentRunState } from "@/types/index";

interface AgentThinkingTabProps {
  /** Persisted agent outputs from a completed run */
  agentOutputs?: AgentThinkingEntry[];
  /** Live agent states from a running pipeline */
  liveAgents?: AgentRunState[];
  isRunning?: boolean;
}

/**
 * Agent Thinking Tab — shows a timeline of each agent's reasoning and output.
 * Supports both live streaming (during execution) and historical view (past runs).
 */
export function AgentThinkingTab({ agentOutputs, liveAgents, isRunning }: AgentThinkingTabProps) {
  const [expandedId, setExpandedId] = useState<string | null>(null);

  // Use live agents if pipeline is running, otherwise use persisted outputs
  const agents: DisplayAgent[] = isRunning && liveAgents
    ? liveAgents.map((a) => ({
        id: a.id,
        name: a.name,
        role: a.role,
        icon: a.icon,
        thinking: a.thinking,
        output: a.output,
        duration: a.duration,
        status: a.status,
      }))
    : (agentOutputs || []).map((a) => ({
        id: a.agent_id,
        name: a.name,
        role: a.role,
        icon: a.icon,
        thinking: a.thinking,
        output: a.output,
        duration: a.duration,
        status: "done" as const,
      }));

  if (agents.length === 0) {
    return (
      <div className="flex items-center justify-center h-full px-6">
        <div className="text-center">
          <p className="text-sm text-grey/50">No agent data available</p>
          <p className="text-[11px] text-grey/35 mt-1">Run a workflow to see agent reasoning here</p>
        </div>
      </div>
    );
  }

  return (
    <div className="px-5 py-4 space-y-2 overflow-y-auto h-full">
      <div className="flex items-center gap-2 mb-4">
        <span className="text-[11px] text-grey/50 font-medium">
          {agents.length} agents • {isRunning ? "Running..." : "Complete"}
        </span>
      </div>

      {agents.map((agent, idx) => {
        const isExpanded = expandedId === agent.id;
        const isActive = agent.status === "running" || agent.status === "thinking";
        const isDone = agent.status === "done";

        return (
          <motion.div
            key={agent.id}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: idx * 0.03 }}
            className={`rounded-xl border transition-all ${
              isActive
                ? "border-blue-500/30 bg-blue-500/5"
                : isDone
                ? "border-grey/10 bg-white/[0.01]"
                : "border-grey/8 bg-white/[0.005] opacity-50"
            }`}
          >
            {/* Agent header */}
            <button
              onClick={() => setExpandedId(isExpanded ? null : agent.id)}
              className="w-full flex items-center gap-3 px-4 py-3 text-left"
            >
              <span className="text-base flex-shrink-0">{agent.icon}</span>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-[12px] font-medium text-white/90">{agent.name}</span>
                  <span className="text-[9px] text-grey/40 bg-white/5 rounded px-1.5 py-0.5">{agent.role}</span>
                </div>
                {agent.thinking && !isExpanded && (
                  <p className="text-[10px] text-grey/45 mt-0.5 truncate">{agent.thinking}</p>
                )}
              </div>
              <div className="flex items-center gap-2 flex-shrink-0">
                {agent.duration !== null && (
                  <span className="text-[9px] text-grey/40 flex items-center gap-0.5">
                    <Clock className="h-2.5 w-2.5" />
                    {agent.duration.toFixed(1)}s
                  </span>
                )}
                {isActive && <Loader2 className="h-3.5 w-3.5 text-blue-400 animate-spin" />}
                {isDone && <CheckCircle2 className="h-3.5 w-3.5 text-green-400" />}
                {isExpanded ? (
                  <ChevronDown className="h-3 w-3 text-grey/40" />
                ) : (
                  <ChevronRight className="h-3 w-3 text-grey/40" />
                )}
              </div>
            </button>

            {/* Expanded content */}
            <AnimatePresence>
              {isExpanded && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.2 }}
                  className="overflow-hidden"
                >
                  <div className="px-4 pb-4 border-t border-grey/8 pt-3">
                    {agent.thinking && (
                      <div className="mb-3">
                        <span className="text-[9px] uppercase tracking-wider text-grey/40 font-medium">Thinking</span>
                        <p className="text-[11px] text-grey/60 mt-1 leading-relaxed italic">{agent.thinking}</p>
                      </div>
                    )}
                    {agent.output && (
                      <div>
                        <span className="text-[9px] uppercase tracking-wider text-grey/40 font-medium">Output</span>
                        <pre className="text-[10px] text-grey/70 mt-1 leading-relaxed whitespace-pre-wrap max-h-[300px] overflow-y-auto bg-black/20 rounded-lg p-3 border border-grey/8">
                          {agent.output.slice(0, 2000)}
                          {agent.output.length > 2000 && "\n...[truncated]"}
                        </pre>
                      </div>
                    )}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </motion.div>
        );
      })}
    </div>
  );
}

interface DisplayAgent {
  id: string;
  name: string;
  role: string;
  icon: string;
  thinking: string;
  output: string;
  duration: number | null;
  status: string;
}
