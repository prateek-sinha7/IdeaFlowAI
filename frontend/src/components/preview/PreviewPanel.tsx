"use client";

import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { Eye, FolderDown, PanelRightClose, Send, Sparkles, Copy, Check } from "lucide-react";
import { UserStoryPreview } from "./UserStoryPreview";
import { PPTPreview } from "./PPTPreview";
import { PrototypePreview } from "./PrototypePreview";
import { FilesTab } from "@/components/results/FilesTab";
import type { WorkflowType } from "@/types/index";

type PanelTab = "preview" | "files";

interface PreviewPanelProps {
  userStoryContent?: string;
  pptContent?: string;
  prototypeContent?: string;
  isStreaming?: boolean;
  onCollapse?: () => void;
  initialTab?: string;
  onTabSelect?: (tab: string) => void;
  workflowType?: WorkflowType;
  onFollowUp?: (message: string) => void;
}

const TAB_CONFIG: { id: PanelTab; label: string; icon: typeof Eye }[] = [
  { id: "preview", label: "Preview", icon: Eye },
  { id: "files", label: "Files", icon: FolderDown },
];

const SUGGESTIONS: Record<string, string[]> = {
  user_stories: ["Add more acceptance criteria", "Add a security epic", "Break largest epic into smaller stories"],
  ppt: ["Make opening more impactful", "Add data visualizations", "Simplify bullet points"],
  prototype: ["Add dark mode", "Include error states", "Add loading skeletons"],
  validate_pitch: ["Strengthen the market sizing", "Add more competitor analysis", "Make the ask more specific"],
  app_builder: ["Add authentication flow", "Include error handling", "Add API rate limiting"],
  reverse_engineer: ["Focus on security risks", "Add migration timeline", "Include cost estimates"],
  custom: ["Add more detail", "Focus on key areas", "Simplify the output"],
};

