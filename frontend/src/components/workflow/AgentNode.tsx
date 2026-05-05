"use client";

import { useState } from "react";
import { motion } from "motion/react";
import {
  CheckCircle2,
  XCircle,
  Loader2,
  Clock,
  ChevronDown,
  ChevronRight,
  BookMarked,
} from "lucide-react";
import type { AgentRunState } from "@/types/index";
import { SkillManager } from "./SkillManager";

interface AgentNodeProps {
  agent: AgentRunState;
  isActive: boolean;
  onExpand?: () => void;
  index?: number;
}

const STATUS_COLORS: Record<string, string> = {
  idle: "border-l-grey/30",
  thinking: "border-l-blue-400",
  running: "border-l-amber-400",
  done: "border-l-green-400",
  error: "border-l-red-400",
};

function StatusBadge({ status }: { status: string }) {
  switch (status) {
    case "idle":
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-white/5 px-2 py-0.5 text-[10px] font-medium text-grey/60">
          Idle
        </span>
      );
    case "thinking":
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-blue-400/10 px-2 py-0.5 text-[10px] font-medium text-blue-400">
          <Loader2 className="h-2.5 w-2.5 animate-spin" />
          Thinking...
        </span>
      );
    case "running":
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-amber-400/10 px-2 py-0.5 text-[10px] font-medium text-amber-400">
          <Loader2 className="h-2.5 w-2.5 animate-spin" />
          Running
        </span>
      );
    case "done":
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-green-400/10 px-2 py-0.5 text-[10px] font-medium text-green-400">
          <CheckCircle2 className="h-2.5 w-2.5" />
          Done ✓
        </span>
      );
    case "error":
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-red-400/10 px-2 py-0.5 text-[10px] font-medium text-red-400">
          <XCircle className="h-2.5 w-2.5" />
          Error ✗
        </span>
      );
    default:
      return null;
  }
}

export function AgentNode({ agent, isActive, onExpand, index = 0 }: AgentNodeProps) {
  const [expanded, setExpanded] = useState(false);
  const [skillOpen, setSkillOpen] = useState(false);

  const handleToggle = () => {
    setExpanded(!expanded);
    onExpand?.();
  };

  const hasOutput = agent.output && agent.output.length > 0;
  const borderColorClass = STATUS_COLORS[agent.status] || STATUS_COLORS.idle;

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: index * 0.08, ease: "easeOut" }}
      className="relative"
    >
      {/* Connection line to next node */}
      <div className="absolute left-6 top-full w-px h-3 border-l border-dashed border-grey/20" />

      <div
        className={`
          glass-action-bar rounded-xl border-l-[3px] transition-all duration-300
          ${borderColorClass}
          ${isActive ? "ring-1 ring-white/10" : ""}
          ${agent.status === "thinking" ? "animate-pulse" : ""}
        `}
      >
        {/* Collapsed header — ~56px */}
        <div
          onClick={handleToggle}
          className="w-full flex items-center gap-3 px-4 py-3 text-left cursor-pointer"
          role="button"
          aria-expanded={expanded}
          tabIndex={0}
          onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") handleToggle(); }}
        >
          {/* Agent icon */}
          <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg bg-white/5 border border-white/10 text-sm">
            {agent.icon || "🤖"}
          </div>

          {/* Name + role */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-xs font-medium text-white truncate">
                {agent.name}
              </span>
              <StatusBadge status={agent.status} />
            </div>
            <p className="text-[10px] text-grey/60 truncate mt-0.5">
              {agent.role}
            </p>
          </div>

          {/* Duration */}
          {agent.duration !== null && (
            <div className="flex items-center gap-1 text-[10px] text-grey/50 flex-shrink-0">
              <Clock className="h-2.5 w-2.5" />
              {agent.duration.toFixed(1)}s
            </div>
          )}

          {/* Skill button */}
          {agent.status === "idle" && (
            <button
              onClick={(e) => { e.stopPropagation(); setSkillOpen(true); }}
              className="flex-shrink-0 flex items-center justify-center rounded-md p-1 text-grey/40 hover:text-blue-400 hover:bg-blue-400/10 transition-all"
              aria-label="Manage skill"
              title="Manage skill"
            >
              <BookMarked className="h-3 w-3" />
            </button>
          )}

          {/* Expand chevron */}
          {hasOutput && (
            <div className="flex-shrink-0 text-grey/40">
              {expanded ? (
                <ChevronDown className="h-3.5 w-3.5" />
              ) : (
                <ChevronRight className="h-3.5 w-3.5" />
              )}
            </div>
          )}
        </div>

        {/* Expanded output content */}
        {expanded && hasOutput && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="border-t border-grey/10 px-4 py-3"
          >
            <pre className="text-[11px] text-grey/80 whitespace-pre-wrap break-words max-h-40 overflow-y-auto font-mono leading-relaxed">
              {agent.output}
            </pre>
          </motion.div>
        )}

        {/* Thinking indicator */}
        {agent.status === "thinking" && agent.thinking && (
          <div className="border-t border-grey/10 px-4 py-2">
            <p className="text-[10px] text-blue-400/80 italic truncate">
              {agent.thinking}
            </p>
          </div>
        )}

        {/* Error display */}
        {agent.status === "error" && agent.error && (
          <div className="border-t border-red-500/20 px-4 py-2 bg-red-500/5">
            <p className="text-[10px] text-red-400 truncate">
              {agent.error}
            </p>
          </div>
        )}
      </div>

      {/* Skill Manager Modal */}
      <SkillManager
        isOpen={skillOpen}
        onClose={() => setSkillOpen(false)}
        agentId={agent.id}
        agentName={agent.name}
      />
    </motion.div>
  );
}
