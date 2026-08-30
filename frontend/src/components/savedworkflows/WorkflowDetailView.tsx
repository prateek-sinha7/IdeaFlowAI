"use client";

import Link from "next/link";
import { Cpu } from "lucide-react";
import type { UserWorkflowSummary } from "@/store/api/userWorkflows";
import {
  CUSTOM_AGENT_PREFIX,
  findAgentInTree,
  manifestStepsToAgents,
} from "@/store/api/userWorkflows";
import { useAgentLibrary } from "@/hooks/useAgentLibrary";
import { Card } from "@/components/ui/Card";
import { routes } from "@/lib/routes";

const PIPELINE_LABEL: Record<string, string> = {
  user_stories: "User Stories", ppt: "Presentation", prototype: "Prototype",
  app_builder: "App Builder", custom: "Custom",
  mulesoft_to_springboot: "Mulesoft → Spring Boot", dotnet_to_azure: ".NET → Azure",
};

interface WorkflowDetailViewProps {
  workflow: UserWorkflowSummary;
}

/**
 * T30 (015-frontend-routing, FR-011): minimal read-only summary for
 * `/workflows/{id}`. data-model.md's T4 finding confirmed this screen has no
 * existing `MainView` to point at — `SavedWorkflowsPage` exposes only
 * `onLaunchSaved`/`onCreateNew`, no per-row open/read affordance — so this
 * renders standalone (bypassing `DashboardLayout`'s `MainView` switch)
 * rather than inventing a new `MainView` case.
 */
export function WorkflowDetailView({ workflow }: WorkflowDetailViewProps) {
  const pipelineLabel = PIPELINE_LABEL[workflow.base_pipeline_type] ?? workflow.base_pipeline_type;
  const agentIds = workflow.agent_ids ?? [];
  const { allAgents } = useAgentLibrary();
  // ISS-490: a composed step is `custom-agent:<instance_id>` and has no catalog
  // entry — its user-given name lives on the manifest step, so reconstruct the
  // saved node tree the same way ComposerPage does on reopen and read it there.
  const manifestAgents = manifestStepsToAgents(workflow.manifest?.steps ?? [], (id) =>
    allAgents.find((a) => a.id === id),
  );
  // ISS-327: resolve each id to the same friendly name the Library page and this
  // workflow's own Composer already show for it; the raw id is a last resort.
  const displayName = (id: string) => {
    const bare = id.startsWith(CUSTOM_AGENT_PREFIX) ? id.slice(CUSTOM_AGENT_PREFIX.length) : id;
    return (allAgents.find((a) => a.id === id) ?? findAgentInTree(manifestAgents, bare))?.name ?? id;
  };

  return (
    <div className="min-h-screen bg-surface-paper px-6 py-10">
      <div className="max-w-2xl mx-auto">
        <Card className="p-6">
          <span className="inline-block text-[9px] font-semibold uppercase tracking-[0.06em] px-2 py-1 rounded-[5px] bg-surface-warm text-ink-500 border border-line-control mb-3">
            {pipelineLabel}
          </span>
          <h1 className="text-[24px] font-semibold italic text-ink-900 font-serif leading-tight">
            {workflow.name}
          </h1>
          {workflow.description && (
            <p className="text-[13px] text-ink-500 leading-relaxed mt-2">{workflow.description}</p>
          )}

          <div className="mt-5 pt-5 border-t border-line-divider">
            <p className="flex items-center gap-1.5 text-[11px] font-semibold text-ink-400 uppercase tracking-wide mb-2">
              <Cpu className="h-3 w-3" />
              {agentIds.length} agent{agentIds.length !== 1 ? "s" : ""}
            </p>
            {agentIds.length > 0 ? (
              <ul className="space-y-1">
                {agentIds.map((id) => (
                  <li key={id} className="text-[12.5px] text-ink-700 bg-surface-warm rounded-[8px] px-3 py-2">
                    {displayName(id)}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-[12px] text-ink-400">No steps.</p>
            )}
          </div>

          <div className="mt-6 flex gap-2">
            <Link
              href={routes.workflowEdit(workflow.id)}
              className="flex-1 inline-flex items-center justify-center rounded-[var(--radius-button)] border border-line-control bg-surface-card px-3.5 py-2 text-[12.5px] font-semibold text-ink-900 hover:bg-surface-warm transition-colors"
            >
              Edit
            </Link>
            <Link
              href={routes.workflowRun(workflow.id)}
              className="flex-1 inline-flex items-center justify-center rounded-[var(--radius-button)] bg-brand px-3.5 py-2 text-[12.5px] font-semibold text-white hover:bg-brand-pressed transition-colors"
            >
              Run
            </Link>
          </div>
        </Card>
      </div>
    </div>
  );
}

export default WorkflowDetailView;
