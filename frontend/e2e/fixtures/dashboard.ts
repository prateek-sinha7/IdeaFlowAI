/**
 * Page object for the Flowin dashboard (the single-page view state machine).
 * Encapsulates navigation (home → input → execution) and the load-bearing
 * locators so specs stay DRY and consistent. The app ships almost no
 * data-testid, so locators are text/role/title based (see TEST-REGISTER §1.5).
 */
import type { Page, Locator } from "@playwright/test";
import { expect } from "@playwright/test";
import type { MockSse } from "./mockSse";
import type { MockApi, Tier } from "./mockApi";
import {
  DEFAULT_USER_WORKFLOWS, SEEDED_HISTORY_RUNS, SEEDED_ANALYTICS, seededHistoryFamily,
  DEFAULT_PROTOTYPE_TEMPLATES, DEFAULT_DESIGN_SYSTEMS, DEFAULT_PPT_TEMPLATES,
} from "./mockApi";
import { TOKEN_KEY, TEST_JWT } from "./constants";

/** One durable run_events row served by `stubRunEvents` — the wire shape of
 *  GET /api/runs/{id}/events (runs.py:897-908). `payload_json` should carry the
 *  frame's own `event_id`/`seq` (the same keys the page router + useRunChat dedup
 *  on), since `getRunEvents` maps each row to `{ type, data: payload_json }`. */
export interface StubRunEventRow {
  seq: number;
  event_id: string;
  type: string;
  payload_json: Record<string, unknown>;
}

export class DashboardPage {
  constructor(readonly page: Page, readonly sse: MockSse, readonly api: MockApi) {}

  // ── navigation ──────────────────────────────────────────────────────────────

  /**
   * OPT-IN shell-capture seeding (Phase 40 / SHELL-04). Installs representative
   * saved-workflow / history / analytics data into the MockApi so the Catalogue,
   * Run History, Analytics and Home "Jump back in" recents render POPULATED for a
   * fair fidelity diff. Call BEFORE `goto()`. NOT production data — the DEFAULT
   * MockApi stays empty so no other spec regresses (ND-D / SC-001).
   */
  seedShell() {
    this.api.setUserWorkflows(DEFAULT_USER_WORKFLOWS);
    this.api.setRuns(SEEDED_HISTORY_RUNS);
    this.api.setAnalytics(SEEDED_ANALYTICS);
    this.api.setFamily(seededHistoryFamily);
    return this;
  }

  /**
   * OPT-IN Configure-capture seeding (Phase 41 / HARN-01). Installs
   * representative template / design-system / ppt-template rows so the Configure
   * Templates + Design-System accordions/overlays render POPULATED for a fair
   * fidelity diff. Call BEFORE `goto()`. NOT production data — the DEFAULT MockApi
   * registries stay empty so no other spec regresses (ND-D / SC-001). Separate
   * from seedShell() so a spec can opt into either independently.
   */
  seedConfigure() {
    this.api.setPrototypeTemplates(DEFAULT_PROTOTYPE_TEMPLATES);
    this.api.setDesignSystems(DEFAULT_DESIGN_SYSTEMS);
    this.api.setPPTTemplates(DEFAULT_PPT_TEMPLATES);
    return this;
  }

  /** Seed an auth token (mocked mode) then open the dashboard at `home`. */
  async goto(opts: { tier?: Tier } = {}) {
    if (opts.tier) this.api.setUser({ tier: opts.tier });
    await this.page.addInitScript(([k, t]) => localStorage.setItem(k, t), [TOKEN_KEY, TEST_JWT]);
    // KAN-125: a spec that emits WITHOUT launching relies on the lazy attach;
    // the page only honours frames for runs in its mount-time tab allow-list.
    if (this.sse.autoAttach) await this.sse.seedTabOwnership();
    await this.page.goto("/dashboard");
    await expect(this.homeHeading()).toBeVisible({ timeout: 15000 });
    // SSE is the sole transport (44-06): the app attaches a run's stream only once
    // a run is live (boot GET /api/runs non-terminal, or attachRun after launch) —
    // there is no always-open socket to await here. The mock's lazy attach wires
    // the stream when the spec launches (runWith) or emits (mockSse.start).
  }

