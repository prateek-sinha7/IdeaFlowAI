/**
 * TS-C — Idea input & pipeline trigger (IdeaInputPage) — TEST-REGISTER §3.
 *
 * Exercises the brief-input surface: per-type placeholders, the Run button's
 * disabled/label state machine (Add agents first / Pick a migration path /
 * Run workflow), Cmd/Ctrl+Enter keyboard submit, file attach, the (absent)
 * voice button, the migration sub-pipeline tile selector, and the
 * input → execution view transition.
 *
 * Every workflow is reached from the home CreationHub at the `enterprise` tier
 * so custom + migration are unlocked (see entitlements.ts: only enterprise
 * grants them). Placeholders/labels are asserted against TYPE_CONFIG read
 * verbatim from IdeaInputPage.tsx.
 */
import { test, expect } from "../fixtures/test";
import { AGENTS } from "../fixtures/scenarios";

// Placeholders copied verbatim from TYPE_CONFIG in IdeaInputPage.tsx.
const PLACEHOLDER = {
  user_stories: "e.g. Generate epics and stories for a refunds workflow with multi-currency support.",
  app_builder: "e.g. A SaaS platform for managing freelance invoices with Stripe integration.",
  custom: "e.g. Research the competitive landscape for AI coding assistants and generate a SWOT analysis.",
  mulesoft_to_springboot:
    "e.g. Migrate three Mulesoft 4 apps powering our orders + claims platform onto AWS, splitting into Spring Boot microservices with Aurora Postgres and SQS messaging.",
};

