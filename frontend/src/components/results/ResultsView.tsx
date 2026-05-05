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
} from "lucide-react";
import { UserStoryPreview } from "@/components/preview/UserStoryPreview";
import { PPTPreview } from "@/components/preview/PPTPreview";
import { PrototypePreview } from "@/components/preview/PrototypePreview";
import { exportUserStories } from "@/lib/exporters/storyExporter";
import { exportToPptx } from "@/lib/exporters/pptExporter";
import { exportPrototype } from "@/lib/exporters/prototypeExporter";
import { parsePPTSlideData } from "@/lib/parsers/pptParser";
import type { WorkflowType } from "@/types/index";

interface ResultsViewProps {
  workflowType: WorkflowType;
  userStoryContent?: string;
  pptContent?: string;
  prototypeContent?: string;
  isStreaming?: boolean;
  originalInput?: string;
  onRefine?: (message: string) => void;
  onRunAnother?: () => void;
  onGoHome?: () => void;
}

const TYPE_CONFIG: Record<WorkflowType, { icon: typeof FileText; label: string; color: string }> = {
  user_stories: { icon: FileText, label: "User Stories", color: "text-blue-400" },
  ppt: { icon: Presentation, label: "Presentation", color: "text-amber-400" },
  prototype: { icon: Layout, label: "Prototype", color: "text-emerald-400" },
};

const REFINEMENT_SUGGESTIONS: Record<WorkflowType, string[]> = {
  user_stories: [
    "Add more acceptance criteria to each story",
    "Break the largest epic into smaller stories",
    "Add technical stories for infrastructure",
    "Increase story point estimates",
    "Add a security-focused epic",
  ],
  ppt: [
    "Make the opening slide more impactful",
    "Add a competitive analysis slide",
    "Simplify the text — max 4 bullets per slide",
    "Add more data visualizations",
    "Change the tone to be more casual",
  ],
  prototype: [
    "Add a dark mode variant",
    "Include error states for all forms",
    "Add loading skeletons to each page",
    "Make the navigation more prominent",
    "Add a settings page with profile editing",
  ],
};

