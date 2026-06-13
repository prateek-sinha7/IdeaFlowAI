/**
 * TS-V — Full per-workflow end-to-end, LIVE (real backend + real Bedrock).
 * TEST-REGISTER §3 (TS-V) + §4 per-workflow matrix.
 *
 * ── THIS IS A LIVE SUITE ──────────────────────────────────────────────────────
 * It runs against a REAL backend on real Bedrock — NO mocks. It drives the
 * real UI (CreationHub → IdeaInputPage → execution view) and waits for the real
 * deliverable to render. Real LLM runs take MINUTES, so every timeout here is
 * deliberately generous (per-test 10 min, deliverable waits up to 8 min).
 *
 * ── PREREQUISITES (all must hold or these will fail at login/run) ─────────────
 *   1. Backend up on :8000 with Bedrock reachable:
 *        cd backend
 *        RUNS_ROOT=/tmp/flowin-runs AWS_PROFILE=default AWS_REGION=eu-central-1 \
 *          python3.11 -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
 *      (profile `default` = acct 473293451041, eu-central-1, Haiku 4.5 — working).
 *   2. Frontend dev server on :3000 (auto-started/reused by playwright.config.ts).
 *   3. Seeded users (qa-basic / qa-pro / qa-enterprise + admin):
 *        python3.11 backend/scripts/seed_test_users.py
 *      Creds resolve from env with seed-script defaults:
 *        E2E_BASE_PASSWORD (default "flowin-e2e-pass")
 *        E2E_ENTERPRISE_EMAIL (default "qa-enterprise@flowin.test")
 *      The `authedPage` fixture logs in as `enterprise` (unlocks custom + app_builder).
 *
 * Run ONLY this suite live:
 *   cd frontend && npx playwright test --project=live e2e/tests/ts-v.per-workflow.live.spec.ts
 *
 * ── Selectors ─────────────────────────────────────────────────────────────────
 * live.ts provides only the `authedPage` fixture (raw Page) — NOT the
 * DashboardPage page object. So we use raw role/text/placeholder/iframe-title
 * locators, MIRRORING the mocked specs (ts-c/ts-e/ts-o) and the canonical
 * handles in fixtures/dashboard.ts. Almost no data-testid ships (TEST-REGISTER
 * §1.5), so anchors are exact visible text / role / iframe[title].
 */
import { liveTest as test, expect } from "../fixtures/live";
import type { Page } from "@playwright/test";

// Real runs are minutes long — give every test a 10-minute ceiling.
const RUN_TIMEOUT = 600_000;
// The deliverable can take most of that budget to render on real Bedrock.
const DELIVERABLE_TIMEOUT = 480_000;

// ── shared helpers (raw-page, mirrors fixtures/dashboard.ts handles) ──────────

/** Click a CreationHub workflow row by its exact H2 label (CreationHub renders
 *  each row as a <button> whose accessible name contains the label text). */
async function selectWorkflow(page: Page, label: string) {
  await page.getByRole("button", { name: new RegExp(label, "i") }).first().click();
}

const ideaTextarea = (page: Page) => page.locator("textarea").first();

/** The Run button cycles label/disabled state — match any of its labels. */
const runButton = (page: Page) =>
  page.getByRole("button", { name: /Run workflow|Add agents first|Pick a migration path/ });

/** Type a brief into the IdeaInputPage textarea. */
async function fillIdea(page: Page, idea: string) {
  await ideaTextarea(page).fill(idea);
}

/**
 * Some workflows pop a clarify questionnaire ("Quick Setup") AFTER Run, before
 * agents stream. It may or may not appear (planner decides PROCEED vs
 * CLARIFY_REQUIRED at runtime). If it shows up within `graceMs`, dismiss it by
 * running with defaults; otherwise no-op. Never fails when it's absent.
 *
 * Submit labels (QuestionnairePanel): all answered → "Run {label} Pipeline";
 * some → "Continue with {a}/{n} answered"; none answered → "Run with defaults";
 * secondary → "Skip all & run directly". We click the secondary skip first
 * (most robust — always present, always proceeds), falling back to the
 * defaults/run-pipeline primary.
 */