  homeHeading(): Locator {
    return this.page.getByRole("heading", { name: "What would you like to build today?" });
  }

  // ── history-open helpers (DEF-44-12-4) ───────────────────────────────────────

  /**
   * Open the Run History list via the AppHeader profile dropdown (lifted from
   * ts-t.history.spec.ts so specs stop duplicating it). NB: the Run History LIST
   * reopen renders WorkflowHistory's OWN RunDetailPage — it does NOT go through
   * page.tsx's handleSelectWorkflowRun, so it does NOT seed the execution-lane
   * pipeline/transcript. Use `openRecent(...)` for the seed path.
   */
  async openHistory() {
    const headerButtons = this.page.locator("header button");
    await headerButtons.last().click();
    await this.page.getByRole("menuitem", { name: "Run History" }).click();
    await expect(this.page.getByRole("heading", { name: "Run History" })).toBeVisible();
  }

  /**
   * Open a run from the Home "Jump back in" recents strip. This is the deep-link
   * that fires page.tsx's `handleSelectWorkflowRun` (onOpenRun → onSelectWorkflowRun
   * → setMainView("execution")) — the path that seeds the run-screen live state
   * (Steps trace + transcript) for the VIEWED run (DEF-44-12-4). The recents strip
   * is populated from GET /api/runs, so seed the run via `mockApi.setRuns([...])`
   * BEFORE `goto()`.
   */
  async openRecent(title: string) {
    await expect(this.page.getByText("Jump back in")).toBeVisible({ timeout: 15000 });
    await this.page.getByRole("button").filter({ hasText: title }).first().click();
  }

  /**
   * Stub the durable, NON-stream events endpoint GET /api/runs/{id}/events?after=N
   * (distinct from the mockSse `/events/stream` down-channel). The shared mockApi
   * catch-all otherwise returns `{}`. Registered per-test so it wins (LIFO) over
   * mockSse's `**​/api/runs**` route, and the RegExp deliberately does NOT match
   * `/events/stream` (events must be followed by `?` or end-of-URL). Honors the
   * `after` cursor (returns only rows with `seq > after`) so a seed fetch (after=0)
   * and a re-fetch-after-send (after=lastSeq) get the right slice — and the caller
   * can MUTATE the passed `events` array between the two (e.g. push a Concierge
   * reply after opening) to model a durable row that lands only post-send.
   */
  async stubRunEvents(runId: string, events: StubRunEventRow[]) {
    await this.page.route(/\/api\/runs\/[^/]+\/events(\?|$)/, async (route) => {
      const url = new URL(route.request().url());
      const after = Number(url.searchParams.get("after") ?? 0) || 0;
      const slice = events.filter((e) => e.seq > after);
      await route.fulfill({ json: { workflow_id: runId, after, events: slice } });
    });
  }

  /** Click a CreationHub workflow row by its H2 label. */
  async selectWorkflow(label: string) {
    const before = new URL(this.page.url()).pathname;
    await this.page.getByRole("button", { name: new RegExp(label, "i") }).first().click();
    // 015-frontend-routing: the card swaps the view optimistically, then the URL
    // commit (/create/{type}, /workflows/new) remounts the screen — settle on the
    // new route so a subsequent fill is not wiped by that remount.
    await this.page.waitForURL((u) => u.pathname !== before, { waitUntil: "commit" });
  }

  ideaTextarea(): Locator {
    return this.page.locator("textarea").first();
  }

  async fillIdea(text: string) {
    await this.ideaTextarea().fill(text);
  }

  runButton(): Locator {
    return this.page.getByRole("button", { name: /Run workflow|Add agents first|Pick a migration path/ });
  }

