"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { FileText, Presentation, Layout, PanelRightClose, Eye } from "lucide-react";
import { UserStoryPreview } from "./UserStoryPreview";
import { PPTPreview } from "./PPTPreview";
import { PrototypePreview } from "./PrototypePreview";

type TabId = "user-stories" | "ppt" | "prototype";

interface Tab {
  id: TabId;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
}

const TABS: Tab[] = [
  { id: "user-stories", label: "User Stories", icon: FileText },
  { id: "ppt", label: "PPT", icon: Presentation },
  { id: "prototype", label: "Prototype", icon: Layout },
];

interface PreviewPanelProps {
  userStoryContent?: string;
  pptContent?: string;
  prototypeContent?: string;
  onCollapse?: () => void;
  initialTab?: string;
  onTabSelect?: (tab: string) => void;
}

/**
 * Tabbed preview container with animated tab switching.
 * Three tabs: User Stories, PPT, Prototype with Lucide icons.
 * Uses AnimatePresence for smooth content transitions.
 * Features pill-style tabs and a premium header.
 */
export function PreviewPanel({
  userStoryContent,
  pptContent,
  prototypeContent,
  onCollapse,
  initialTab,
  onTabSelect,
}: PreviewPanelProps) {
  const [activeTab, setActiveTab] = useState<TabId>("user-stories");

  // Sync with initialTab prop when it changes
  useEffect(() => {
    if (initialTab && (initialTab === "user-stories" || initialTab === "ppt" || initialTab === "prototype")) {
      setActiveTab(initialTab as TabId);
    }
  }, [initialTab]);

  const handleTabChange = (tabId: TabId) => {
    setActiveTab(tabId);
    onTabSelect?.(tabId);
  };

  return (
    <div className="flex h-full flex-col backdrop-blur-sm" style={{ backgroundColor: 'var(--theme-surface)' }}>
      {/* Header section */}
      <div className="flex items-center justify-between px-4 pt-4 pb-2">
        <div className="flex items-center gap-2">
          <div className="flex h-6 w-6 items-center justify-center rounded-md bg-white/10">
            <Eye className="h-3.5 w-3.5 text-white/80" />
          </div>
          <h2 className="text-sm font-semibold text-white tracking-tight">Preview</h2>
        </div>
        {onCollapse && (
          <button
            onClick={onCollapse}
            className="flex items-center justify-center rounded-md p-1.5 text-grey/60 hover:text-white hover:bg-white/5 transition-all duration-200"
            aria-label="Close preview"
          >
            <PanelRightClose className="h-4 w-4" />
          </button>
        )}
      </div>

      {/* Pill-style tab bar */}
      <div className="px-4 pb-3" role="tablist">
        <div className="flex gap-1 rounded-xl bg-black/40 p-1 border border-grey/10">
          {TABS.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                role="tab"
                aria-selected={isActive}
                aria-controls={`panel-${tab.id}`}
                className={`relative flex flex-1 items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-xs font-medium transition-all duration-200 ${
                  isActive
                    ? "text-white"
                    : "text-grey/60 hover:text-white/80"
                }`}
                onClick={() => handleTabChange(tab.id)}
              >
                {isActive && (
                  <motion.div
                    layoutId="preview-pill-indicator"
                    className="absolute inset-0 rounded-lg bg-navy/80 border border-grey/15"
                    transition={{ duration: 0.25, ease: "easeInOut" }}
                  />
                )}
                <span className="relative z-10 flex items-center gap-1.5">
                  <Icon className="h-3.5 w-3.5" />
                  {tab.label}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Divider */}
      <div className="mx-4 border-t border-grey/10" />

      {/* Tab panels with AnimatePresence */}
      <div className="relative flex-1 overflow-hidden">
        <AnimatePresence mode="wait">
          <motion.div
            key={activeTab}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.2, ease: "easeInOut" }}
            className="absolute inset-0 overflow-y-auto"
          >
            {activeTab === "user-stories" && (
              <UserStoryPreview content={userStoryContent} />
            )}
            {activeTab === "ppt" && <PPTPreview content={pptContent} />}
            {activeTab === "prototype" && (
              <PrototypePreview content={prototypeContent} />
            )}
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  );
}
