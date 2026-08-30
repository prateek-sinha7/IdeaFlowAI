/**
 * ISS-311 — the "Add agent" library's own-category tab (e.g. "User Stories")
 * must not show the generic "No agents found" message when the category is
 * empty ONLY because every catalog agent in it is already on the canvas.
 *
 * Root cause (AgentLibrary.tsx:104-117, :229-232): `filteredAgents` excludes
 * every `existingAgentIds` member, and the default `/create/user_stories`
 * workflow pre-seeds all 6 `user_stories`-tagged catalog agents — so the tab
 * a fresh user lands on is guaranteed empty, and the empty state reuses the
 * same "No agents found" copy as a category with zero catalog entries at
 * all, giving no signal that the agents exist and are simply already added.
 */

import { describe, expect, it } from "vitest";
import { renderWithProviders, screen } from "@/test/renderWithProviders";
import { AgentLibrary } from "./AgentLibrary";
import type { AgentDef } from "@/types/index";

function agent(id: string, pipeline_type: string): AgentDef {
  return {
    id,
    name: id,
    role: "role",
    description: "description",
    pipeline_type,
    order: 0,
    icon: "icon",
    estimated_duration: 1,
    has_skill: false,
  };
}

// The 6 real catalog agents ISS-311's root cause names as `user_stories`-tagged.
const USER_STORIES_AGENT_IDS = [
  "domain-analyst",
  "epic-architect",
  "story-estimator",
  "nfr-specialist",
  "backlog-reviewer",
  "backlog-compiler",
];

describe("ISS-311 — AgentLibrary own-category empty state", () => {
  it("ISS-311: does not show the generic 'No agents found' message when every own-category agent is already on the canvas", () => {
    const agents = USER_STORIES_AGENT_IDS.map((id) => agent(id, "user_stories"));

    renderWithProviders(
      <AgentLibrary
        isOpen={true}
        onClose={() => {}}
        currentPipelineType="user_stories"
        existingAgentIds={USER_STORIES_AGENT_IDS}
      />,
      { preloadedState: { agents: { agents, totalCount: agents.length, pipelines: {}, status: "succeeded", error: null } } },
    );

    // Sanity: the defaulted tab is indeed empty (this part is correct — you
    // cannot re-add an agent already on the canvas).
    expect(screen.queryByTestId(/^library-card-/)).toBeNull();

    // The defect: the empty state must not read like the category has zero
    // catalog entries at all — that copy is reserved for a genuinely empty
    // category, not "everything here is already added".
    expect(screen.queryByText("No agents found")).toBeNull();
  });
});
