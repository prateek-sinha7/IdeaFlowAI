"use client";

import type { ReactNode } from "react";

/**
 * Tabs — shared run-screen underline-tab primitive (SC-1, D-15).
 *
 * Active tab: ink #15161A text + 2px brand #3C2CDA underline; inactive: #8A8B82
 * (ink-400). All values route through the plan-01 token layer, NO raw hex.
 * The tab shape is a GENERIC `{id,label}` list — never a workflow name (SC-001).
 */
export interface TabItem {
  id: string;
  label: string;
  icon?: ReactNode;
}

export interface TabsProps {
  tabs: TabItem[];
  active: string;
  onChange: (id: string) => void;
  className?: string;
}

export function Tabs({ tabs, active, onChange, className = "" }: TabsProps) {
  return (
    <div
      role="tablist"
      className={["flex items-center gap-4 border-b border-line-divider", className]
        .filter(Boolean)
        .join(" ")}
    >
      {tabs.map((tab) => {
        const isActive = tab.id === active;
        return (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={isActive}
            data-testid={`tab-${tab.id}`}
            onClick={() => onChange(tab.id)}
            className={[
              "-mb-px inline-flex items-center gap-1.5 border-b-2 pb-2 pt-1 font-sans text-[12.5px] font-medium transition-colors",
              isActive
                ? "text-ink-900 border-brand"
                : "text-ink-400 border-transparent hover:text-ink-700",
            ].join(" ")}
          >
            {tab.icon}
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}

export default Tabs;