export function PreviewPanel({ userStoryContent, pptContent, prototypeContent, isStreaming, onCollapse, initialTab, onTabSelect, workflowType, onFollowUp }: PreviewPanelProps) {
  const [activeTab, setActiveTab] = useState<PanelTab>("preview");
  const [followUpInput, setFollowUpInput] = useState("");
  const [copied, setCopied] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => { if (initialTab === "preview" || initialTab === "files") setActiveTab(initialTab); }, [initialTab]);

  const detectedType: WorkflowType = workflowType || (userStoryContent ? "user_stories" : pptContent ? "ppt" : prototypeContent ? "prototype" : "user_stories");
  const activeContent = detectedType === "user_stories" || detectedType === "app_builder" || detectedType === "reverse_engineer" || detectedType === "custom" ? userStoryContent : detectedType === "ppt" || detectedType === "validate_pitch" ? pptContent : prototypeContent;
  const hasContent = !!(userStoryContent || pptContent || prototypeContent);
  const suggestions = SUGGESTIONS[detectedType] || [];

  const handleTabChange = (tabId: PanelTab) => { setActiveTab(tabId); onTabSelect?.(tabId); };
  const handleCopy = () => { if (activeContent) { navigator.clipboard.writeText(activeContent); setCopied(true); setTimeout(() => setCopied(false), 2000); } };
  const handleSendFollowUp = () => { if (!followUpInput.trim()) return; onFollowUp?.(followUpInput.trim()); setFollowUpInput(""); };

  return (
    <div className="flex h-full flex-col bg-[#faf9f5]">
      {/* Header */}
      <div className="flex items-center justify-between px-4 pt-3 pb-2">
        <div className="flex items-center gap-2">
          <div className="flex h-6 w-6 items-center justify-center rounded-md bg-[#f0eee6]">
            <Eye className="h-3.5 w-3.5 text-[#5e5d59]" />
          </div>
          <h2 className="text-xs font-semibold text-[#141413] tracking-tight">
            {isStreaming ? "Generating..." : hasContent ? "Results" : "Preview"}
          </h2>
        </div>
        <div className="flex items-center gap-1">
          {hasContent && (
            <button onClick={handleCopy} className="flex items-center justify-center rounded-md p-1.5 text-[#87867f] hover:text-[#141413] hover:bg-[#f0eee6] transition-all" title="Copy">
              {copied ? <Check className="h-3.5 w-3.5 text-green-600" /> : <Copy className="h-3.5 w-3.5" />}
            </button>
          )}
          {onCollapse && (
            <button onClick={onCollapse} className="flex items-center justify-center rounded-md p-1.5 text-[#87867f] hover:text-[#141413] hover:bg-[#f0eee6] transition-all" aria-label="Close preview">
              <PanelRightClose className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>

      {/* Tab Bar */}
      <div className="px-4 pb-2">
        <div className="flex gap-0.5 rounded-lg bg-[#f0eee6] p-0.5 border border-[#e8e6dc]">
          {TAB_CONFIG.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button key={tab.id} onClick={() => handleTabChange(tab.id)}
                className={`relative flex flex-1 items-center justify-center gap-1 rounded-md px-2 py-1.5 text-[10px] font-medium transition-all ${isActive ? "text-[#141413] bg-white shadow-sm" : "text-[#87867f] hover:text-[#5e5d59]"}`}>
                <Icon className="h-3 w-3" />
                {tab.label}
              </button>
            );
          })}
        </div>
      </div>

      <div className="mx-4 border-t border-[#e8e6dc]" />

      {/* Tab Content */}
      <div className="relative flex-1 min-h-0 overflow-hidden">
        <AnimatePresence mode="wait">
          {activeTab === "preview" && (
            <motion.div key="preview" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.15 }} className="absolute inset-0 overflow-y-auto">
              {!hasContent ? (
                <div className="flex items-center justify-center h-full"><p className="text-xs text-[#87867f]">Output will appear here</p></div>
              ) : (
                <>
                  {(detectedType === "user_stories" || detectedType === "app_builder" || detectedType === "reverse_engineer" || detectedType === "custom") && userStoryContent && <UserStoryPreview content={userStoryContent} />}
                  {(detectedType === "ppt" || detectedType === "validate_pitch") && pptContent && <PPTPreview content={pptContent} isStreaming={isStreaming} />}
                  {detectedType === "prototype" && prototypeContent && <PrototypePreview content={prototypeContent} isStreaming={isStreaming} />}
                </>
              )}
            </motion.div>
          )}
          {activeTab === "files" && (
            <motion.div key="files" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.15 }} className="absolute inset-0">
              <FilesTab workflowType={detectedType} userStoryContent={userStoryContent} pptContent={pptContent} prototypeContent={prototypeContent} />
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Follow-up */}
      {hasContent && onFollowUp && (
        <div className="border-t border-[#e8e6dc] px-3 py-2.5">
          {suggestions.length > 0 && (
            <div className="flex flex-wrap gap-1 mb-2">
              {suggestions.map((s) => (
                <button key={s} onClick={() => onFollowUp(s)} className="rounded-full px-2 py-0.5 text-[9px] text-[#5e5d59] hover:text-[#141413] bg-[#f0eee6] hover:bg-[#e8e6dc] border border-[#e8e6dc] transition-all truncate max-w-[160px]">{s}</button>
              ))}
            </div>
          )}
          <div className="flex items-center gap-1.5">
            <div className="flex-1 flex items-center gap-1.5 rounded-lg border border-[#e8e6dc] bg-white px-2.5 py-2 focus-within:border-[#c96442]/40 transition-colors">
              <Sparkles className="h-3 w-3 text-[#87867f] flex-shrink-0" />
              <input ref={inputRef} type="text" value={followUpInput} onChange={(e) => setFollowUpInput(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") handleSendFollowUp(); }}
                placeholder="Steer agents or ask follow-up..." className="flex-1 bg-transparent text-[11px] text-[#141413] placeholder-[#87867f] focus:outline-none" />
            </div>
            <button onClick={handleSendFollowUp} disabled={!followUpInput.trim()} className="flex items-center justify-center rounded-lg bg-[#c96442] text-white p-2 transition-all disabled:opacity-30 disabled:cursor-not-allowed">
              <Send className="h-3 w-3" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
