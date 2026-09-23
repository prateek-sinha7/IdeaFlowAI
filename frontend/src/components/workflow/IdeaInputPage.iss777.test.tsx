/**
 * ISS-777 (QA-SG-014 sibling of ISS-770) — IdeaInputPage's custom-workflow
 * launch path has no Output Format control at all. Its `resolveDispatchType`
 * (`IdeaInputPage.tsx:450-465`) silently forces `streamed_text`/`output.md`
 * for any agent combination outside the three hardcoded `AGENT_DELIVERABLE_MAP`
 * groups (prototype / user-story / PPT agents) — the same "always .md" defect
 * QA-SG-014 reports, reached from the dashboard's launch screen instead of the
 * `/workflows/new` composer ISS-770 already proved.
 *
 * A user picking e.g. security-audit-agent + documentation-agent has no way to
 * request (or even be told they're getting) anything other than markdown.
 * `aria-label="Output format"` exists once in the whole `workflow/` tree today
 * (`composer/CanvasView.tsx`) — never in `IdeaInputPage.tsx`.
 */
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import path from "node:path";

import { resolveDispatchType } from "./IdeaInputPage";
import type { AgentDef } from "@/types/index";

function agent(id: string): AgentDef {
  return { id, name: id, role: "", pipeline_type: "custom" } as AgentDef;
}

describe("ISS-777 — IdeaInputPage custom-workflow launch has no Output Format control", () => {
  it("renders an Output Format control on the custom-workflow launch screen", () => {
    const src = readFileSync(path.join(__dirname, "IdeaInputPage.tsx"), "utf8");
    expect(src).toContain('aria-label="Output format"');
  });

  it("does not silently force streamed_text/output.md for an agent combo outside the hardcoded groups", () => {
    // security-audit-agent + documentation-agent are in none of
    // AGENT_DELIVERABLE_MAP's three hardcoded groups (prototype/user-story/PPT).
    const agents = [agent("security-audit-agent"), agent("documentation-agent")];
    const { deliverableOverride } = resolveDispatchType(agents, "custom");

    // Correct behaviour: an agent combo the map doesn't recognize must not be
    // silently forced to a hardcoded markdown deliverable with no way for the
    // user to have requested (or been shown) anything else.
    expect(deliverableOverride).toBeUndefined();
  });
});