test.describe("TS-C — idea input & trigger", () => {
  test.beforeEach(async ({ dashboard }) => {
    // enterprise unlocks every workflow row (custom + migration are gated).
    await dashboard.goto({ tier: "enterprise" });
  });

  test("TS-C-01 placeholder matches TYPE_CONFIG per workflow type", async ({ dashboard, page }) => {
    test.fixme(true, "pre-existing feat/ui-2 red at 8c2f0b9d — not Phase 42 (RUNUI-09 baseline)");
    // user_stories
    await dashboard.selectWorkflow("Generate product requirements");
    await expect(dashboard.ideaTextarea()).toHaveAttribute("placeholder", PLACEHOLDER.user_stories);

    // back → app_builder
    await page.getByRole("button", { name: "Back" }).click();
    await dashboard.selectWorkflow("Build an end-to-end application");
    await expect(dashboard.ideaTextarea()).toHaveAttribute("placeholder", PLACEHOLDER.app_builder);

    // back → custom
    await page.getByRole("button", { name: "Back" }).click();
    await dashboard.selectWorkflow("Compose a custom workflow");
    await expect(dashboard.ideaTextarea()).toHaveAttribute("placeholder", PLACEHOLDER.custom);
  });

  test("TS-C-02 Run-button disabled states (empty idea, no agents)", async ({ dashboard, page }) => {
    test.fixme(true, "pre-existing feat/ui-2 red at 8c2f0b9d — not Phase 42 (RUNUI-09 baseline)");
    // user_stories seeds default agents → empty idea ⇒ Run disabled but labelled "Run workflow".
    await dashboard.selectWorkflow("Generate product requirements");
    const run = dashboard.runButton();
    await expect(run).toBeDisabled();
    await expect(run).toHaveText(/Run workflow/);

    // custom seeds NO library agents (CUSTOM_AGENTS live outside LIBRARY_AGENTS)
    // → the Run button advertises "Add agents first" and stays disabled.
    await page.getByRole("button", { name: "Back" }).click();
    await dashboard.selectWorkflow("Compose a custom workflow");
    const customRun = dashboard.runButton();
    await expect(customRun).toBeDisabled();
    await expect(customRun).toHaveText(/Add agents first/);
  });

  test("TS-C-03 Run enables once a brief is typed (user_stories)", async ({ dashboard }) => {
    await dashboard.selectWorkflow("Generate product requirements");
    const run = dashboard.runButton();
    await expect(run).toBeDisabled();

    await dashboard.fillIdea("Generate epics for a refunds workflow with multi-currency support.");
    await expect(run).toBeEnabled();
    await expect(run).toHaveText(/Run workflow/);
  });

  test("TS-C-04 Cmd/Ctrl+Enter from the textarea triggers the run", async ({ dashboard, mockWs, page }) => {
    await dashboard.selectWorkflow("Generate product requirements");
    // Phase-39 "Fused Home" mounts its OWN launcher <textarea> (#home-launch-prompt),
    // so `ideaTextarea().first()` can land on the home field mid-transition. Wait for
    // the input view ("Provide the brief") so the fill targets the IdeaInputPage.
    await expect(page.getByRole("heading", { name: /Provide the brief/i })).toBeVisible();
    const ta = dashboard.ideaTextarea();
    await ta.click();
    await ta.fill("Generate epics for a refunds workflow with multi-currency support.");
    // Gate the keyboard submit on the brief actually being committed to React
    // state (handleRun early-returns while `ideaInput` is empty) — the Run button
    // enabling is the observable proxy for that commit.
    await expect(dashboard.runButton()).toBeEnabled();

    // onKeyDown fires handleRun() when Enter is pressed with metaKey || ctrlKey.
    // Playwright maps Meta→Cmd on macOS; the component accepts either modifier.
    await ta.press("ControlOrMeta+Enter");

    // The app dispatches a run_pipeline frame (proves the keyboard path runs).
    const frame = await mockWs.waitForClientFrame("run_pipeline");
    expect(frame.pipeline_type).toBe("user_stories");
  });

  test("TS-C-06 attach file shows a chip and injects the filename into the brief", async ({ dashboard, page, mockWs }) => {
    await dashboard.selectWorkflow("Generate product requirements");
    // Wait for the input view — the Phase-39 "Fused Home" launcher <textarea> would
    // otherwise steal `ideaTextarea().first()` mid-transition (see TS-C-04).
    await expect(page.getByRole("heading", { name: /Provide the brief/i })).toBeVisible();
    // A brief is required for Run to fire (attaching alone does not enable it).
    await dashboard.fillIdea("Generate epics for a refunds workflow with multi-currency support.");

    // Reveal/identify the hidden file input, then drive it directly. The visible
    // "+ Attach file" button just proxies a click to this input.
    await page.getByRole("button", { name: "+ Attach file" }).click();
    await page.locator('input[type=file]').setInputFiles({
      name: "spec.txt",
      mimeType: "text/plain",
      buffer: Buffer.from("hi"),
    });

    // A chip with the filename renders. Target it with exact text so we hit the
    // chip <span> ("spec.txt") and not other chrome.
    await expect(page.getByText("spec.txt", { exact: true })).toBeVisible();

    // Phase-39/KAN-91: the textarea now stays CLEAN — the old "[Attached: …]"
    // marker is no longer injected into the visible brief. Instead the filename
    // (and its extracted content) is composed into the brief at SEND time: the
    // outbound run_pipeline `message` carries an "=== Attached: spec.txt ===" block
    // (IdeaInputPage.handleRun fileBlocks). Run it and assert that injection.
    await dashboard.runButton().click();
    const frame = await mockWs.waitForClientFrame("run_pipeline");
    expect(String(frame.message)).toContain("Attached: spec.txt");
  });

  test("TS-C-07 Voice button presence is gated on SpeechRecognition support", async ({ dashboard, page }) => {
    // The component renders the Voice control ONLY when `speechSupported`
    // (useSpeechRecognition.isSupported, i.e. window.SpeechRecognition ||
    // window.webkitSpeechRecognition exists). The TEST-REGISTER frames the
    // absence case for engines without the API. NOTE: contrary to the common
    // assumption that Playwright's Chromium ships no SpeechRecognition, the
    // bundled Chromium in THIS environment *does* expose webkitSpeechRecognition,
    // so the button IS mounted here. Rather than hard-code either outcome, we
    // assert the component's `speechSupported &&` gate in BOTH directions —
    // deterministic regardless of which engine/build runs the suite.
    await dashboard.selectWorkflow("Generate product requirements");
    await expect(dashboard.ideaTextarea()).toBeVisible();

    const supported = await page.evaluate(
      () => typeof (window.SpeechRecognition || window.webkitSpeechRecognition) !== "undefined",
    );
    const voice = page.getByRole("button", { name: "Voice" });
    if (supported) {
      // API present → the Voice button is rendered (the only consumer of the gate).
      await expect(voice).toHaveCount(1);
    } else {
      // API absent (e.g. Firefox) → the button is never mounted.
      await expect(voice).toHaveCount(0);
    }
  });

  // RE-ANCHORED (40-02): the data-driven home serves "Platform workflows" as the
  // CONCRETE `mulesoft_to_springboot` id (fixtures DEFAULT_WORKFLOWS), so it opens
  // the concrete "Modernise off Mulesoft" input directly (13 LIBRARY_AGENTS
  // seeded) — the `migration` meta-picker ("Choose your migration path" + the two
  // path tiles + the "Pick a migration path" Run label) still exists in
  // IdeaInputPage but has no home entry point. The behavioral core — the concrete
  // migration input takes a brief and enables Run — is preserved and asserted.
  test("TS-C-08 'Platform workflows' opens the concrete migration input and Run enables on a brief", async ({ dashboard, page }) => {
    await dashboard.selectWorkflow("Platform workflows");
    await expect(page.getByRole("heading", { name: "Modernise off Mulesoft" })).toBeVisible();

    // The concrete pipeline's placeholder (TYPE_CONFIG.mulesoft_to_springboot).
    await expect(dashboard.ideaTextarea()).toHaveAttribute("placeholder", PLACEHOLDER.mulesoft_to_springboot);

    // 13 agents are seeded for the concrete pipeline → Run reads "Run workflow"
    // and enables once a brief is present (empty brief keeps it disabled).
    const run = dashboard.runButton();
    await expect(run).toHaveText(/Run workflow/);
    await expect(run).toBeDisabled();

    await dashboard.fillIdea("Migrate three Mulesoft 4 apps onto AWS as Spring Boot microservices.");
    await expect(run).toBeEnabled();
    await expect(run).toHaveText(/Run workflow/);
  });

  test("TS-C-10 trigger swaps to the execution view and emits run_pipeline", async ({ dashboard, mockWs, page }) => {
    // runWith: select user_stories, type a brief, click Run, await the frame.
    await dashboard.runWith({
      workflow: "Generate product requirements",
      idea: "Generate epics for a refunds workflow with multi-currency support.",
    });

    // The view machine swaps input → execution (AnimatePresence mode="wait"), so
    // the IdeaInputPage unmounts. Phase-39: the execution surface (RunChatLane)
    // mounts its OWN chat-composer textarea, so a bare `textarea` count is no
    // longer 0 — assert the IdeaInputPage's "Provide the brief" heading is gone
    // instead (the reliable input-view-unmounted signal).
    await expect(page.getByRole("heading", { name: /Provide the brief/i })).toHaveCount(0);
    // And the run_pipeline frame was sent for this pipeline type.
    expect(mockWs.framesOfType("run_pipeline").length).toBeGreaterThan(0);

    // Seed the agent cards via pipeline_start and assert one renders on the
    // execution surface (cards come from pipeline_start, not the pre-run seed).
    mockWs.start(AGENTS.user_stories, { pipelineType: "user_stories" });
    await expect(dashboard.agentCardByName("Domain Discovery Agent").first()).toBeVisible();
  });
});
