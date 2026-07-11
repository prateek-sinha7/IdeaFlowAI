/**
 * Page object for the Flowin dashboard (the single-page view state machine).
 * Encapsulates navigation (home → input → execution) and the load-bearing
 * locators so specs stay DRY and consistent. The app ships almost no
 * data-testid, so locators are text/role/title based (see TEST-REGISTER §1.5).
 */
import type { Page, Locator } from "@playwright/test";
import { expect } from "@playwright/test";
import type { MockWs } from "./mockWs";
import type { MockApi, Tier } from "./mockApi";
import { TOKEN_KEY, TEST_JWT } from "./constants";

export class DashboardPage {
  constructor(readonly page: Page, readonly ws: MockWs, readonly api: MockApi) {}

  // ── navigation ──────────────────────────────────────────────────────────────

  /** Seed an auth token (mocked mode) then open the dashboard at `home`. */
  async goto(opts: { tier?: Tier } = {}) {
    if (opts.tier) this.api.setUser({ tier: opts.tier });
    await this.page.addInitScript(([k, t]) => localStorage.setItem(k, t), [TOKEN_KEY, TEST_JWT]);
    await this.page.goto("/dashboard");
    await expect(this.homeHeading()).toBeVisible({ timeout: 15000 });
    await this.ws.ready();
  }

  homeHeading(): Locator {
    return this.page.getByRole("heading", { name: "What would you like to build today?" });
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
    if (opts.waitForFrame !== false) await this.ws.waitForClientFrame("run_pipeline", 20000);
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
  async openSteps() { await this.thinkingTab().click(); }

  /** A Steps L1 spine row for an agent, by its display name. */
  stepsAgentRow(name: string): Locator {
    return this.page.getByTestId("steps-agent-row").filter({ hasText: name });
  }

  /** The per-agent "Live" badge carried by a RUNNING agent's spine row — one per
   *  running agent (the per-agent running signal that replaced the RUNNING badge). */
  stepsLiveBadge(): Locator {
    return this.page.getByTestId("steps-agent-row").getByText("Live", { exact: true });
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