  /** Select a workflow from home, land on the "Provide the brief" screen, type
   *  the brief AFTER it mounts, click Run, and (default) wait for the outbound
   *  run_pipeline frame. Leaves the app on the execution view.
   *
   *  The home deliverable row → brief-screen navigation is a real transition: the
   *  textarea must be filled only once "Provide the brief" is visible, else the
   *  fill races the still-mounted home composer and lands in the wrong field. */
  async runWith(opts: { workflow?: string; idea: string; waitForFrame?: boolean }) {
    if (opts.workflow) await this.selectWorkflow(opts.workflow);
    await expect(
      this.page.getByRole("heading", { name: /Provide the brief/i }),
    ).toBeVisible({ timeout: 15000 });
    const brief = this.ideaTextarea();
    await brief.click();
    await brief.fill(opts.idea);
    await expect(this.runButton()).toBeEnabled({ timeout: 10000 });
    const fetchesBefore = this.sse.eventsFetchCount;
    await this.runButton().click();
    // The app launches over REST (POST /api/runs, body { type:"run_pipeline", … });
    // wait for the recorded up-channel command instead of a WS frame.
    if (opts.waitForFrame !== false) {
      await this.sse.waitForCommand("run_pipeline", 20000);
      // 015-frontend-routing: the launch pushes /runs/{id}/stream, which remounts
      // the run screen — settle there before the spec drives the run.
      await this.awaitRunRoute();
      await this.awaitRunScreenSettled(fetchesBefore);
    }
  }
  /** After the /runs/{id}/stream remount the run screen resets its state and replays
   *  the durable log (GET /events). Frames pushed before that replay lands can be
   *  overwritten by it, so wait (bounded and tolerant: the app skips the fetch when
   *  it already tracks the run) for the replay fetch to be observed. */
  async awaitRunScreenSettled(fetchesBefore: number) {
    await expect
      .poll(() => this.sse.eventsFetchCount > fetchesBefore, { timeout: 5000 })
      .toBe(true)
      .catch(() => undefined);
  }

  /** Wait until the app sits on the tracked run's own route (/runs/{id}/stream). */
  async awaitRunRoute() {
    await this.page.waitForURL(new RegExp(`/runs/${this.sse.currentRunId}/stream`), { waitUntil: "commit" });
  }

  // ── full-page Composer (mainView="composer") ─────────────────────────────────
  // Since 41-04 (e1490fad) the `custom` workflow ("Compose a custom workflow"
  // card, My Workflows "New workflow", launching a saved custom row) opens the
  // full-page ComposerPage at /workflows/new|/workflows/{id}/run — NOT the
  // IdeaInputPage brief screen. It has no <h1>; these are its role/label anchors.

  /** Open the full-page Composer from Home via the "Compose a custom workflow"
   *  card (FIX-181 retired Home's "Create workflow" button). */
  async openComposer(opts: { view?: "simple" | "canvas" } = {}) {
    await this.goto();
    await this.selectWorkflow("Compose a custom workflow");
    await expect(this.composerEyebrow()).toBeVisible();
    // The composer opens on the Canvas view (ComposerPage default); the Simple
    // view (agent rows + Summary rail) is one toggle away.
    if (opts.view === "simple") {
      await this.page.getByRole("button", { name: "Simple", exact: true }).click();
      await expect(this.page.getByTestId("composer-summary-rail")).toBeVisible();
    }
  }

  /** The Composer header eyebrow ("Custom · Composer") — the composer-mounted signal. */
  composerEyebrow(): Locator {
    return this.page.getByText("Custom · Composer", { exact: true });
  }

  /** The inline workflow-name field (replaces the retired NameWorkflowModal). */
  composerNameInput(): Locator {
    return this.page.getByRole("textbox", { name: "Workflow name" });
  }

  /** The Composer's brief field (Canvas rail / Simple Brief card — one mounts at a time). */
  composerBrief(): Locator {
    return this.page.getByRole("textbox", { name: "Brief description" });
  }

  /** The Composer header's "Run once" launch button. */
  composerRunOnce(): Locator {
    return this.page.getByRole("button", { name: "Run once", exact: true });
  }

  /** The Composer header run summary ("N agents · N review gates · ~est"). */
  composerSummary(): Locator {
    return this.page.getByTestId("composer-header-summary");
  }

  // ── composer / model picker ──────────────────────────────────────────────────

