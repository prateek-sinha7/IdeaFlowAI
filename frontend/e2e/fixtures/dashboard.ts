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

  /** Select a workflow from home, type a brief, click Run, and (default) wait
   *  for the outbound run_pipeline frame. Leaves the app on the execution view. */
  async runWith(opts: { workflow?: string; idea: string; waitForFrame?: boolean }) {
    if (opts.workflow) await this.selectWorkflow(opts.workflow);
    await this.fillIdea(opts.idea);
    await expect(this.runButton()).toBeEnabled();
    await this.runButton().click();
    if (opts.waitForFrame !== false) await this.ws.waitForClientFrame("run_pipeline");
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

  runningBadge(): Locator { return this.page.getByText("RUNNING", { exact: true }); }
  doneBadge(): Locator { return this.page.getByText("DONE", { exact: true }); }
  errorBadge(): Locator { return this.page.getByText("ERROR", { exact: true }); }
  stopButton(): Locator { return this.page.getByRole("button", { name: "Stop" }); }
  newPipelineButton(): Locator { return this.page.getByRole("button", { name: "New Pipeline" }); }

  /** An agent card by its display name. */
  agentCardByName(name: string): Locator { return this.page.getByText(name, { exact: false }); }

  // wave panel
  waveHeading(): Locator { return this.page.getByText("Wave / Subagent Tree"); }
  waveEmpty(): Locator { return this.page.getByText("No waves running."); }
  waveGroup(index: number): Locator { return this.page.getByText(new RegExp(`^Wave ${index}$`)); }

  // preview
  previewEmpty(): Locator { return this.page.getByText("Output will appear here"); }
  degradedHeading(): Locator { return this.page.getByText("This run did not complete successfully"); }
  cancelledHeading(): Locator { return this.page.getByText("This run was cancelled"); }
  failedAgentsLabel(): Locator { return this.page.getByText("Failed agents"); }
  genericIframe(): Locator { return this.page.locator('iframe[title="Deliverable Preview"]'); }
  deckIframe(): Locator { return this.page.locator('iframe[title="Slide Deck Preview"]'); }
  prototypeIframe(): Locator { return this.page.locator('iframe[title="Prototype Preview"]'); }

  // tabs
  previewTab(): Locator { return this.page.getByRole("button", { name: "Preview" }); }
  filesTab(): Locator { return this.page.getByRole("button", { name: "Files" }); }
  thinkingTab(): Locator { return this.page.getByRole("button", { name: "Thinking" }); }

  // questionnaire / gates
  questionnaireTitle(): Locator { return this.page.getByRole("heading", { name: "Quick Setup" }); }
  reviewGateTitle(name: "Specification Review" | "Task Plan Review"): Locator { return this.page.getByText(name); }
  approveButton(): Locator { return this.page.getByRole("button", { name: /Approve.*continue/ }); }
  rejectButton(): Locator { return this.page.getByRole("button", { name: "Reject & cancel pipeline" }); }
}
