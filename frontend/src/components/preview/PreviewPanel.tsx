"use client";

import { useState } from "react";
import { UserStoryPreview } from "./UserStoryPreview";
import { PPTPreview } from "./PPTPreview";
import { PrototypePreview } from "./PrototypePreview";

type TabId = "user-stories" | "ppt" | "prototype";

interface Tab {
  id: TabId;
  label: string;
}

const TABS: Tab[] = [
  { id: "user-stories", label: "User Stories" },
  { id: "ppt", label: "PPT" },
  { id: "prototype", label: "Prototype" },
];

interface PreviewPanelProps {
  userStoryContent?: string;
  pptContent?: string;
  prototypeContent?: string;
}

/**
 * Tabbed preview container with three tabs: User Stories, PPT, Prototype.
 * Uses CSS display:none/block to preserve rendered state of inactive tabs.
 * Supports real-time updates during streaming.
 */
export function PreviewPanel({
  userStoryContent,
  pptContent,
  prototypeContent,
}: PreviewPanelProps) {
  const [activeTab, setActiveTab] = useState<TabId>("user-stories");

  return (
    <div className="flex h-full flex-col bg-navy/50">
      {/* Tab bar */}
      <div className="flex border-b border-grey/30" role="tablist">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            role="tab"
            aria-selected={activeTab === tab.id}
            aria-controls={`panel-${tab.id}`}
            className={`tab-transition px-4 py-2 text-sm font-medium ${
              activeTab === tab.id ? "tab-active" : "tab-inactive"
            }`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab panels — all rendered, visibility controlled via CSS */}
      <div className="relative flex-1 overflow-hidden">
        <div
          id="panel-user-stories"
          role="tabpanel"
          aria-labelledby="tab-user-stories"
          className="absolute inset-0 overflow-y-auto"
          style={{ display: activeTab === "user-stories" ? "block" : "none" }}
        >
          <div className="tab-panel">
            <UserStoryPreview content={userStoryContent} />
          </div>
        </div>

        <div
          id="panel-ppt"
          role="tabpanel"
          aria-labelledby="tab-ppt"
          className="absolute inset-0 overflow-y-auto"
          style={{ display: activeTab === "ppt" ? "block" : "none" }}
        >
          <div className="tab-panel">
            <PPTPreview content={pptContent} />
          </div>
        </div>

        <div
          id="panel-prototype"
          role="tabpanel"
          aria-labelledby="tab-prototype"
          className="absolute inset-0 overflow-y-auto"
          style={{ display: activeTab === "prototype" ? "block" : "none" }}
        >
          <div className="tab-panel">
            <PrototypePreview content={prototypeContent} />
          </div>
        </div>
      </div>
    </div>
  );
}