export function ResultsView({
  workflowType,
  userStoryContent,
  pptContent,
  prototypeContent,
  isStreaming,
  originalInput,
  onRefine,
  onRunAnother,
  onGoHome,
}: ResultsViewProps) {
  const [chatOpen, setChatOpen] = useState(false);
  const [chatInput, setChatInput] = useState("");
  const [copied, setCopied] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const typeConfig = TYPE_CONFIG[workflowType];
  const TypeIcon = typeConfig.icon;
  const suggestions = REFINEMENT_SUGGESTIONS[workflowType];

  // Get the active content based on workflow type
  const activeContent =
    workflowType === "user_stories" ? userStoryContent :
    workflowType === "ppt" ? pptContent :
    prototypeContent;

  const hasContent = !!activeContent;

  const handleDownload = useCallback(() => {
    if (workflowType === "user_stories" && userStoryContent) {
      exportUserStories(userStoryContent);
    } else if (workflowType === "ppt" && pptContent) {
      try {
        const slideData = parsePPTSlideData(pptContent);
        exportToPptx(slideData);
      } catch {
        const blob = new Blob([pptContent], { type: "application/json" });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = "presentation.json";
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
      }
    } else if (workflowType === "prototype" && prototypeContent) {
      exportPrototype(prototypeContent);
    }
  }, [workflowType, userStoryContent, pptContent, prototypeContent]);

  const handleCopy = useCallback(() => {
    if (activeContent) {
      navigator.clipboard.writeText(activeContent);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }, [activeContent]);

  const handleSendRefinement = useCallback(() => {
    if (!chatInput.trim()) return;
    onRefine?.(chatInput.trim());
    setChatInput("");
  }, [chatInput, onRefine]);

  const handleSuggestionClick = useCallback((suggestion: string) => {
    onRefine?.(suggestion);
  }, [onRefine]);

  return (
    <div className="flex h-full flex-col" style={{ backgroundColor: "var(--theme-bg)" }}>
      {/* Results Toolbar */}
      <div className="flex items-center justify-between px-5 py-3 border-b" style={{ borderColor: "var(--theme-border)" }}>
        <div className="flex items-center gap-3">
          <button
            onClick={onGoHome}
            className="flex items-center justify-center rounded-lg p-1.5 text-grey/50 hover:text-white hover:bg-white/5 transition-all"
            aria-label="Back to home"
          >
            <Home className="h-4 w-4" />
          </button>
          <div className="flex items-center gap-2">
            <div className={`flex h-7 w-7 items-center justify-center rounded-lg bg-white/5 border border-white/10`}>
              <TypeIcon className={`h-3.5 w-3.5 ${typeConfig.color}`} />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-white">{typeConfig.label}</h2>
              <p className="text-[10px] text-grey/50">
                {isStreaming ? "Generating..." : "Complete"}
              </p>
            </div>
          </div>
        </div>

        {/* Action buttons */}
        <div className="flex items-center gap-1.5">
          <button
            onClick={handleCopy}
            disabled={!hasContent}
            className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[11px] font-medium text-grey/60 hover:text-white bg-white/5 hover:bg-white/10 border border-white/10 transition-all disabled:opacity-30 disabled:cursor-not-allowed"
            title="Copy to clipboard"
          >
            {copied ? <Check className="h-3 w-3 text-green-400" /> : <Copy className="h-3 w-3" />}
            {copied ? "Copied" : "Copy"}
          </button>
          <button
            onClick={handleDownload}
            disabled={!hasContent}
            className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[11px] font-medium text-grey/60 hover:text-white bg-white/5 hover:bg-white/10 border border-white/10 transition-all disabled:opacity-30 disabled:cursor-not-allowed"
            title="Download"
          >
            <Download className="h-3 w-3" />
            Export
          </button>
          <button
            onClick={() => { setChatOpen(!chatOpen); setTimeout(() => inputRef.current?.focus(), 100); }}
            className={`flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[11px] font-medium transition-all border ${
              chatOpen
                ? "text-blue-300 bg-blue-500/10 border-blue-500/30"
                : "text-grey/60 hover:text-white bg-white/5 hover:bg-white/10 border-white/10"
            }`}
            title="Refine with AI"
          >
            <Sparkles className="h-3 w-3" />
            Refine
          </button>
          <button
            onClick={onRunAnother}
            className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[11px] font-medium text-grey/60 hover:text-white bg-white/5 hover:bg-white/10 border border-white/10 transition-all"
            title="Start a new workflow"
          >
            <RotateCcw className="h-3 w-3" />
            New
          </button>
        </div>
      </div>

      {/* Main content area — artifact preview */}
      <div className="flex-1 min-h-0 overflow-y-auto relative">
        {!hasContent && !isStreaming ? (
          <div className="flex items-center justify-center h-full">
            <div className="text-center">
              <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-white/5 border border-white/10 mx-auto mb-3">
                <TypeIcon className={`h-6 w-6 ${typeConfig.color}`} />
              </div>
              <p className="text-sm text-grey/50">No results yet</p>
              <p className="text-[11px] text-grey/35 mt-1">Run a workflow to see output here</p>
            </div>
          </div>
        ) : (
          <div className="h-full">
            {workflowType === "user_stories" && (
              <UserStoryPreview content={userStoryContent} />
            )}
            {workflowType === "ppt" && (
              <PPTPreview content={pptContent} isStreaming={isStreaming} />
            )}
            {workflowType === "prototype" && (
              <PrototypePreview content={prototypeContent} isStreaming={isStreaming} />
            )}
          </div>
        )}
      </div>

      {/* Refinement Chat — collapsible bottom drawer */}
      <AnimatePresence>
        {chatOpen && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25, ease: "easeInOut" }}
            className="border-t overflow-hidden"
            style={{ borderColor: "var(--theme-border)" }}
          >
            <div className="px-5 py-3">
              {/* Context indicator */}
              {originalInput && (
                <div className="flex items-start gap-2 mb-3 rounded-lg bg-white/[0.02] border border-grey/10 px-3 py-2">
                  <TypeIcon className={`h-3 w-3 ${typeConfig.color} mt-0.5 flex-shrink-0`} />
                  <p className="text-[10px] text-grey/50 line-clamp-2 leading-relaxed">
                    Original: &quot;{originalInput.split("\n---\n")[0].slice(0, 100)}&quot;
                  </p>
                </div>
              )}

              {/* Suggestion chips */}
              <div className="flex flex-wrap gap-1.5 mb-3">
                {suggestions.slice(0, 3).map((suggestion) => (
                  <button
                    key={suggestion}
                    onClick={() => handleSuggestionClick(suggestion)}
                    className="rounded-full px-3 py-1 text-[10px] text-grey/60 hover:text-white bg-white/5 hover:bg-white/10 border border-white/10 hover:border-white/20 transition-all truncate max-w-[200px]"
                  >
                    {suggestion}
                  </button>
                ))}
              </div>

              {/* Input */}
              <div className="flex items-center gap-2">
                <div className="flex-1 flex items-center gap-2 rounded-xl border border-grey/15 bg-white/[0.02] px-3 py-2 focus-within:border-grey/30 transition-colors">
                  <Sparkles className="h-3.5 w-3.5 text-grey/40 flex-shrink-0" />
                  <input
                    ref={inputRef}
                    type="text"
                    value={chatInput}
                    onChange={(e) => setChatInput(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter") handleSendRefinement(); }}
                    placeholder="Tell the agents how to improve this..."
                    className="flex-1 bg-transparent text-xs text-white placeholder-grey/40 focus:outline-none"
                  />
                </div>
                <motion.button
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                  onClick={handleSendRefinement}
                  disabled={!chatInput.trim()}
                  className="flex items-center justify-center rounded-xl bg-white text-black p-2.5 transition-all disabled:opacity-30 disabled:cursor-not-allowed"
                >
                  <Send className="h-3.5 w-3.5" />
                </motion.button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
