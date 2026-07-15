/**
 * Canned agent line-ups + full-run scenario players for the E2E suite.
 * Agent seeds mirror the real backend registry ids so the cards match what a
 * live run would show. Use the granular MockWs.* methods for interleaved
 * assertions; use these presets for "just get to a terminal state" setups.
 */
import type { MockSse, AgentSeed } from "./mockSse";

export const AGENTS: Record<string, AgentSeed[]> = {
  user_stories: [
    { id: "domain-analyst", name: "Domain Discovery Agent", role: "Discovery" },
    { id: "story-writer", name: "Story Writer", role: "Authoring" },
    { id: "backlog-compiler", name: "Delivery Compilation Agent", role: "Compilation" },
  ],
  app_builder: [
    { id: "material-analyzer", name: "Material Analyzer", role: "Analysis" },
    { id: "app-api-design", name: "API Design Agent", role: "Design" },
    { id: "app-infra-generator", name: "Infra Generator", role: "Infrastructure" },
    { id: "app-devops", name: "DevOps Agent", role: "DevOps" },
  ],
  od_ppt: [
    { id: "od-ppt-brief-analyst", name: "Brief Analyst", role: "Analysis" },
    { id: "od-ppt-composer", name: "Deck Composer", role: "Composition" },
    { id: "od-ppt-validator", name: "Deck Validator", role: "Validation" },
  ],
  od_prototype: [
    { id: "prototype-specify", name: "Spec Writer", role: "Specification" },
    { id: "prototype-plan", name: "Task Planner", role: "Planning" },
    { id: "prototype-build", name: "Build Agent", role: "Construction" },
    { id: "prototype-validate", name: "Validation Agent", role: "Validation" },
  ],
  custom: [
    { id: "ui-proto-factfind", name: "Fact Finder", role: "Research" },
    { id: "ui-proto-plan", name: "Planner", role: "Planning" },
    { id: "ui-proto-build", name: "Builder", role: "Construction" },
    { id: "ui-proto-validate", name: "Validator", role: "Validation" },
  ],
};

/** Sample HTML deliverable (renders in the generic sandboxed iframe). */
export const SAMPLE_HTML = `<!DOCTYPE html><html><head><title>Habit Tracker</title></head><body><h1>Habit Tracker</h1><p>Custom deliverable</p></body></html>`;

/** A minimal 5-slide deck (od_ppt). */
export const SAMPLE_DECK = `<!DOCTYPE html><html><body>${Array.from({ length: 5 }).map((_, i) => `<section class="slide">Slide ${i + 1}</section>`).join("")}</body></html>`;

/** A user-stories markdown backlog. */
export const SAMPLE_BACKLOG = `# Product Backlog\n\n## Epic: Refunds\n\n### Story: Issue refund\nAs a user I want a refund.\n\n**Given** an order **When** I request a refund **Then** it is processed.\n`;

/** Drive an agent through start → thinking → chunk → complete. */
export async function runAgent(ws: MockSse, id: string, opts: { thinking?: string; chunk?: string } = {}) {
  ws.agentStart(id);
  ws.agentThinking(id, opts.thinking ?? `Working on ${id}…`);
  ws.agentChunk(id, opts.chunk ?? `output from ${id}`);
  ws.agentComplete(id);
}

/** Full green run: start → all agents → pipeline_complete. */
export async function playGreenRun(ws: MockSse, pipelineType: keyof typeof AGENTS, finalOutput: string, deliverable?: { mimetype?: string; filename?: string }) {
  const agents = AGENTS[pipelineType];
  ws.start(agents, { pipelineType });
  for (const a of agents) await runAgent(ws, a.id);
  ws.complete({ pipelineType, finalOutput, deliverableMimetype: deliverable?.mimetype, deliverableFilename: deliverable?.filename });
}

/** Full failed run: every agent errors → pipeline_failed (the ISS-016 shape). */
export async function playFailedRun(ws: MockSse, pipelineType: keyof typeof AGENTS = "user_stories") {
  const agents = AGENTS[pipelineType];
  ws.start(agents, { pipelineType });
  for (const a of agents) { ws.agentStart(a.id); ws.agentError(a.id, "The model rejected this request."); }
  ws.failed({ agentsFailed: agents.map((a) => a.id), error: "Operation not allowed" });
}