  async openAdvanced() {
    await this.page.getByRole("button", { name: /^Advanced/ }).click();
    // AgentsPopup folded its "Advanced" eyebrow into one h2:
    // "Advanced Workflow Configuration — <workflow label>".
    await expect(this.advancedHeading()).toBeVisible();
  }

  /** The AgentsPopup title (h2 "Advanced Workflow Configuration — …"). */
  advancedHeading(): Locator {
    return this.page.getByRole("heading", { name: /^Advanced Workflow Configuration/ });
  }

  /** A tab in the AgentsPopup header strip ("Agents (N)" / "Workflow"). Scoped to
   *  the strip that holds the Agents tab, so it never resolves the embedded
   *  canvas rail's own "Workflow" / "Agent" toggle. */
  advancedTab(name: string | RegExp): Locator {
    const agentsTab = this.page.getByRole("button", { name: /^Agents \(\d+\)$/ });
    return this.page.locator("div").filter({ has: agentsTab }).last()
      .getByRole("button", { name, exact: typeof name === "string" });
  }

  async openModelPicker() {
    await this.openAdvanced();
    // Agents tab is default; the picker is its footer.
    await expect(this.page.getByText("Per-Agent Model")).toBeVisible();
  }

  // ── execution-view locators ──────────────────────────────────────────────────

  // Run-status badges — Phase 39 run-screen redesign RETIRED the per-agent
  // uppercase RUNNING/DONE/ERROR text badges of the old AgentProgressPanel (that
  // panel is no longer mounted). The run-level status now renders as a single
  // token in the lane run header (LaneRunHeader → StatusToken, testid
  // `lane-run-status`) keyed by a generic `data-status-tone`:
  //   • building/clarify/gate → tone "running"  (pill "Running"/"Clarifying"/…)
  //   • complete / settled    → tone "done"      (token "Done")
  //   • terminal-failed       → tone "failed"    (token "Failed")
  // These are the run-lifecycle heirs of the three badges (whole-run granularity).
  // PER-AGENT state relocated to the Steps tab (see the Steps helpers below).
  runningBadge(): Locator { return this.page.locator('[data-testid="lane-run-status"][data-status-tone="running"]'); }
  doneBadge(): Locator { return this.page.locator('[data-testid="lane-run-status"][data-status-tone="done"]'); }
  errorBadge(): Locator { return this.page.locator('[data-testid="lane-run-status"][data-status-tone="failed"]'); }
  stopButton(): Locator { return this.page.getByRole("button", { name: "Stop" }); }

  /** An agent card by its display name (the lane's PipelineMini rows / Steps spine). */
  agentCardByName(name: string): Locator { return this.page.getByText(name, { exact: false }); }

  // ── Steps tab · per-agent panels (Phase 39 relocated the AgentProgressPanel
  //    per-agent detail into the Steps drill-down: L1 StepsOverviewSpine spine →
  //    L2 AgentDetailPanel). Open the tab, then use these to assert per-agent
  //    state that used to live in the run-lane badges. ──────────────────────────
  async openSteps() {
    // Robust against the Phase 42-02 state-keyed auto-tab: a Steps click can race
    // an in-flight run-state transition (building/complete) whose auto-tab clobbers
    // it. Re-click until Steps is the selected tab (the auto-tab latch fires once
    // per state, so a re-click after it fires sticks). NB: a run that will SETTLE
    // to a deliverable auto-tabs to Preview — read Steps content only after the run
    // has settled (await stopButton().toHaveCount(0)) so the terminal auto-tab has
    // already fired before this call.
    await expect(async () => {
      await this.thinkingTab().click();
      await expect(this.thinkingTab()).toHaveAttribute("aria-selected", "true", { timeout: 1000 });
    }).toPass({ timeout: 15000 });
  }

  /** Re-select the Preview tab until it sticks (mirror of openSteps): a terminal
   *  auto-tab or a late replay can clobber a single click. Call after the run is Done. */
  async openPreview() {
    await expect(async () => {
      await this.previewTab().click();
      await expect(this.previewTab()).toHaveAttribute("aria-selected", "true", { timeout: 1000 });
    }).toPass({ timeout: 15000 });
  }
  /** Wait until the live run has SETTLED (Stop gone → isRunning=false). Use before
   *  reading a settled-run surface so any terminal auto-tab has already fired. */
  async waitForRunSettled() {
    await expect(this.stopButton()).toHaveCount(0, { timeout: 15000 });
  }

