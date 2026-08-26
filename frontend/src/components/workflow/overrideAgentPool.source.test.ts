import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

// ─────────────────────────────────────────────────────────────────
// An override of a BUILT-IN may only reuse agents that exist as files.
//
// The blank `custom-agent` template mints a dynamic `custom-agent:<instance_id>`
// step. That id has no AGENT.md on disk and is absent from the static roster
// `allowed_custom_agent_ids(pipeline)` builds, so POST /api/runs rejects it at
// ingress with `invalid_agent_ids` — reproduced live on a ppt override carrying
// one custom agent: the override saved, the wizard drew it, and every launch
// 400'd. The template stays available on the composer canvas (a user-defined
// step is the point there; those launch via USER_WORKFLOW_MANIFEST, which has
// no flat allow-list to fail).
//
// Pinned as source assertions rather than a render: AgentLibrary reads its pool
// from a Redux-backed hook, and the value here is the wiring, not the markup.
// ─────────────────────────────────────────────────────────────────

const read = (p: string) => readFileSync(resolve(__dirname, p), "utf8");
const library = read("./AgentLibrary.tsx");
const popup = read("./AgentsPopup.tsx");
const wizard = read("./LaunchWizard.tsx");

const collapse = (s: string) => s.replace(/\s+/g, " ");

describe("override agent pool excludes the file-less custom template", () => {
  it("AgentLibrary gates the blank template behind a prop that defaults to true", () => {
    expect(library).toContain("allowCustomAgentTemplate?: boolean;");
    expect(collapse(library)).toContain("allowCustomAgentTemplate = true,");
  });

  it("AgentLibrary applies that gate to the rendered list", () => {
    expect(collapse(library)).toContain(
      "const templateAllowed = allowCustomAgentTemplate || !isCustomAgentTemplate(agent);",
    );
    expect(collapse(library)).toContain("&& templateAllowed;");
  });

  it("AgentLibrary keeps the category count consistent with the list", () => {
    expect(collapse(library)).toContain(
      "if (!allowCustomAgentTemplate && isCustomAgentTemplate(a)) return;",
    );
  });

  it("AgentsPopup forwards the prop to the library", () => {
    expect(popup).toContain("allowCustomAgentTemplate?: boolean;");
    expect(collapse(popup)).toContain(
      "<AgentLibrary allowCustomAgentTemplate={allowCustomAgentTemplate}",
    );
  });

  it("the LaunchWizard — where overrides are authored — turns it OFF", () => {
    expect(collapse(wizard)).toContain("allowCustomAgentTemplate={false}");
  });

  it("the composer canvas does NOT turn it off (keeps the default)", () => {
    // IdeaInputPage mounts the same popup for the full canvas; a blank
    // user-defined step is exactly what that surface is for.
    const idea = read("./IdeaInputPage.tsx");
    expect(collapse(idea)).not.toContain("allowCustomAgentTemplate={false}");
  });
});

// ─────────────────────────────────────────────────────────────────
// Appending a step to a LAST-STREAMED workflow eats its deliverable.
//
// `ppt` and `streamed_text` both resolve to `ctx.last_streamed` — the final
// step's output IS the deliverable (engine: `ectx.last_streamed =
// results[-1].output`). So the trailing "+" on ppt / user_stories /
// reverse_engineer silently replaced the deck or the backlog with whatever the
// appended agent said: no error, no warning, wrong artifact delivered.
//
// `single_file` (prototype) and `serialized_sandbox` (app_builder, mulesoft,
// dotnet) read a NAMED file back off the sandbox and are immune — which is why
// the guard keys on the declared strategy rather than blocking every append.
// ─────────────────────────────────────────────────────────────────

describe("append guard for last-streamed deliverables", () => {
  const canvas = read("./composer/CanvasView.tsx");
  const flat = collapse(canvas);

  it("only the append-at-end slot is guarded, not mid-chain inserts", () => {
    expect(flat).toContain(
      "const appendsAtEnd = add.insertBeforeId === undefined && pipelineAgents.length > 0;",
    );
  });

  it("guards exactly the two last-streamed strategies", () => {
    expect(flat).toContain(
      'appendsAtEnd && (declaredStrategy === "ppt" || declaredStrategy === "streamed_text")',
    );
  });

  it("keys on the DECLARED strategy, never the composer default", () => {
    // Using the `?? "streamed_text"` fallback would disable the composer's own
    // append slot, where appending is the entire point of the surface.
    expect(flat).toContain("const declaredStrategy = runConfig?.deliverable?.strategy;");
  });

  it("disables the button rather than failing after the fact", () => {
    expect(flat).toContain("disabled={!canAddMore || eatsDeliverable}");
  });
});
