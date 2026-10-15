/**
 * TS-H — run_pipeline outbound contract + execution transition.
 *
 * Proves the trigger half of the workflow loop: what the app SENDS when the
 * user clicks Run, and that the execution surface swaps in optimistically
 * (before any server event). The inbound→UI mapping is covered by TS-I/TS-Q;
 * here we pin the OUTBOUND frame shape (byte-identical legacy payload) and the
 * synchronous view transition in DashboardLayout.handleRunPipeline.
 *
 * Frame fields are TOP-LEVEL on the parsed outbound object: the app sends
 * JSON.stringify({ type, pipeline_type, message, agent_ids, ... }) and MockSse
 * parses it raw — so assert f.pipeline_type / f.agent_ids / f.message directly.
 */
import { test, expect, DashboardPage } from "../fixtures/test";
import { AGENTS } from "../fixtures/scenarios";
import { installMockApi } from "../fixtures/mockApi";
import { installMockSse } from "../fixtures/mockSse";

test.describe("TS-H — trigger contract", () => {
  test("TS-H-01 run_pipeline payload (minimal) is the byte-identical legacy shape", async ({ dashboard, mockSse }) => {
    // runWith selects "Generate product requirements" (→ user_stories), types the
    // brief, clicks Run, and waits for the outbound run_pipeline frame. No
    // skills / hooks / model-overrides / review-gates are touched anywhere, so
    // the payload must carry ONLY the legacy keys.
    await dashboard.goto();
    await dashboard.runWith({
      workflow: "Generate product requirements",
      idea: "Build a refunds backlog",
    });

    const f = await mockSse.waitForCommand("run_pipeline");

    expect(f.type).toBe("run_pipeline");
    expect(f.pipeline_type).toBe("user_stories");
    // IdeaInputPage sends ideaInput.trim() — assert the exact trimmed brief.
    expect(f.message).toBe("Build a refunds backlog");
    // Default user_stories line-up seeds agents from the library → non-empty.
    expect(Array.isArray(f.agent_ids)).toBe(true);
    expect((f.agent_ids as string[]).length).toBeGreaterThan(0);

    // The legacy contract: with nothing opted into, NONE of the additive
    // capability keys are present on the wire (INV-3 — byte-identical payload).
    expect(f).not.toHaveProperty("attached_skills");
    expect(f).not.toHaveProperty("attached_hooks");
    expect(f).not.toHaveProperty("model_overrides");
    expect(f).not.toHaveProperty("gate_agent_ids");

    // The frame must carry EXACTLY the four legacy keys and nothing else.
    expect(Object.keys(f).sort()).toEqual(["agent_ids", "message", "pipeline_type", "type"]);
  });

  test("TS-H-02 clicking Run swaps to the execution view immediately (pre-event)", async ({ dashboard, mockSse }) => {
    await dashboard.goto();

    // Phase 39: selecting a workflow from home transitions to the "Provide the
    // brief" screen; the brief textarea must be filled only once that heading is
    // visible (else the fill races the still-mounted home composer — the same
    // gotcha DashboardPage.runWith guards against).
    await dashboard.selectWorkflow("Generate product requirements");
    await expect(
      dashboard.page.getByRole("heading", { name: /Provide the brief/i }),
    ).toBeVisible({ timeout: 15000 });
    await dashboard.fillIdea("Build a refunds backlog");
    await expect(dashboard.ideaTextarea()).toBeVisible();

    await expect(dashboard.runButton()).toBeEnabled();
    await dashboard.runButton().click();

    // The transition is OPTIMISTIC: handleRunPipeline sets mainView="execution"
    // synchronously, before onStartPipeline sends the frame and long before any
    // server event. So immediately after the run_pipeline frame lands, the
    // brief-input screen is gone and the run lane is mounted — with NO
    // pipeline_start/agent_* sent yet.
    await mockSse.waitForCommand("run_pipeline");
    await expect(dashboard.page.getByRole("heading", { name: /Provide the brief/i })).toHaveCount(0);
    // Phase 39: the retired AgentProgressPanel "0 / 0 agents" header is replaced by
    // the run lane (RunChatLane) whose header shows the live "Running" status pill
    // even before pipeline_start (isRunning is already true). This is the
    // pre-event marker of the mounted execution surface.
    await expect(dashboard.page.getByTestId("execution-chat-lane")).toBeVisible();
    await expect(dashboard.runningBadge().first()).toBeVisible();

    // Now drive the server: pipeline_start seeds the real cards into the same
    // mounted panel, confirming the execution surface is live.
    mockSse.start(AGENTS.user_stories, { pipelineType: "user_stories" });
    await expect(dashboard.agentCardByName("Domain Discovery Agent").first()).toBeVisible();
    await expect(dashboard.page.getByRole("heading", { name: /Provide the brief/i })).toHaveCount(0);
  });

  test("TS-H-04 pipeline_start seeds exactly the sent cards; currentAgentIndex starts at 0", async ({ dashboard, mockSse }) => {
    await dashboard.goto();
    await dashboard.runWith({
      workflow: "Generate product requirements",
      idea: "Build a refunds backlog",
    });

    const agents = AGENTS.user_stories; // exactly 3
    expect(agents).toHaveLength(3);
    mockSse.start(agents, { pipelineType: "user_stories" });

    // Exactly those 3 agent names render as cards.
    for (const a of agents) {
      await expect(dashboard.agentCardByName(a.name).first()).toBeVisible();
    }

    // currentAgentIndex starts at 0 → the FIRST agent can transition to RUNNING.
    // (agent_start only flips a card it can find at its seeded index; the seed
    // sets currentAgentIndex:0, so the head-of-line agent driving RUNNING proves
    // the index contract.)
    mockSse.agentStart(agents[0].id);
    await expect(dashboard.runningBadge().first()).toBeVisible();
  });

  // TS-H-05 — the wizard path (prototype/ppt) launch contract.
  //
  // From home these rows router.push to /create/{prototype,ppt} (the [...view]
  // catch-all's wizardMode branch) instead of opening IdeaInputPage. The launch is a three-hop
  // hand-off, and this test drives every hop with the seeded Configure registries
  // (dashboard.seedConfigure → DEFAULT_PROTOTYPE_TEMPLATES / DEFAULT_DESIGN_SYSTEMS
  // / DEFAULT_PPT_TEMPLATES):
  //   1. LaunchWizard.handleLaunch (LaunchWizard.tsx:985-1039) serializes the
  //      selection via buildLaunchDraft (lib/launchDraft.ts) into sessionStorage
  //      `{prototype,ppt}.draft` + `{prototype,ppt}.pending`, then pushes /dashboard.
  //   2. The dashboard page consumes the pending draft once the run connection is
  //      ready ([...view]/page.tsx:2463-2547 prototype, :2551-2627 ppt) and clears
  //      both keys.
  //   3. DashboardLayout's launch-consumer effects build the extraParams
  //      (DashboardLayout.tsx:1367-1386 prototype, :1438-1450 ppt) and call
  //      onStartPipeline → useWorkflow merges them TOP-LEVEL onto the
  //      run_pipeline body (useWorkflow.ts:83-122) → POST /api/runs.
  test("TS-H-05 wizard path sends prototype/ppt + template_id", async ({ dashboard, mockSse, page, context, tier }) => {
    const isRunPipeline = (pt: string) => (c: Record<string, unknown>) =>
      c.type === "run_pipeline" && c.pipeline_type === pt;
    // Two full wizard round-trips (home → wizard → home, ×2), each on its own tab.
    test.setTimeout(120_000);

    // Registries must be seeded BEFORE goto (the wizard lists them on mount).
    dashboard.seedConfigure();
    await dashboard.goto();

    // ── prototype: template + design system (DS is REQUIRED for web) ─────────
    const protoBrief = "A kanban board for a 5-person growth squad";
    await dashboard.selectWorkflow("Build an interactive prototype");
    // routes.createPrototype() (lib/routes.ts:65) — served by the [...view] catch-all.
    await page.waitForURL(/\/create\/prototype(\?|$)/);
    await expect(page.getByRole("heading", { name: "Configure your prototype" })).toBeVisible({ timeout: 15000 });

    await page.getByRole("textbox", { name: "Brief", exact: true }).fill(protoBrief);

    // Template step: a card opens TemplateDetailModal; "Use this template" selects.
    await page.getByRole("button", { name: /SaaS analytics dashboard/ }).first().click();
    const tplDialog = page.getByRole("dialog");
    await tplDialog.getByRole("button", { name: "Use this template" }).click();
    await expect(tplDialog).toHaveCount(0);

    // Design System step: the band-card corner toggle drives onSelect(id).
    await page.getByRole("button", { name: "Next", exact: true }).click();
    await page.getByRole("button", { name: "Select Velocity Motors" }).click();
    await expect(page.getByRole("button", { name: "Deselect Velocity Motors" })).toBeVisible();

    const protoContinue = page.getByRole("button", { name: "Continue", exact: true });
    await expect(protoContinue).toBeEnabled();
    await protoContinue.click();
    await page.waitForURL(/\/dashboard/);

    const proto = await mockSse.waitForCommand(isRunPipeline("prototype"), 20000);
    expect(proto.pipeline_type).toBe("prototype");
    expect(proto.message).toBe(protoBrief);
    expect(proto.template_id).toBe("saas-dashboard");
    expect(proto.design_system_id).toBe("velocity-motors");
    // The staged hand-off was consumed (page.tsx:2509-2511) — a reload must not relaunch.
    expect(
      await page.evaluate(() => [sessionStorage.getItem("prototype.pending"), sessionStorage.getItem("prototype.draft")]),
    ).toEqual([null, null]);

    // One launch per wizard Continue — no double-mint (BUG-007 latch).
    expect(mockSse.framesOfType("run_pipeline").filter(isRunPipeline("prototype"))).toHaveLength(1);

    // ── ppt: template only (exec-pitch declares design_system.requires=false) ─
    // Driven on a FRESH tab with its OWN mock backend. HARNESS NOTE: once the
    // prototype launch lands, the mock lists that run as "running" on every
    // GET /api/runs and holds its frame-less stream response open (no headers
    // until a frame), so the provider sits in phase "connecting" — and the
    // wizard consumer only fires on a phase that maps to "connected"
    // ([...view]/page.tsx:62-77, :2464). A second launch on the same tab would
    // therefore test that mock artifact, not the ppt contract. The fresh tab
    // gives the deck launch the same clean starting state the prototype had.
    const deckPage = await context.newPage();
    const deckApi = await installMockApi(deckPage, { user: { tier } });
    const deckSse = await installMockSse(deckPage, deckApi);
    const deck = new DashboardPage(deckPage, deckSse, deckApi);
    deck.seedConfigure();
    await deck.goto();

    const pptBrief = "A pitch deck for our Series A fundraise";
    await deck.selectWorkflow("Pitch an idea");
    await deckPage.waitForURL(/\/create\/ppt(\?|$)/); // routes.createPpt() (lib/routes.ts:63)
    await expect(deckPage.getByRole("heading", { name: "Configure your presentation" })).toBeVisible({ timeout: 15000 });

    await deckPage.getByRole("textbox", { name: "Brief", exact: true }).fill(pptBrief);
    await deckPage.getByRole("button", { name: /Executive pitch/ }).first().click();
    // The PPT detail modal carries no role="dialog" (PPTTemplateGallery.tsx:415),
    // so target its select button directly — it only exists while the modal is open.
    const useDeckTemplate = deckPage.getByRole("button", { name: "Use this template", exact: true });
    await useDeckTemplate.click();
    await expect(useDeckTemplate).toHaveCount(0);

    const pptContinue = deckPage.getByRole("button", { name: "Continue", exact: true });
    await expect(pptContinue).toBeEnabled();
    await pptContinue.click();
    await deckPage.waitForURL(/\/dashboard/);

    const ppt = await deckSse.waitForCommand(isRunPipeline("ppt"), 20000);
    expect(ppt.pipeline_type).toBe("ppt");
    expect(ppt.message).toBe(pptBrief);
    expect(ppt.template_id).toBe("exec-pitch");
    // A template that does not require a DS sends NO design_system_id
    // (LaunchWizard.tsx:999 nulls it; DashboardLayout.tsx:1439 omits a null).
    expect(ppt).not.toHaveProperty("design_system_id");
    expect(
      await deckPage.evaluate(() => [sessionStorage.getItem("ppt.pending"), sessionStorage.getItem("ppt.draft")]),
    ).toEqual([null, null]);
    expect(deckSse.framesOfType("run_pipeline").filter(isRunPipeline("ppt"))).toHaveLength(1);

    await deckPage.close();
  });
});
