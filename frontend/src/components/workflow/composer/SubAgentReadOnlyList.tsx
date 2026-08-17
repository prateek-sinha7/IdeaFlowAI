"use client";

import { getAgentInitials } from "../AgentsPopup";
import type { AgentDef } from "@/types/index";

/**
 * Spec 012 (R-35) — Simple view's read-only projection of a node's sub-agent
 * tree. The Simple view (`AgentRow`) has no nested tree UI — only Canvas can
 * add/rename/remove a sub-agent — but the tree still lives in `pipelineAgents`
 * and Save still persists it (`buildWorkflowManifest` walks `agent.children`
 * regardless of which view is open). Rendering NOTHING here made a workflow
 * with sub-agents look, in Simple view, like it didn't have any — this closes
 * that gap without adding an editable surface Simple was never meant to have.
 */
export function SubAgentReadOnlyList({ agents, depth = 1 }: { agents: AgentDef[]; depth?: number }) {
  if (agents.length === 0) return null;
  return (
    <div
      className="mt-2 flex flex-col gap-2 border-l border-dashed border-line-control pl-4"
      style={{ marginLeft: depth * 24 }}
    >
      {agents.map((child) => (
        <div
          key={child.id}
          data-testid={`subagent-row-${child.id}`}
          className="rounded-[11px] border border-dashed border-line-control bg-surface-warm px-3 py-2"
        >
          <div className="flex items-center gap-2.5">
            <span className="grid h-6 w-6 flex-none place-items-center rounded-[7px] bg-line-faint-row font-sans text-[10px] font-semibold text-ink-700">
              {getAgentInitials(child.name)}
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate font-sans text-[12px] font-semibold leading-tight text-ink-900">
                {child.name}
              </p>
              <p className="truncate font-serif text-[10.5px] leading-tight text-ink-400">
                {child.role}
              </p>
            </div>
            <span className="flex-none font-sans text-[9px] font-semibold uppercase tracking-[0.06em] text-ink-300">
              Sub-agent
            </span>
          </div>
          {child.children?.length ? (
            <SubAgentReadOnlyList agents={child.children} depth={depth + 1} />
          ) : null}
        </div>
      ))}
    </div>
  );
}
