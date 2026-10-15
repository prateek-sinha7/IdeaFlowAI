/**
 * TS-O — PreviewPanel deliverable renderers, dispatched by workflow type.
 * Proves the four bespoke render branches (user_stories backlog, app_builder
 * IDE, ppt deck iframe, prototype iframe) + the neutral empty state, the
 * three preview tabs, and the header copy affordance.
 *
 * Setup per case: goto + runWith(user_stories framing) → mockSse.start(...) with
 * the case's pipelineType → run agents → mockSse.complete({ pipelineType,
 * finalOutput }). pipeline_start's pipeline_type drives the workflowType sync in
 * DashboardLayout (ppt, prototype, app_builder),
 * so the right renderer mounts on completion.
 */
import { test, expect } from "../fixtures/test";
import { AGENTS, runAgent, SAMPLE_BACKLOG, SAMPLE_DECK } from "../fixtures/scenarios";

// A final_output the AppBuilder IDE parser yields ≥1 file from. Format 1 of
// parseAppBuilderFilesForIDE: ```filename: path/to/file.ext\n<content>\n```
const SAMPLE_APP_FILES = [
  "# Generated App",
  "",
  "```filename: src/index.ts",
  "export const x = 1;",
  "```",
  "",
  "```filename: src/server/app.ts",
  "export const app = () => 'ok';",
  "```",
].join("\n");

/** Start a pipeline of `pipelineType`, run all its agents, then complete it. */
async function runToComplete(
  mockSse: import("../fixtures/mockSse").MockSse,
  pipelineType: keyof typeof AGENTS,
  finalOutput: string,
) {
  const agents = AGENTS[pipelineType];
  mockSse.start(agents, { pipelineType });
  // Lazy-attach cases: let the stream attach before the rest of the run plays,
  // else the durable replay delivers start→complete in one burst and the run
  // never renders as live (no execution-view swap).
  await mockSse.ready();
  for (const a of agents) await runAgent(mockSse, a.id);
  mockSse.complete({ pipelineType, finalOutput });
}