async function dismissClarifyIfPresent(page: Page, graceMs = 90_000) {
  const quickSetup = page.getByRole("heading", { name: "Quick Setup" });
  try {
    await quickSetup.waitFor({ state: "visible", timeout: graceMs });
  } catch {
    return; // planner went straight to PROCEED — no questionnaire, fine.
  }
  // Prefer the always-present secondary skip; fall back to the primary submit.
  const skip = page.getByRole("button", { name: "Skip all & run directly" });
  const runDefaults = page.getByRole("button", { name: /Run with defaults|Run .* Pipeline|Continue with/ });
  if (await skip.count()) {
    await skip.first().click();
  } else if (await runDefaults.count()) {
    await runDefaults.first().click();
  }
  // The panel clears on submit (questionnaire_complete).
  await expect(quickSetup).toBeHidden({ timeout: 30_000 }).catch(() => {});
}

/** Open the AgentsPopup composer ("Advanced" → "Workflow configuration"). */
async function openComposer(page: Page) {
  await page.getByRole("button", { name: /^Advanced/ }).click();
  await expect(page.getByText("Workflow configuration")).toBeVisible();
}

/**
 * Assert NO fabricated tool-call XML leaked into the rendered run (F4 / TS-V-01).
 * The agents must never surface raw `<function_calls>` markup in chunks/output.
 */
async function expectNoToolXml(page: Page) {
  await expect(page.locator("body")).not.toContainText("<function_calls>");
}

