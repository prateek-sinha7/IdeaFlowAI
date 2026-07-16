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
    await this.page.getByRole("button", { name: new RegExp(label, "i") }).first().click();
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
    await this.runButton().click();
    // The app launches over REST (POST /api/runs, body { type:"run_pipeline", … });
    // wait for the recorded up-channel command instead of a WS frame.
    if (opts.waitForFrame !== false) await this.sse.waitForCommand("run_pipeline", 20000);
  }

  // ── composer / model picker ──────────────────────────────────────────────────

  async openAdvanced() {
    await this.page.getByRole("button", { name: /^Advanced/ }).click();
    await expect(this.page.getByText("Workflow configuration")).toBeVisible();
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

  // Construction · waves & subagents (the Build Agent's L2 detail — Phase 39 plan
  // 02: the former standalone WaveTreePanel is now ONE integrated block with build
  // tasks NESTED under their waves; waves display 1-based to match the mock).
  waveHeading(): Locator { return this.page.getByText(/Construction · waves/); }
  waveEmpty(): Locator { return this.page.getByTestId("construction-empty"); }
  waveGroup(index: number): Locator { return this.page.getByText(new RegExp(`^Wave ${index + 1}$`)); }

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
  filesTab(): Locator { return this.page.getByRole("tab", { name: /Files/i }); }
  /** The Steps tab (Phase 32 relabelled the old "Thinking" tab to "Steps"; the
   *  Phase-39 redesign made the tab strip role="tab"). */
  thinkingTab(): Locator { return this.page.getByRole("tab", { name: /Steps/i }); }

  // questionnaire / gates
  questionnaireTitle(): Locator { return this.page.getByRole("heading", { name: "Quick Setup" }); }
  reviewGateTitle(name: "Specification Review" | "Task Plan Review"): Locator { return this.page.getByText(name); }
  approveButton(): Locator { return this.page.getByRole("button", { name: /Approve.*continue/ }); }
  rejectButton(): Locator { return this.page.getByRole("button", { name: "Reject & cancel pipeline" }); }
}
