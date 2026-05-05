"use client";

import { motion } from "motion/react";
import { Play, Pause, Clock } from "lucide-react";

interface WorkflowControlsProps {
  pipelineType: string;
  isRunning: boolean;
  estimatedDuration: number;
  onRun: () => void;
  onCancel?: () => void;
  onTypeChange?: (type: string) => void;
}

const PIPELINE_TABS = [
  { id: "user_stories", label: "User Stories" },
  { id: "ppt", label: "PPT" },
  { id: "prototype", label: "Prototype" },
];

export function WorkflowControls({
  pipelineType,
  isRunning,
  estimatedDuration,
  onRun,
  onCancel,
  onTypeChange,
}: WorkflowControlsProps) {
  return (
    <div className="space-y-4">
      {/* Pipeline type tabs */}
      <div className="flex items-center gap-1 rounded-lg bg-white/5 border border-white/10 p-1">
        {PIPELINE_TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => onTypeChange?.(tab.id)}
            disabled={isRunning}
            className={`
              flex-1 rounded-md px-3 py-1.5 text-[11px] font-medium transition-all duration-200
              ${
                pipelineType === tab.id
                  ? "bg-white/10 text-white border border-white/10"
                  : "text-grey/60 hover:text-white hover:bg-white/5 border border-transparent"
              }
              ${isRunning ? "opacity-50 cursor-not-allowed" : ""}
            `}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Run / Cancel button + estimated time */}
      <div className="flex items-center gap-3">
        {!isRunning ? (
          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.97 }}
            onClick={onRun}
            className="flex-1 flex items-center justify-center gap-2 rounded-xl bg-white text-black px-5 py-3 text-sm font-semibold transition-all duration-200 hover:bg-white/90 shadow-lg shadow-white/10"
          >
            <Play className="h-4 w-4" />
            Run Workflow
          </motion.button>
        ) : (
          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.97 }}
            onClick={onCancel}
            className="flex-1 flex items-center justify-center gap-2 rounded-xl bg-red-500/20 border border-red-500/30 text-red-300 px-5 py-3 text-sm font-medium transition-all duration-200 hover:bg-red-500/30"
          >
            <Pause className="h-4 w-4" />
            Cancel
          </motion.button>
        )}

        {/* Estimated time */}
        <div className="flex items-center gap-1.5 text-[11px] text-grey/50 flex-shrink-0">
          <Clock className="h-3 w-3" />
          <span>~{Math.ceil(estimatedDuration / 60)}min</span>
        </div>
      </div>
    </div>
  );
}