  /** A Steps L1 spine row for an agent, by its display name. */
  stepsAgentRow(name: string): Locator {
    return this.page.getByTestId("steps-agent-row").filter({ hasText: name });
  }

  /** The per-agent RUNNING signal in the spine — one per running agent. Phase 42
   *  REMOVED the spine's "Live" text pill (it now lives ONLY in the L2 agent-detail
   *  header); a running spine row is instead marked by its violet highlight + a
   *  pulsing brand dot (StepsOverviewSpine running node). This locator counts the
   *  running rows via that reskin-durable pulse indicator, preserving the old
   *  "how many agents are live" semantics the callers assert on. */
  stepsLiveBadge(): Locator {
    return this.page
      .getByTestId("steps-agent-row")
      .filter({ has: this.page.locator("span.animate-pulse") });
  }

  /** The Steps L1 segmented progress track (one segment per agent). */
  stepsProgressTrack(): Locator {
    return this.page.locator("div.h-\\[5px\\]").first();
  }

  /** Drill into an agent's L2 detail (AgentDetailPanel) by clicking its spine row. */
  async openAgentDetail(name: string) { await this.stepsAgentRow(name).click(); }

  // "Waves & tasks" (the wave step's L2 detail — WaveWorkersBlock). A wave fan-out
  // is drawn from the step's stamped worker events (agent_start/agent_complete +
  // task_id); the "Construction" block is reserved for task_loop progress and is
  // withdrawn when it has nothing to draw.
  waveBlock(): Locator { return this.page.getByTestId("wave-workers-block"); }
  waveHeading(): Locator { return this.waveBlock().getByText("Waves & tasks", { exact: true }); }
  waveGroup(index: number): Locator { return this.page.locator(`[data-testid="wave-section"][data-wave-index="${index}"]`); }

  // preview
  previewEmpty(): Locator { return this.page.getByText("Output will appear here"); }
  degradedHeading(): Locator { return this.page.getByText("This run did not complete successfully"); }
  cancelledHeading(): Locator { return this.page.getByText("This run was cancelled"); }
  failedAgentsLabel(): Locator { return this.page.getByText("Failed agents"); }
  genericIframe(): Locator { return this.page.locator('iframe[title="Deliverable Preview"]'); }
  deckIframe(): Locator { return this.page.locator('iframe[title="Slide Deck Preview"]'); }
  prototypeIframe(): Locator { return this.page.locator('iframe[title="Prototype Preview"]'); }

  // tabs
  // Phase 39 redesigned right-panel tabs are the Tabs primitive (role="tab");
  // labels may carry a count (e.g. "Files 8"), so match by regex like thinkingTab.
  previewTab(): Locator { return this.page.getByRole("tab", { name: /Preview/i }); }
  /** The Workspace tab — replaced the retired "Files" tab in the panel tab strip
   *  (PreviewPanel TAB_CONFIG: Preview · Steps · Workspace · Audit). */
  workspaceTab(): Locator { return this.page.getByRole("tab", { name: /Workspace/i }); }
  /** The Steps tab (Phase 32 relabelled the old "Thinking" tab to "Steps"; the
   *  Phase-39 redesign made the tab strip role="tab"). */
  thinkingTab(): Locator { return this.page.getByRole("tab", { name: /Steps/i }); }

  // questionnaire / gates
  questionnaireTitle(): Locator { return this.page.getByRole("heading", { name: "Quick Setup" }); }
  reviewGateTitle(name: "Specification Review" | "Task Plan Review"): Locator { return this.page.getByText(name); }
  approveButton(): Locator { return this.page.getByRole("button", { name: /Approve.*continue/ }); }
  rejectButton(): Locator { return this.page.getByRole("button", { name: "Reject & cancel pipeline" }); }
}
