"use client";

import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import {
  Eye,
  Brain,
  FolderDown,
  PanelRightClose,
  Download,
  Send,
  Sparkles,
  Copy,
  Check,
} from "lucide-react";
import { UserStoryPreview } from "./UserStoryPreview";
import { PPTPreview } from "./PPTPreview";
import { PrototypePreview } from "./PrototypePreview";
import { AgentThinkingTab } from "@/components/results/AgentThinkingTab";
import { FilesTab } from "@/components/results/FilesTab";
import type { AgentThinkingEntry, AgentRunState, WorkflowType } from "@/types/index";

type PanelTab = "preview" | "thinking" | "files";

interface PreviewPanelProps {
  userStoryContent?: string;
  pptContent?: string;
  prototypeContent?: string;
  isStreaming?: boolean;
  onCollapse?: () => void;
  initialTab?: string;
  onTabSelect?: (tab: string) => void;
  /** The workflow type that generated this content */
  workflowType?: WorkflowType;
  /** Persisted agent outputs from a completed run */
  agentOutputs?: AgentThinkingEntry[];
  /** Live agent states from a running pipeline */
  liveAgents?: AgentRunState[];
  /** Whether the pipeline is currently running */
  isPipelineRunning?: boolean;
  /** Callback for follow-up / steering input */
  onFollowUp?: (message: string) => void;
}

const TAB_CONFIG: { id: PanelTab; label: string; icon: typeof Eye }[] = [
  { id: "preview", label: "Preview", icon: Eye },
  { id: "thinking", label: "Thinking", icon: Brain },
  { id: "files", label: "Files", icon: FolderDown },
];

const SUGGESTIONS: Record<string, string[]> = {
  user_stories: ["Add more acceptance criteria", "Add a security epic", "Break largest epic into smaller stories"],
  ppt: ["Make opening more impactful", "Add data visualizations", "Simplify bullet points"],
  prototype: ["Add dark mode", "Include error states", "Add loading skeletons"],
};

/**
 * Preview Panel — auto-opens when content is generated.
 * 3 tabs: Preview (rendered output), Agent Thinking (reasoning timeline), Files (downloads).
 * Includes a persistent follow-up input at the bottom for steering agents.
 */
