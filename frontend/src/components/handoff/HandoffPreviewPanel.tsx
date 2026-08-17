"use client";

import { useEffect, useState } from "react";
import {
  Code2,
  TestTube,
  ShieldCheck,
  ExternalLink,
  CheckCircle2,
  AlertCircle,
} from "lucide-react";

import { DiffView } from "./DiffView";
import { TestReportView, ComplianceReportView } from "./ReportViews";
import type { HandoffAgentId, HandoffPipelineState } from "./types";

const TABS: { id: HandoffAgentId; label: string; icon: typeof Code2 }[] = [
  { id: "coding_agent", label: "Diff", icon: Code2 },
  { id: "test_agent", label: "Tests", icon: TestTube },
  { id: "compliance_agent", label: "Compliance", icon: ShieldCheck },
];

/**
 * Right-side preview pane — the handoff analog of the pptx slide preview
 * panel. Switches between diff / test report / compliance report based on
 * which agent the user has focus on.
 *
 * The PR result strip and the pipeline error footer sit OUTSIDE the
 * tab body so they're always visible once they apply.
 */
export function HandoffPreviewPanel({
  state,
  selectedAgentId,
  onSelectAgent,
}: {
  state: HandoffPipelineState;
  selectedAgentId: HandoffAgentId | null;
  onSelectAgent: (id: HandoffAgentId) => void;
}) {
  // Auto-promote the selected tab as agents finish, so a passive viewer
  // sees the most relevant content without clicking.
  const [autoFollow, setAutoFollow] = useState(true);
  useEffect(() => {
    if (!autoFollow) return;
    if (state.agents.compliance_agent.status === "complete") {
      onSelectAgent("compliance_agent");
    } else if (state.agents.test_agent.status === "complete") {
      onSelectAgent("test_agent");
    } else if (state.agents.coding_agent.status === "complete") {
      onSelectAgent("coding_agent");
    }
  }, [
    autoFollow,
    state.agents.coding_agent.status,
    state.agents.test_agent.status,
    state.agents.compliance_agent.status,
    onSelectAgent,
  ]);

  const codingSkipped = state.resolvedMode === "test";
  const visibleTabs = codingSkipped ? TABS.filter((t) => t.id !== "coding_agent") : TABS;
  const active = selectedAgentId ?? visibleTabs[0]?.id ?? "coding_agent";

  const codingAgent = state.agents.coding_agent;
  const testAgent = state.agents.test_agent;
  const complianceAgent = state.agents.compliance_agent;

  return (
    <section className="h-full flex flex-col bg-white">
      {/* Tab bar */}
      <div className="flex items-center justify-between border-b border-gray-200 px-3">
        <div className="flex items-center">
          {visibleTabs.map((tab) => {
            const Icon = tab.icon;
            const isActive = tab.id === active;
            const agent = state.agents[tab.id];
            return (
              <button
                key={tab.id}
                type="button"
                onClick={() => {
                  setAutoFollow(false);
                  onSelectAgent(tab.id);
                }}
                className={`relative px-4 py-3 text-[12px] font-medium inline-flex items-center gap-2 transition-colors ${
                  isActive
                    ? "text-gray-900 border-b-2 border-blue-500 -mb-px"
                    : "text-gray-500 hover:text-gray-800 border-b-2 border-transparent -mb-px"
                }`}
              >
                <Icon className="h-3.5 w-3.5" />
                {tab.label}
                {agent.status === "complete" && (
                  <CheckCircle2 className="h-3 w-3 text-emerald-600" />
                )}
                {agent.status === "thinking" && (
                  <span className="h-1.5 w-1.5 rounded-full bg-amber-400 animate-pulse" />
                )}
              </button>
            );
          })}
        </div>
        <label className="text-[10px] text-gray-400 inline-flex items-center gap-1.5 select-none cursor-pointer">
          <input
            type="checkbox"
            name="auto-follow"
            checked={autoFollow}
            onChange={(e) => setAutoFollow(e.target.checked)}
            className="h-3 w-3"
          />
          Auto-follow
        </label>
      </div>

      {/* Tab body */}
      <div className="flex-1 min-h-0">
        {active === "coding_agent" && (
          <DiffView
            edits={codingAgent.edits ?? []}
            results={state.editResults}
            testsAdded={codingAgent.tests_added}
            followUps={codingAgent.follow_ups}
          />
        )}
        {active === "test_agent" && <TestReportView report={testAgent.test_report} />}
        {active === "compliance_agent" && (
          <ComplianceReportView report={complianceAgent.compliance_report} />
        )}
      </div>

      {/* PR result strip */}
      {state.prUrl && state.prNumber != null && (
        <div className="border-t border-emerald-200 bg-emerald-50 px-5 py-3 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 min-w-0">
            <CheckCircle2 className="h-4 w-4 text-emerald-700 flex-shrink-0" />
            <div className="min-w-0">
              <div className="text-[12px] font-semibold text-emerald-900">
                Draft pull request opened
              </div>
              {state.branchName && (
                <div className="text-[10px] text-emerald-700 font-mono truncate">
                  {state.branchName}
                </div>
              )}
            </div>
          </div>
          <a
            href={state.prUrl}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 rounded-md bg-emerald-700 text-white px-3 py-1.5 text-[11px] font-medium hover:bg-emerald-800"
          >
            <ExternalLink className="h-3 w-3" />
            View PR #{state.prNumber}
          </a>
        </div>
      )}

      {/* Pipeline error strip */}
      {state.error && (
        <div className="border-t border-red-200 bg-red-50 px-5 py-3 flex items-start gap-2">
          <AlertCircle className="h-4 w-4 text-red-600 mt-0.5 flex-shrink-0" />
          <div className="text-[11px] text-red-800 break-words whitespace-pre-wrap min-w-0">
            <div className="font-semibold mb-0.5">Pipeline failed</div>
            {state.error}
          </div>
        </div>
      )}
    </section>
  );
}
