/**
 * TS-O — PreviewPanel deliverable renderers, dispatched by workflow type.
 * Proves the four bespoke render branches (user_stories backlog, app_builder
 * IDE, od_ppt deck iframe, od_prototype iframe) + the neutral empty state, the
 * three preview tabs, and the header copy affordance.
 *
 * Setup per case: goto + runWith(user_stories framing) → mockWs.start(...) with
 * the case's pipelineType → run agents → mockWs.complete({ pipelineType,
 * finalOutput }). pipeline_start's pipeline_type drives the workflowType sync in
 * DashboardLayout (od_prototype→prototype, od_ppt→ppt, app_builder passthrough),
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
  mockWs: import("../fixtures/mockWs").MockWs,
  pipelineType: keyof typeof AGENTS,
  finalOutput: string,
) {
  const agents = AGENTS[pipelineType];
  mockWs.start(agents, { pipelineType });
  for (const a of agents) await runAgent(mockWs, a.id);
  mockWs.complete({ pipelineType, finalOutput });
}

test.describe("TS-O — deliverable renderers", () => {
  test.beforeEach(async ({ dashboard }) => {
    await dashboard.goto();
    await dashboard.runWith({ workflow: "Generate product requirements", idea: "Refunds backlog" });
  });

  test("TS-O-01 empty preview before completion shows the neutral state", async ({ dashboard, mockWs }) => {
    // Start + run agents but do NOT complete — no deliverable yet.
    const agents = AGENTS.user_stories;
    mockWs.start(agents, { pipelineType: "user_stories" });
    for (const a of agents) await runAgent(mockWs, a.id);

    // Phase 39 redesign: while the run is still in-flight (isRunning) with no
    // content, the preview shows the streaming "Building your deliverable…"
    // placeholder inside PreviewChrome (the neutral "Output will appear here"
    // now only shows for a settled/idle empty run). This is the heir of the
    // pre-completion neutral state.
    await expect(dashboard.page.getByText(/Building your deliverable/)).toBeVisible();
  });

  test("TS-O-02 user_stories renders the Product Backlog with stats", async ({ dashboard, mockWs }) => {
    await runToComplete(mockWs, "user_stories", SAMPLE_BACKLOG);

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

  test("TS-O-03 app_builder renders the file-tree IDE", async ({ dashboard, mockWs }) => {
    await runToComplete(mockWs, "app_builder", SAMPLE_APP_FILES);

    // The IDE chrome appears once ≥1 file parses. Two filename: blocks → "2 files".
    await expect(dashboard.page.getByText(/^\d+ files$/)).toBeVisible();
    await expect(dashboard.page.getByPlaceholder("Search files...")).toBeVisible();
    await expect(dashboard.page.getByRole("button", { name: "Download ZIP" })).toBeVisible();
  });

  test("TS-O-04 od_ppt renders the deck in a sandboxed iframe", async ({ dashboard, mockWs }) => {
    await runToComplete(mockWs, "od_ppt", SAMPLE_DECK);

    await expect(dashboard.deckIframe()).toBeVisible();
  });

  test("TS-O-05 od_prototype renders the prototype iframe", async ({ dashboard, mockWs }) => {
    await runToComplete(
      mockWs,
      "od_prototype",
      "<!DOCTYPE html><html><body><h1>App</h1></body></html>",
    );

    // PrototypePreview builds a Blob URL + keys the iframe on it (one effect tick) —
    // poll for the iframe rather than asserting synchronously.
    await expect(dashboard.prototypeIframe()).toBeVisible({ timeout: 10000 });
  });

  test("TS-O-06 the three tabs exist and Files switches content", async ({ dashboard, mockWs }) => {
    await runToComplete(mockWs, "user_stories", SAMPLE_BACKLOG);

    await expect(dashboard.previewTab()).toBeVisible();
    await expect(dashboard.filesTab()).toBeVisible();
    await expect(dashboard.thinkingTab()).toBeVisible();

    // The Preview tab shows the backlog; the Files tab shows a downloadable file list.
    await expect(dashboard.page.getByRole("heading", { name: "Product Backlog" }).first()).toBeVisible();
    await dashboard.filesTab().click();
    // FilesTab surfaces the user-stories .md → a "{n} file(s) available" header.
    await expect(dashboard.page.getByText(/\d+ files? available/)).toBeVisible();
    await expect(dashboard.page.getByRole("button", { name: "Download All" })).toBeVisible();
  });

  test("TS-O-08 run header settles with Share + Download once content is present", async ({ dashboard, mockWs }) => {
    // Phase 39 (RUNUI-06/07): the old header [title="Copy"] icon button was retired
    // with the mock run-header redesign. The run header now settles (data-run-state
    // ="complete") and exposes Share + Download once the deliverable is present.
    await runToComplete(mockWs, "user_stories", SAMPLE_BACKLOG);

    const runHeader = dashboard.page.locator('[data-testid="run-header"]');
    await expect(runHeader).toHaveAttribute("data-run-state", "complete");
    await expect(dashboard.page.getByRole("button", { name: /Copy a link to this run/ })).toBeVisible();
    await expect(dashboard.page.getByRole("button", { name: /Download the deliverable/ })).toBeVisible();
  });
});