export function PreviewPanel({
  userStoryContent,
  pptContent,
  prototypeContent,
  isStreaming,
  onCollapse,
  initialTab,
  onTabSelect,
  workflowType,
  agentOutputs,
  liveAgents,
  isPipelineRunning,
  onFollowUp,
}: PreviewPanelProps) {
  const [activeTab, setActiveTab] = useState<PanelTab>("preview");
  const [followUpInput, setFollowUpInput] = useState("");
  const [copied, setCopied] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  // Sync with initialTab prop
  useEffect(() => {
    if (initialTab === "preview" || initialTab === "thinking" || initialTab === "files") {
      setActiveTab(initialTab);
    }
  }, [initialTab]);

  // Determine which content type is active
  const detectedType: WorkflowType = workflowType || (
    userStoryContent ? "user_stories" :
    pptContent ? "ppt" :
    prototypeContent ? "prototype" :
    "user_stories"
  );

  const activeContent = detectedType === "user_stories" ? userStoryContent :
    detectedType === "ppt" ? pptContent : prototypeContent;

  const hasContent = !!(userStoryContent || pptContent || prototypeContent);
  const suggestions = SUGGESTIONS[detectedType] || [];

  const handleTabChange = (tabId: PanelTab) => {
    setActiveTab(tabId);
    onTabSelect?.(tabId);
  };

  const handleCopy = () => {
    if (activeContent) {
      navigator.clipboard.writeText(activeContent);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleSendFollowUp = () => {
    if (!followUpInput.trim()) return;
    onFollowUp?.(followUpInput.trim());
    setFollowUpInput("");
  };

  return (
    <div className="flex h-full flex-col" style={{ backgroundColor: "var(--theme-surface)" }}>
      {/* Header */}
      <div className="flex items-center justify-between px-4 pt-3 pb-2">
        <div className="flex items-center gap-2">
          <div className="flex h-6 w-6 items-center justify-center rounded-md bg-white/10">
            <Eye className="h-3.5 w-3.5 text-white/80" />
          </div>
          <h2 className="text-xs font-semibold text-white tracking-tight">
            {isStreaming ? "Generating..." : hasContent ? "Results" : "Preview"}
          </h2>
        </div>
        <div className="flex items-center gap-1">
          {hasContent && (
            <button
              onClick={handleCopy}
              className="flex items-center justify-center rounded-md p-1.5 text-grey/60 hover:text-white hover:bg-white/5 transition-all"
              title="Copy to clipboard"
            >
              {copied ? <Check className="h-3.5 w-3.5 text-green-400" /> : <Copy className="h-3.5 w-3.5" />}
            </button>
          )}
          {onCollapse && (
            <button
              onClick={onCollapse}
              className="flex items-center justify-center rounded-md p-1.5 text-grey/60 hover:text-white hover:bg-white/5 transition-all"
              aria-label="Close preview"
            >
              <PanelRightClose className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>

      {/* Tab Bar */}
      <div className="px-4 pb-2">
        <div className="flex gap-0.5 rounded-lg bg-black/30 p-0.5 border border-grey/10">
          {TAB_CONFIG.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => handleTabChange(tab.id)}
                className={`relative flex flex-1 items-center justify-center gap-1 rounded-md px-2 py-1.5 text-[10px] font-medium transition-all ${
                  isActive ? "text-white" : "text-grey/50 hover:text-white/70"
                }`}
              >
                {isActive && (
                  <motion.div
                    layoutId="panel-tab-indicator"
                    className="absolute inset-0 rounded-md bg-white/10 border border-white/10"
                    transition={{ duration: 0.2 }}
                  />
                )}
                <span className="relative z-10 flex items-center gap-1">
                  <Icon className="h-3 w-3" />
                  {tab.label}
                  {tab.id === "thinking" && isPipelineRunning && (
                    <span className="h-1.5 w-1.5 rounded-full bg-blue-400 animate-pulse" />
                  )}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Divider */}
      <div className="mx-4 border-t border-grey/8" />

      {/* Tab Content */}
      <div className="relative flex-1 min-h-0 overflow-hidden">
        <AnimatePresence mode="wait">
          {activeTab === "preview" && (
            <motion.div
              key="preview"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.15 }}
              className="absolute inset-0 overflow-y-auto"
            >
              {!hasContent ? (
                <div className="flex items-center justify-center h-full">
                  <p className="text-xs text-grey/40">Output will appear here</p>
                </div>
              ) : (
                <>
                  {detectedType === "user_stories" && userStoryContent && (
                    <UserStoryPreview content={userStoryContent} />
                  )}
                  {detectedType === "ppt" && pptContent && (
                    <PPTPreview content={pptContent} isStreaming={isStreaming} />
                  )}
                  {detectedType === "prototype" && prototypeContent && (
                    <PrototypePreview content={prototypeContent} isStreaming={isStreaming} />
                  )}
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
              className="absolute inset-0"
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
              className="absolute inset-0"
            >
              <FilesTab
                workflowType={detectedType}
                userStoryContent={userStoryContent}
                pptContent={pptContent}
                prototypeContent={prototypeContent}
              />
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Follow-up Input — always visible when there's content */}
      {(hasContent || isPipelineRunning) && onFollowUp && (
        <div className="border-t px-3 py-2.5" style={{ borderColor: "var(--theme-border)" }}>
          {/* Suggestion chips */}
          {suggestions.length > 0 && !isPipelineRunning && (
            <div className="flex flex-wrap gap-1 mb-2">
              {suggestions.map((s) => (
                <button
                  key={s}
                  onClick={() => onFollowUp(s)}
                  className="rounded-full px-2 py-0.5 text-[9px] text-grey/50 hover:text-white bg-white/5 hover:bg-white/10 border border-white/8 transition-all truncate max-w-[160px]"
                >
                  {s}
                </button>
              ))}
            </div>
          )}
          {/* Input */}
          <div className="flex items-center gap-1.5">
            <div className="flex-1 flex items-center gap-1.5 rounded-lg border border-grey/15 bg-white/[0.02] px-2.5 py-2 focus-within:border-grey/30 transition-colors">
              <Sparkles className="h-3 w-3 text-grey/40 flex-shrink-0" />
              <input
                ref={inputRef}
                type="text"
                value={followUpInput}
                onChange={(e) => setFollowUpInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") handleSendFollowUp(); }}
                placeholder="Steer agents or ask follow-up..."
                className="flex-1 bg-transparent text-[11px] text-white placeholder-grey/40 focus:outline-none"
              />
            </div>
            <button
              onClick={handleSendFollowUp}
              disabled={!followUpInput.trim()}
              className="flex items-center justify-center rounded-lg bg-white text-black p-2 transition-all disabled:opacity-30 disabled:cursor-not-allowed"
            >
              <Send className="h-3 w-3" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