test.describe("TS-O — deliverable renderers", () => {
  // Cases whose pipeline_start declares a NON-user_stories type are served by the
  // mock's lazy attach instead of a user_stories launch: since 015-frontend-routing
  // a launch persists its run TYPE (sessionStorage run_type:{id}) and restores it
  // across the /runs/{id}/stream remount, so launching user_stories and then
  // announcing ppt is a state the real backend can never produce.
  const NON_USER_STORIES = /TS-O-0[345] /;
  test.beforeEach(async ({ dashboard }, testInfo) => {
    await dashboard.goto();
    if (NON_USER_STORIES.test(testInfo.title)) return;
    await dashboard.runWith({ workflow: "Generate product requirements", idea: "Refunds backlog" });
  });

  test("TS-O-01 empty preview before completion shows the neutral state", async ({ dashboard, mockSse }) => {
    // Start + run agents but do NOT complete — no deliverable yet.
    const agents = AGENTS.user_stories;
    mockSse.start(agents, { pipelineType: "user_stories" });
    for (const a of agents) await runAgent(mockSse, a.id);

    // Phase 42-02 (§B) auto-tabs a live/building run to Steps, so open the Preview
    // tab to observe its pre-completion chrome.
    await dashboard.previewTab().click();

    // Phase 39 redesign: while the run is still in-flight (isRunning) with no
    // content, the preview shows the streaming "Building your deliverable…"
    // placeholder inside PreviewChrome (the neutral "Output will appear here"
    // now only shows for a settled/idle empty run). This is the heir of the
    // pre-completion neutral state.
    await expect(dashboard.page.getByText(/Building your deliverable/)).toBeVisible();
  });

  test("TS-O-02 user_stories renders the Product Backlog with stats", async ({ dashboard, mockSse }) => {
    await runToComplete(mockSse, "user_stories", SAMPLE_BACKLOG);

    // Terminal auto-tab fires once the run is Done; re-select Preview after it.
    await expect(dashboard.doneBadge()).toBeVisible();
    await dashboard.openPreview();
    // The h1 backlog header (".first()" — the sample's epic title also reads
    // "Product Backlog", rendered later as an h2).
    await expect(dashboard.page.getByRole("heading", { name: "Product Backlog" }).first()).toBeVisible();
    // Stat labels from the backlog header.
    for (const label of ["Epics", "Stories", "Points", "Sprints"]) {
      await expect(dashboard.page.getByText(label, { exact: true }).first()).toBeVisible();
    }
    // The backlog-specific copy affordance.
    await expect(dashboard.page.getByText("Copy MD")).toBeVisible();
  });

  test("TS-O-03 app_builder renders the file-tree IDE", async ({ dashboard, mockSse }) => {
    await runToComplete(mockSse, "app_builder", SAMPLE_APP_FILES);

    // The IDE chrome appears once ≥1 file parses. Two filename: blocks → "2 files".
    await expect(dashboard.doneBadge()).toBeVisible();
    await dashboard.openPreview();
    // First IDE locator gets a larger timeout: cold first-load of the IDE chunk.
    await expect(dashboard.page.getByText(/^\d+ files$/)).toBeVisible({ timeout: 30000 });
    await expect(dashboard.page.getByPlaceholder("Search files...")).toBeVisible();
    await expect(dashboard.page.getByRole("button", { name: "Download ZIP" })).toBeVisible();
  });

  test("TS-O-04 ppt renders the deck in a sandboxed iframe", async ({ dashboard, mockSse }) => {
    await runToComplete(mockSse, "ppt", SAMPLE_DECK);

    await expect(dashboard.deckIframe()).toBeVisible();
  });

  test("TS-O-05 prototype renders the prototype iframe", async ({ dashboard, mockSse }) => {
    await runToComplete(
      mockSse,
      "prototype",
      "<!DOCTYPE html><html><body><h1>App</h1></body></html>",
    );

    // PrototypePreview builds a Blob URL + keys the iframe on it (one effect tick) —
    // poll for the iframe rather than asserting synchronously.
    await expect(dashboard.prototypeIframe()).toBeVisible({ timeout: 10000 });
  });

  // Title kept (renames need a migration plan); "Files" is now the Workspace tab.
  test("TS-O-06 the three tabs exist and Files switches content", async ({ dashboard, mockSse }) => {
    await runToComplete(mockSse, "user_stories", SAMPLE_BACKLOG);

    await expect(dashboard.doneBadge()).toBeVisible();
    await dashboard.openPreview();
    // The retired "Files" tab was replaced by "Workspace" (PreviewPanel TAB_CONFIG).
    await expect(dashboard.previewTab()).toBeVisible();
    await expect(dashboard.workspaceTab()).toBeVisible();
    await expect(dashboard.thinkingTab()).toBeVisible();

    // The Preview tab shows the backlog; selecting Workspace swaps it out.
    const backlog = dashboard.page.getByRole("heading", { name: "Product Backlog" });
    await expect(backlog.first()).toBeVisible();
    await dashboard.workspaceTab().click();
    await expect(dashboard.workspaceTab()).toHaveAttribute("aria-selected", "true");
    await expect(backlog).toHaveCount(0);
  });

  test("TS-O-08 run header settles with Share + Download once content is present", async ({ dashboard, mockSse }) => {
    // Phase 39 (RUNUI-06/07): the old header [title="Copy"] icon button was retired
    // with the mock run-header redesign. The run header now settles (data-run-state
    // ="complete") and exposes Share + Download once the deliverable is present.
    await runToComplete(mockSse, "user_stories", SAMPLE_BACKLOG);

    const runHeader = dashboard.page.locator('[data-testid="run-header"]');
    await expect(runHeader).toHaveAttribute("data-run-state", "complete");
    await expect(dashboard.page.getByRole("button", { name: "Share this run" })).toBeVisible();
    await expect(dashboard.page.getByRole("button", { name: /Download the deliverable/ })).toBeVisible();
  });
});
