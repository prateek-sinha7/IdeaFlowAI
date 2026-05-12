"use client";

import { motion } from "motion/react";
import { CheckCircle2, Loader2, AlertCircle, Code2, TestTube, ShieldCheck } from "lucide-react";

import type {
  HandoffAgentId,
  HandoffAgentState,
  HandoffPipelineState,
} from "./types";

const AGENT_ORDER: HandoffAgentId[] = ["coding_agent", "test_agent", "compliance_agent"];

const ICON_FOR: Record<HandoffAgentId, React.ComponentType<{ className?: string }>> = {
  coding_agent: Code2,
  test_agent: TestTube,
  compliance_agent: ShieldCheck,
};

const ROLE_FOR: Record<HandoffAgentId, string> = {
  coding_agent: "Senior software engineer",
  test_agent: "Senior test engineer",
  compliance_agent: "Principal reviewer",
};

const ICON_STYLES = [
  { bg: "#E8EDF5", text: "#1B2A4A" },
  { bg: "#F0EDE8", text: "#5C4A2A" },
  { bg: "#EAF0EA", text: "#2A5C2A" },
];

function AgentCard({
  agent,
  index,
  selected,
  onSelect,
  skipped,
}: {
  agent: HandoffAgentState;
  index: number;
  selected: boolean;
  onSelect: () => void;
  skipped: boolean;
}) {
  const Icon = ICON_FOR[agent.agent_id];
  const iconStyle = ICON_STYLES[index % ICON_STYLES.length];

  const isQueued = agent.status === "queued";
  const isActive = agent.status === "thinking";
  const isDone = agent.status === "complete";
  const isError = agent.status === "error";

  const duration =
    agent.completed_at && agent.started_at
      ? (agent.completed_at - agent.started_at) / 1000
      : null;

  return (
    <motion.button
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.04 }}
      onClick={onSelect}
      type="button"
      className={`w-full text-left rounded-xl border px-4 py-3.5 transition-all ${
        selected
          ? "border-blue-300 bg-blue-50/40 shadow-sm"
          : isActive
          ? "border-gray-200 bg-white shadow-sm"
          : isDone
          ? "border-gray-100 bg-white hover:bg-gray-50"
          : isError
          ? "border-red-100 bg-red-50"
          : "border-gray-100 bg-white/60 hover:bg-white"
      } ${skipped ? "opacity-50" : ""}`}
    >
      <div className="flex items-center gap-3 mb-2">
        <div
          className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0"
          style={{
            background: isQueued ? "#F5F5F0" : iconStyle.bg,
            color: isQueued ? "#9CA3AF" : iconStyle.text,
          }}
        >
          <Icon className="h-4 w-4" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2">
            <p
              className={`text-[12px] font-semibold leading-tight ${
                isQueued ? "text-gray-400" : "text-gray-900"
              }`}
            >
              {agent.name}
            </p>
            <div className="flex items-center gap-1.5 flex-shrink-0">
              {isDone && duration != null && (
                <span className="text-[9px] text-gray-400">{duration.toFixed(0)}s</span>
              )}
              {skipped && (
                <span className="text-[9px] font-bold text-gray-500 bg-gray-100 border border-gray-200 px-1.5 py-0.5 rounded">
                  SKIPPED
                </span>
              )}
              {!skipped && isDone && (
                <span className="text-[9px] font-bold text-emerald-700 bg-emerald-50 border border-emerald-200 px-1.5 py-0.5 rounded">
                  DONE
                </span>
              )}
              {!skipped && isActive && (
                <span className="text-[9px] font-bold text-amber-700 bg-amber-50 border border-amber-200 px-1.5 py-0.5 rounded animate-pulse">
                  RUNNING
                </span>
              )}
              {!skipped && isError && (
                <span className="text-[9px] font-bold text-red-700 bg-red-50 border border-red-200 px-1.5 py-0.5 rounded">
                  ERROR
                </span>
              )}
            </div>
          </div>
          <p className="text-[10px] text-gray-400 mt-0.5">{ROLE_FOR[agent.agent_id]}</p>
        </div>
      </div>

      {isDone && agent.summary && (
        <p className="text-[11px] text-gray-600 line-clamp-2 leading-relaxed">
          {agent.summary}
        </p>
      )}
      {isDone && !agent.summary && agent.test_report?.verdict && (
        <p className="text-[11px] text-gray-600 line-clamp-2 leading-relaxed">
          {agent.test_report.summary || ""}
        </p>
      )}
      {isDone && !agent.summary && agent.compliance_report?.verdict && (
        <p className="text-[11px] text-gray-600 line-clamp-2 leading-relaxed">
          {agent.compliance_report.summary || ""}
        </p>
      )}
      {isActive && (
        <p className="text-[11px] text-gray-500 flex items-center gap-1.5">
          <Loader2 className="h-3 w-3 animate-spin text-gray-400" />
          {agent.thinking || "Working..."}
        </p>
      )}
      {isError && agent.error && (
        <p className="text-[11px] text-red-600">{agent.error}</p>
      )}
      {isQueued && !skipped && (
        <p className="text-[11px] text-gray-400">Waiting...</p>
      )}
    </motion.button>
  );
}

