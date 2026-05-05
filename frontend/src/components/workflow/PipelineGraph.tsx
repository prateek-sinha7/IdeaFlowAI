"use client";

import { useEffect, useRef } from "react";
import { motion } from "motion/react";
import { CheckCircle2, Clock } from "lucide-react";
import type { AgentRunState } from "@/types/index";
import { AgentNode } from "./AgentNode";

interface PipelineGraphProps {
  agents: AgentRunState[];
  currentIndex: number;
  pipelineType?: string;
  totalDuration?: number | null;
}

const PIPELINE_LABELS: Record<string, string> = {
  user_stories: "User Stories",
  ppt: "Presentation",
  prototype: "Prototype",
};

export function PipelineGraph({
  agents,
  currentIndex,
  pipelineType,
  totalDuration,
}: PipelineGraphProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const activeNodeRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to active agent
  useEffect(() => {
    if (activeNodeRef.current && scrollRef.current) {
      activeNodeRef.current.scrollIntoView({
        behavior: "smooth",
        block: "center",
      });
    }
  }, [currentIndex]);

  const completedCount = agents.filter((a) => a.status === "done").length;

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-grey/10">
        <div className="flex items-center gap-2">
          {pipelineType && (
            <span className="inline-flex items-center rounded-md bg-white/5 border border-white/10 px-2 py-0.5 text-[10px] font-medium text-white/80">
              {PIPELINE_LABELS[pipelineType] || pipelineType}
            </span>
          )}
          <span className="text-[10px] text-grey/50">
            {completedCount} of {agents.length} agents complete
          </span>
        </div>

        {/* Total duration */}
        {totalDuration !== null && totalDuration !== undefined && (
          <div className="flex items-center gap-1 text-[10px] text-grey/50">
            <Clock className="h-2.5 w-2.5" />
            {totalDuration.toFixed(1)}s total
          </div>
        )}
      </div>

      {/* Progress bar */}
      <div className="px-5 py-2">
        <div className="h-1 w-full rounded-full bg-white/5 overflow-hidden">
          <motion.div
            className="h-full rounded-full bg-gradient-to-r from-blue-400 to-green-400"
            initial={{ width: "0%" }}
            animate={{
              width: agents.length > 0
                ? `${(completedCount / agents.length) * 100}%`
                : "0%",
            }}
            transition={{ duration: 0.5, ease: "easeOut" }}
          />
        </div>
      </div>

      {/* Agent nodes list */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-5 py-3 space-y-3">
        {agents.map((agent, idx) => (
          <div
            key={agent.id}
            ref={idx === currentIndex ? activeNodeRef : undefined}
          >
            <AgentNode
              agent={agent}
              isActive={idx === currentIndex}
              index={idx}
            />
          </div>
        ))}

        {/* Completion indicator */}
        {completedCount === agents.length && agents.length > 0 && (
          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.4, delay: 0.2 }}
            className="flex items-center justify-center gap-2 py-4"
          >
            <CheckCircle2 className="h-4 w-4 text-green-400" />
            <span className="text-xs text-green-400 font-medium">
              Pipeline Complete
            </span>
          </motion.div>
        )}
      </div>
    </div>
  );
}
