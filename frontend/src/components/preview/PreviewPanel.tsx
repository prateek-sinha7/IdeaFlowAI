"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { Eye, FolderDown, PanelRightClose, Copy, Check } from "lucide-react";
import { UserStoryPreview } from "./UserStoryPreview";
import { PPTPreview } from "./PPTPreview";
import { PrototypePreview } from "./PrototypePreview";
import { MarkdownPreview } from "./MarkdownPreview";
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
}

const TAB_CONFIG: { id: PanelTab; label: string; icon: typeof Eye }[] = [
  { id: "preview", label: "Preview", icon: Eye },
  { id: "files", label: "Files", icon: FolderDown },
];

export function PreviewPanel({ userStoryContent, pptContent, prototypeContent, isStreaming, onCollapse, initialTab, onTabSelect, workflowType }: PreviewPanelProps) {
  const [activeTab, setActiveTab] = useState<PanelTab>("preview");
  const [copied, setCopied] = useState(false);

  useEffect(() => { if (initialTab === "preview" || initialTab === "files") setActiveTab(initialTab); }, [initialTab]);

  const detectedType: WorkflowType = workflowType || (userStoryContent ? "user_stories" : pptContent ? "ppt" : prototypeContent ? "prototype" : "user_stories");
  const activeContent =
    detectedType === "user_stories" || detectedType === "app_builder" || detectedType === "reverse_engineer" || detectedType === "custom"
      ? userStoryContent
      : detectedType === "ppt"
      ? pptContent
      : prototypeContent;
  const hasContent = !!(userStoryContent || pptContent || prototypeContent);

  const handleTabChange = (tabId: PanelTab) => { setActiveTab(tabId); onTabSelect?.(tabId); };
  const handleCopy = () => {
    if (activeContent) {
      navigator.clipboard.writeText(activeContent);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="flex h-full flex-col bg-white border-l border-gray-200">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200">
        <h2 className="text-sm font-semibold text-gray-900">
          {isStreaming ? "Generating..." : hasContent ? "Results" : "Preview"}
        </h2>
        <div className="flex items-center gap-1">
          {hasContent && (
            <button
              onClick={handleCopy}
              className="p-1.5 rounded text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-all"
              title="Copy"
            >
              {copied ? <Check className="h-3.5 w-3.5 text-emerald-600" /> : <Copy className="h-3.5 w-3.5" />}
            </button>
          )}
          {onCollapse && (
            <button
              onClick={onCollapse}
              className="p-1.5 rounded text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-all"
              aria-label="Close preview"
            >
              <PanelRightClose className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>

      {/* Tab Bar */}
      <div className="px-4 py-2 border-b border-gray-200">
        <div className="flex gap-0.5 bg-gray-100 rounded-md p-0.5 w-fit">
          {TAB_CONFIG.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => handleTabChange(tab.id)}
                className={`flex items-center gap-1.5 rounded px-3 py-1 text-xs font-medium transition-all ${
                  isActive ? "bg-white text-gray-900 shadow-sm" : "text-gray-500 hover:text-gray-700"
                }`}
              >
                <Icon className="h-3 w-3" />
                {tab.label}
              </button>
            );
          })}
        </div>
      </div>

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
                  <p className="text-xs text-gray-400">Output will appear here</p>
                </div>
              ) : (
                <>
                  {detectedType === "user_stories" && userStoryContent && <UserStoryPreview content={userStoryContent} />}
                  {(detectedType === "app_builder" || detectedType === "reverse_engineer" || detectedType === "custom") && userStoryContent && <MarkdownPreview content={userStoryContent} />}
                  {detectedType === "ppt" && pptContent && <PPTPreview content={pptContent} isStreaming={isStreaming} />}
                  {detectedType === "prototype" && prototypeContent && <PrototypePreview content={prototypeContent} isStreaming={isStreaming} />}
                </>
              )}
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
              <FilesTab workflowType={detectedType} userStoryContent={userStoryContent} pptContent={pptContent} prototypeContent={prototypeContent} />
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