export function HandoffAgentPanel({
  state,
  selectedAgentId,
  onSelectAgent,
}: {
  state: HandoffPipelineState;
  selectedAgentId: HandoffAgentId | null;
  onSelectAgent: (id: HandoffAgentId) => void;
}) {
  const codingSkipped = state.resolvedMode === "test";

  const totalDone = AGENT_ORDER.filter(
    (id) => !(id === "coding_agent" && codingSkipped) && state.agents[id].status === "complete"
  ).length;
  const totalActive = AGENT_ORDER.filter((id) => state.agents[id].status !== "queued").length;
  const totalExpected = codingSkipped ? 2 : 3;

  const overallStatusLabel =
    state.pipelineStatus === "running"
      ? "Pipeline running"
      : state.pipelineStatus === "completed"
      ? "Pipeline complete"
      : state.pipelineStatus === "failed"
      ? "Pipeline failed"
      : "Pipeline pending";

  return (
    <aside className="h-full flex flex-col border-r border-gray-200 bg-gray-50">
      {/* Header */}
      <div className="px-5 py-4 border-b border-gray-200 bg-white">
        <div className="flex items-center justify-between mb-1.5">
          <h2 className="text-[12px] font-semibold text-gray-900">Handoff pipeline</h2>
          <span className="text-[10px] text-gray-500">
            {totalDone}/{totalExpected}
          </span>
        </div>
        <p className="text-[10px] uppercase tracking-wide text-gray-400">
          {overallStatusLabel}
        </p>
        {totalActive > 0 && totalExpected > 0 && (
          <div className="mt-3 h-1 w-full rounded-full bg-gray-100 overflow-hidden">
            <div
              className="h-full bg-blue-500 transition-all duration-700"
              style={{ width: `${Math.min(100, (totalDone / totalExpected) * 100)}%` }}
            />
          </div>
        )}
      </div>

      {/* Agent list */}
      <div className="flex-1 overflow-y-auto p-3 space-y-2">
        {AGENT_ORDER.map((id, idx) => (
          <AgentCard
            key={id}
            agent={state.agents[id]}
            index={idx}
            selected={selectedAgentId === id}
            onSelect={() => onSelectAgent(id)}
            skipped={id === "coding_agent" && codingSkipped}
          />
        ))}
      </div>

      {/* Phase log */}
      {state.phases.length > 0 && (
        <div className="px-5 py-3 border-t border-gray-200 bg-white max-h-40 overflow-y-auto">
          <p className="text-[10px] uppercase tracking-wide text-gray-400 mb-1.5">
            Steps
          </p>
          <div className="text-[10px] text-gray-500 font-mono space-y-0.5">
            {state.phases.map((p, idx) => (
              <div key={idx} className="flex items-start gap-1">
                {p.status === "end" ? (
                  <CheckCircle2 className="h-2.5 w-2.5 mt-0.5 text-emerald-600 flex-shrink-0" />
                ) : (
                  <Loader2 className="h-2.5 w-2.5 mt-0.5 text-blue-500 animate-spin flex-shrink-0" />
                )}
                <span className="truncate">{p.section}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Error footer */}
      {state.error && (
        <div className="px-5 py-3 border-t border-gray-200 bg-red-50">
          <div className="flex items-start gap-2">
            <AlertCircle className="h-3.5 w-3.5 mt-0.5 text-red-600 flex-shrink-0" />
            <p className="text-[11px] text-red-700 break-words">{state.error}</p>
          </div>
        </div>
      )}
    </aside>
  );
}