test.describe("TS-V — per-workflow end-to-end (LIVE, real Bedrock)", () => {
  test.describe.configure({ mode: "serial" });

  // ── TS-V-01 user_stories ────────────────────────────────────────────────────
  test("TS-V-01 user_stories → Product Backlog (clarify-tolerant, 0 tool-XML)", async ({ authedPage: page }) => {
    test.setTimeout(RUN_TIMEOUT);

    // Home → "Generate product requirements" (user_stories seeds 6 agents).
    await selectWorkflow(page, "Generate product requirements");
    await expect(page.getByRole("heading", { name: "Provide the brief" })).toBeVisible();

    await fillIdea(
      page,
      "Generate epics and user stories for a refunds workflow with multi-currency support and partial refunds.",
    );
    await expect(runButton(page)).toBeEnabled();
    await runButton(page).click();

    // user_stories typically asks clarify questions first — dismiss if shown.
    await dismissClarifyIfPresent(page);

    // The real deliverable: the UserStoryPreview "Product Backlog" header.
    // (.first() — the sample epic title can also read "Product Backlog" as an h2).
    await expect(
      page.getByRole("heading", { name: "Product Backlog" }).first(),
    ).toBeVisible({ timeout: DELIVERABLE_TIMEOUT });

    // F4: no fabricated tool-call XML leaked anywhere on screen.
    await expectNoToolXml(page);
  });

  // ── TS-V-04 app_builder ───────────────────────────────────────────────────────
  test("TS-V-04 app_builder → file-tree IDE (Download ZIP / {n} files)", async ({ authedPage: page }) => {
    test.setTimeout(RUN_TIMEOUT);

    // app_builder is gated to pro+; the enterprise fixture user unlocks it.
    await selectWorkflow(page, "Build an end-to-end application");
    await expect(page.getByRole("heading", { name: "Describe the application" })).toBeVisible();

    await fillIdea(
      page,
      "A SaaS platform for managing freelance invoices with Stripe integration, auth, and a dashboard.",
    );
    await expect(runButton(page)).toBeEnabled();
    await runButton(page).click();

    // app_builder may also clarify — tolerate it.
    await dismissClarifyIfPresent(page);

    // The AppBuilder IDE chrome appears once ≥1 file parses: a "{n} files" badge,
    // the file search box, and the Download ZIP button. app_builder is the
    // longest run (15 agents → minutes) — lean on the full deliverable budget.
    await expect(
      page.getByRole("button", { name: "Download ZIP" }),
    ).toBeVisible({ timeout: DELIVERABLE_TIMEOUT });
    await expect(page.getByText(/^\d+ files$/)).toBeVisible();

    await expectNoToolXml(page);
  });

  // ── TS-V-05 custom — THE SC-001 HEADLINE ──────────────────────────────────────
  // SC-001: "A brand-new custom workflow can replicate prototype by manifest +
  // AGENT.md only — with zero engine edits." This drives the composer to assemble
  // a custom workflow and waits for the generic, mimetype-dispatched deliverable.
  test("TS-V-05 [SC-001] custom workflow → generic deliverable (zero engine edits)", async ({ authedPage: page }) => {
    test.setTimeout(RUN_TIMEOUT);
    test.info().annotations.push({
      type: "SC-001",
      description:
        "Core value: a brand-new custom workflow runs from registered capabilities only — the kernel knows no workflow by name. Deliverable dispatches on mimetype (generic 'Deliverable Preview' iframe / markdown), never a workflow name.",
    });

    // Home → "Compose a custom workflow" (enterprise-gated; custom seeds NO agents).
    await selectWorkflow(page, "Compose a custom workflow");
    await expect(page.getByRole("heading", { name: "Describe the task" })).toBeVisible();

    // custom seeds zero agents → Run reads "Add agents first" until we add one.
    await expect(runButton(page)).toHaveText(/Add agents first/);

    // Open the composer and add ≥1 agent from the library so the run is valid.
    await openComposer(page);
    // "Browse agent library →" opens the AgentLibrary modal ("Add agent").
    await page.getByRole("button", { name: "Browse agent library →" }).click();
    await expect(page.getByRole("heading", { name: "Add agent" })).toBeVisible();
    // Add the first available agent — its "+ Add" button (title="Add agent")
    // adds it to the flow AND closes the library. (Library defaults to the
    // `custom` category for a custom pipeline; any agent is fine for this proof.)
    await page.getByRole("button", { name: "+ Add", exact: true }).first().click();
    await expect(page.getByRole("heading", { name: "Add agent" })).toBeHidden();
    // Close the composer (Save changes ≡ Cancel — state is already live).
    await page.getByRole("button", { name: "Save changes" }).click();
    await expect(page.getByText("Workflow configuration")).toBeHidden();

    // Brief + Run (now enabled with ≥1 agent).
    await fillIdea(
      page,
      "Research the competitive landscape for AI coding assistants and produce a concise SWOT analysis.",
    );
    await expect(runButton(page)).toBeEnabled();
    await runButton(page).click();

    await dismissClarifyIfPresent(page);

    // custom is deliberately NOT a known render type → the deliverable comes
    // through the generic, MIMETYPE-dispatched channel (SC-001). Depending on the
    // agents' output mimetype it is EITHER:
    //   • text/html      → iframe[title="Deliverable Preview"] (sandbox allow-scripts), OR
    //   • text/markdown  → a MarkdownPreview (no iframe), OR
    //   • other          → a "Deliverable ready" download card.
    // We accept ANY of these as proof the run produced a deliverable. A robust
    // cross-cut: the PreviewPanel header flips "Generating..." → "Results" when
    // content is present, so we wait on that too.
    const genericIframe = page.locator('iframe[title="Deliverable Preview"]');
    const deliverableReady = page.getByText("Deliverable ready");
    const resultsHeader = page.getByText("Results", { exact: true });

    await expect
      .poll(
        async () =>
          (await genericIframe.count()) > 0 ||
          (await deliverableReady.count()) > 0 ||
          (await resultsHeader.count()) > 0,
        { timeout: DELIVERABLE_TIMEOUT, message: "custom deliverable never rendered (generic channel)" },
      )
      .toBe(true);

    // SECURITY (TS-P-01): if the deliverable IS an HTML iframe, it must be
    // sandboxed allow-scripts ONLY — never allow-same-origin.
    if ((await genericIframe.count()) > 0) {
      const sandbox = await genericIframe.first().getAttribute("sandbox");
      expect(sandbox).toBe("allow-scripts");
    }

    await expectNoToolXml(page);
  });

  // ── TS-V-02 od_prototype — WIZARD PATH (fixme: live template/DS selection) ────
  test.fixme(
    "TS-V-02 od_prototype → Prototype Preview iframe (wizard-path live driver)",
    async () => {
      // ── WHY FIXME ──────────────────────────────────────────────────────────
      // CreationHub routes "Build an interactive prototype" to a hard nav
      // (/workflow/prototype/templates), NOT IdeaInputPage. That wizard requires
      // selecting BOTH a template (from a gallery loaded live via
      // listPrototypeTemplates) AND a design system (listDesignSystems) before
      // "Continue" enables — and the gallery cards are keyed on live template
      // names/ids that aren't knowable offline. Driving it reliably needs the
      // live template set in hand. Documented exact steps for a manual/maintained
      // driver:
      //
      //   1. await selectWorkflow(page, "Build an interactive prototype");
      //      → page.waitForURL(/\/workflow\/prototype\/templates/);
      //   2. await expect(page.getByRole("heading",
      //        { name: "Configure your prototype" })).toBeVisible();
      //   3. Fill the brief textarea (Section 1):
      //      await page.locator("textarea").first().fill(
      //        "A kanban board for a 5-person growth squad — backlog, doing, review, done.");
      //   4. Pick a template card in <TemplateGallery> (Section 2). Cards render
      //      from has_preview templates; click the first selectable card (it gets
      //      a Check overlay). Card has no stable testid — target the first
      //      gallery tile button/image under the "Choose a template" section.
      //   5. Pick a design system in <DesignSystemPicker> (Section 3) — click the
      //      first system card.
      //   6. (Optional) leave Review gates at defaults — prototype-specify +
      //      prototype-plan are pre-checked (gate === "Human_Gate").
      //   7. await page.getByRole("button", { name: "Continue" }).click();
      //      → wizard sets sessionStorage od_prototype.pending=true +
      //      prototype.draft and router.push("/dashboard"); on WS connect the FE
      //      fires run_pipeline { pipeline_type: "od_prototype", template_id,
      //      design_system_id }.
      //   8. TWO human review gates appear mid-run (F1, before approval):
      //        await page.getByText("Specification Review");   // approve
      //        await page.getByRole("button", { name: /Approve.*continue/ }).click();
      //        await page.getByText("Task Plan Review");        // approve
      //        await page.getByRole("button", { name: /Approve.*continue/ }).click();
      //   9. Spec-Kit live view ("Spec Kit Pipeline") then the deliverable:
      //        await expect(page.locator('iframe[title="Prototype Preview"]'))
      //          .toBeVisible({ timeout: 480_000 });
      //
      // Implement when the live template/design-system catalog is pinned for E2E.
    },
  );

  // ── TS-V-03 od_ppt — WIZARD PATH (fixme: live template selection) ────────────
  test.fixme(
    "TS-V-03 od_ppt → Slide Deck Preview iframe (wizard-path live driver)",
    async () => {
      // ── WHY FIXME ──────────────────────────────────────────────────────────
      // CreationHub routes "Pitch an idea" to /workflow/ppt/templates (hard nav,
      // not IdeaInputPage). The PPT wizard requires picking a deck template from
      // <PPTTemplateGallery> (loaded live via listPPTTemplates); a design system
      // is required ONLY when the chosen template declares design_system.requires.
      // Gallery cards key on live template names not knowable offline. Documented
      // exact steps for a manual/maintained driver:
      //
      //   1. await selectWorkflow(page, "Pitch an idea");
      //      → page.waitForURL(/\/workflow\/ppt\/templates/);
      //   2. await expect(page.getByRole("heading",
      //        { name: "Configure your presentation" })).toBeVisible();
      //   3. Fill the brief (Section 1):
      //      await page.locator("textarea").first().fill(
      //        "Blockchain technology — enterprise adoption trends and ROI analysis for 2025.");
      //   4. Pick a deck template in <PPTTemplateGallery> (Section 2): click the
      //      first selectable card (gets a Check). If that template's
      //      design_system.requires === true, also pick a design system (Section 3).
      //   5. await page.getByRole("button", { name: "Continue" }).click();
      //      → sets sessionStorage od_ppt.pending=true + ppt.draft and
      //      router.push("/dashboard"); on WS connect FE fires run_pipeline
      //      { pipeline_type: "od_ppt", template_id, design_system_id? }.
      //   6. od_ppt has NO default human gates → no review modal.
      //   7. Deliverable: the deck renders in the slide iframe (NOT QA narration):
      //        await expect(page.locator('iframe[title="Slide Deck Preview"]'))
      //          .toBeVisible({ timeout: 480_000 });
      //
      // Implement when the live PPT template catalog is pinned for E2E.
    },
  );
});
