"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { FileText, Presentation, Layout, PanelRightClose, Eye, Download } from "lucide-react";
import { UserStoryPreview } from "./UserStoryPreview";
import { PPTPreview } from "./PPTPreview";
import { PrototypePreview } from "./PrototypePreview";
import { exportUserStories } from "@/lib/exporters/storyExporter";
import { exportToPptx } from "@/lib/exporters/pptExporter";
import { exportPrototype } from "@/lib/exporters/prototypeExporter";
import { parsePPTSlideData } from "@/lib/parsers/pptParser";

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
  isStreaming?: boolean;
  onCollapse?: () => void;
  initialTab?: string;
  onTabSelect?: (tab: string) => void;
}

/**
 * Tabbed preview container with animated tab switching.
 * Three tabs: User Stories, PPT, Prototype with Lucide icons.
 * Uses AnimatePresence for smooth content transitions.
 * Features pill-style tabs, a premium header, and download buttons.
 */
export function PreviewPanel({
  userStoryContent,
  pptContent,
  prototypeContent,
  isStreaming,
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

  const handleDownload = () => {
    if (activeTab === "user-stories" && userStoryContent) {
      exportUserStories(userStoryContent);
    } else if (activeTab === "ppt" && pptContent) {
      try {
        const slideData = parsePPTSlideData(pptContent);
        exportToPptx(slideData);
      } catch {
        // Fallback: download as JSON text
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
    } else if (activeTab === "prototype" && prototypeContent) {
      exportPrototype(prototypeContent);
    }
  };

  const hasContent =
    (activeTab === "user-stories" && userStoryContent) ||
    (activeTab === "ppt" && pptContent) ||
    (activeTab === "prototype" && prototypeContent);

  // Only show tabs that have content
  const visibleTabs = TABS.filter((tab) => {
    if (tab.id === "user-stories") return !!userStoryContent;
    if (tab.id === "ppt") return !!pptContent;
    if (tab.id === "prototype") return !!prototypeContent;
    return false;
  });

  // Auto-select the only visible tab if there's just one
  useEffect(() => {
    if (visibleTabs.length === 1 && activeTab !== visibleTabs[0].id) {
      setActiveTab(visibleTabs[0].id);
    }
  }, [visibleTabs.length]);

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
        <div className="flex items-center gap-1">
          {hasContent && (
            <button
              onClick={handleDownload}
              className="flex items-center justify-center rounded-md p-1.5 text-grey/60 hover:text-white hover:bg-white/5 transition-all duration-200"
              aria-label="Download content"
              title="Download"
            >
              <Download className="h-4 w-4" />
            </button>
          )}
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
      </div>

      {/* Pill-style tab bar — only show when multiple content types exist */}
      {visibleTabs.length > 1 && (
        <div className="px-4 pb-3" role="tablist">
          <div className="flex gap-1 rounded-xl bg-black/40 p-1 border border-grey/10">
            {visibleTabs.map((tab) => {
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
      )}

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
            {activeTab === "ppt" && <PPTPreview content={pptContent} isStreaming={isStreaming} />}
            {activeTab === "prototype" && (
              <PrototypePreview content={prototypeContent} isStreaming={isStreaming} />
            )}
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  );
}
