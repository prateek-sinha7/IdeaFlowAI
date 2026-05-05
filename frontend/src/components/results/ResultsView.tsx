"use client";

import { useCallback, useRef, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import {
  Download,
  Send,
  FileText,
  Presentation,
  Layout,
  Home,
  Sparkles,
  Copy,
  Check,
  RotateCcw,
  Eye,
  Brain,
  FolderDown,
} from "lucide-react";
import { UserStoryPreview } from "@/components/preview/UserStoryPreview";
import { PPTPreview } from "@/components/preview/PPTPreview";
import { PrototypePreview } from "@/components/preview/PrototypePreview";
import { AgentThinkingTab } from "./AgentThinkingTab";
import { FilesTab } from "./FilesTab";
import type { WorkflowType, AgentThinkingEntry, AgentRunState } from "@/types/index";

type ResultsTab = "preview" | "thinking" | "files";

interface ResultsViewProps {
  workflowType: WorkflowType;
  userStoryContent?: string;
  pptContent?: string;
  prototypeContent?: string;
  isStreaming?: boolean;
  originalInput?: string;
  /** Persisted agent outputs from a completed run */
  agentOutputs?: AgentThinkingEntry[];
  /** Live agent states from a running pipeline */
  liveAgents?: AgentRunState[];
  isPipelineRunning?: boolean;
  onRefine?: (message: string) => void;
  onRunAnother?: () => void;
  onGoHome?: () => void;
}

const TYPE_CONFIG: Record<WorkflowType, { icon: typeof FileText; label: string; color: string }> = {
  user_stories: { icon: FileText, label: "User Stories", color: "text-blue-400" },
  ppt: { icon: Presentation, label: "Presentation", color: "text-amber-400" },
  prototype: { icon: Layout, label: "Prototype", color: "text-emerald-400" },
};

const FOLLOW_UP_SUGGESTIONS: Record<WorkflowType, string[]> = {
  user_stories: [
    "Add more acceptance criteria",
    "Break the largest epic into smaller stories",
    "Add a security-focused epic",
    "Increase story point estimates",
  ],
  ppt: [
    "Make the opening more impactful",
    "Add a competitive analysis slide",
    "Simplify — max 4 bullets per slide",
    "Add more data visualizations",
  ],
  prototype: [
    "Add a dark mode variant",
    "Include error states for forms",
    "Add loading skeletons",
    "Make navigation more prominent",
  ],
};

const TAB_CONFIG: { id: ResultsTab; label: string; icon: typeof Eye }[] = [
  { id: "preview", label: "Preview", icon: Eye },
  { id: "thinking", label: "Agent Thinking", icon: Brain },
  { id: "files", label: "Files", icon: FolderDown },
];

export function ResultsView({
  workflowType,
  userStoryContent,
  pptContent,
  prototypeContent,
  isStreaming,
  originalInput,
  agentOutputs,
  liveAgents,
  isPipelineRunning,
  onRefine,
  onRunAnother,
  onGoHome,
}: ResultsViewProps) {
  const [activeTab, setActiveTab] = useState<ResultsTab>("preview");
  const [followUpInput, setFollowUpInput] = useState("");
  const [copied, setCopied] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const typeConfig = TYPE_CONFIG[workflowType];
  const TypeIcon = typeConfig.icon;
  const suggestions = FOLLOW_UP_SUGGESTIONS[workflowType];

  const activeContent =
    workflowType === "user_stories" ? userStoryContent :
    workflowType === "ppt" ? pptContent :
    prototypeContent;

  const hasContent = !!activeContent;

  const handleCopy = useCallback(() => {
    if (activeContent) {
      navigator.clipboard.writeText(activeContent);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }, [activeContent]);

  const handleSendFollowUp = useCallback(() => {
    if (!followUpInput.trim()) return;
    onRefine?.(followUpInput.trim());
    setFollowUpInput("");
  }, [followUpInput, onRefine]);

  return (
    <div className="flex h-full flex-col" style={{ backgroundColor: "var(--theme-bg)" }}>
      {/* Top Toolbar */}
      <div className="flex items-center justify-between px-5 py-2.5 border-b" style={{ borderColor: "var(--theme-border)" }}>
        <div className="flex items-center gap-3">
          <button
            onClick={onGoHome}
            className="flex items-center justify-center rounded-lg p-1.5 text-grey/50 hover:text-white hover:bg-white/5 transition-all"
            aria-label="Back to home"
          >
            <Home className="h-4 w-4" />
          </button>
          <div className="flex items-center gap-2">
            <div className={`flex h-6 w-6 items-center justify-center rounded-lg bg-white/5 border border-white/10`}>
              <TypeIcon className={`h-3 w-3 ${typeConfig.color}`} />
            </div>
            <span className="text-xs font-medium text-white">{typeConfig.label}</span>
            <span className="text-[10px] text-grey/40">
              {isStreaming ? "• Generating..." : "• Complete"}
            </span>
          </div>
        </div>

        <div className="flex items-center gap-1.5">
          <button
            onClick={handleCopy}
            disabled={!hasContent}
            className="flex items-center gap-1 rounded-lg px-2 py-1.5 text-[10px] font-medium text-grey/60 hover:text-white bg-white/5 hover:bg-white/10 border border-white/10 transition-all disabled:opacity-30"
          >
            {copied ? <Check className="h-3 w-3 text-green-400" /> : <Copy className="h-3 w-3" />}
            {copied ? "Copied" : "Copy"}
          </button>
          <button
            onClick={onRunAnother}
            className="flex items-center gap-1 rounded-lg px-2 py-1.5 text-[10px] font-medium text-grey/60 hover:text-white bg-white/5 hover:bg-white/10 border border-white/10 transition-all"
          >
            <RotateCcw className="h-3 w-3" />
            New
          </button>
        </div>
      </div>

      {/* Tab Bar */}
      <div className="px-5 py-2 border-b" style={{ borderColor: "var(--theme-border)" }}>
        <div className="flex gap-1">
          {TAB_CONFIG.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`relative flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[11px] font-medium transition-all ${
                  isActive
                    ? "text-white bg-white/10 border border-white/15"
                    : "text-grey/50 hover:text-white hover:bg-white/5 border border-transparent"
                }`}
              >
                <Icon className="h-3 w-3" />
                {tab.label}
                {tab.id === "thinking" && isPipelineRunning && (
                  <span className="h-1.5 w-1.5 rounded-full bg-blue-400 animate-pulse" />
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* Tab Content */}
      <div className="flex-1 min-h-0 overflow-hidden">
        <AnimatePresence mode="wait">
          {activeTab === "preview" && (
            <motion.div
              key="preview"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.15 }}
              className="h-full overflow-y-auto"
            >
              {!hasContent && !isStreaming ? (
                <div className="flex items-center justify-center h-full">
                  <div className="text-center">
                    <TypeIcon className={`h-8 w-8 ${typeConfig.color} mx-auto mb-3 opacity-50`} />
                    <p className="text-sm text-grey/50">No results yet</p>
                  </div>
                </div>
              ) : (
                <>
                  {workflowType === "user_stories" && <UserStoryPreview content={userStoryContent} />}
                  {workflowType === "ppt" && <PPTPreview content={pptContent} isStreaming={isStreaming} />}
                  {workflowType === "prototype" && <PrototypePreview content={prototypeContent} isStreaming={isStreaming} />}
                </>
              )}
            </motion.div>
          )}

          {activeTab === "thinking" && (
            <motion.div
              key="thinking"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.15 }}
              className="h-full"
            >
              <AgentThinkingTab
                agentOutputs={agentOutputs}
                liveAgents={liveAgents}
                isRunning={isPipelineRunning}
              />
            </motion.div>
          )}

          {activeTab === "files" && (
            <motion.div
              key="files"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.15 }}
              className="h-full"
            >
              <FilesTab
                workflowType={workflowType}
                userStoryContent={userStoryContent}
                pptContent={pptContent}
                prototypeContent={prototypeContent}
              />
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Persistent Follow-up Input */}
      <div className="border-t px-5 py-3" style={{ borderColor: "var(--theme-border)" }}>
        {/* Suggestion chips */}
        <div className="flex flex-wrap gap-1.5 mb-2.5">
          {suggestions.slice(0, 3).map((suggestion) => (
            <button
              key={suggestion}
              onClick={() => { onRefine?.(suggestion); }}
              className="rounded-full px-2.5 py-1 text-[9px] text-grey/55 hover:text-white bg-white/5 hover:bg-white/10 border border-white/8 hover:border-white/20 transition-all"
            >
              {suggestion}
            </button>
          ))}
        </div>

        {/* Input */}
        <div className="flex items-center gap-2">
          <div className="flex-1 flex items-center gap-2 rounded-xl border border-grey/15 bg-white/[0.02] px-3 py-2.5 focus-within:border-grey/30 transition-colors">
            <Sparkles className="h-3.5 w-3.5 text-grey/40 flex-shrink-0" />
            <input
              ref={inputRef}
              type="text"
              value={followUpInput}
              onChange={(e) => setFollowUpInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") handleSendFollowUp(); }}
              placeholder="Ask a follow-up or steer the agents..."
              className="flex-1 bg-transparent text-xs text-white placeholder-grey/40 focus:outline-none"
            />
          </div>
          <motion.button
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            onClick={handleSendFollowUp}
            disabled={!followUpInput.trim()}
            className="flex items-center justify-center rounded-xl bg-white text-black p-2.5 transition-all disabled:opacity-30 disabled:cursor-not-allowed"
          >
            <Send className="h-3.5 w-3.5" />
          </motion.button>
        </div>
      </div>
    </div>
  );
}
