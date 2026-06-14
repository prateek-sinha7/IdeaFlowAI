/**
 * TS-Z2 (LIVE) — Saved Workflows against the REAL Phase-21 backend.
 *
 * ── THIS IS A LIVE SUITE ──────────────────────────────────────────────────────
 * NO mocks (no mock-API / mock-WS). It logs in via the real `POST /api/auth/login`
 * (live.ts harness) and drives the REAL `/api/user-workflows` CRUD router. It is
 * the live analog of the mocked `ts-z2.saved-workflows.spec.ts` — same selectors /
 * flow structure, but every byte hits the running backend.
 *
 * It proves the Phase-21 journey for an ENTERPRISE user (custom/saved workflows are
 * enterprise-gated):
 *
 *   1. Save persists (UI): compose a custom workflow → add an agent via the
 *      AgentsPopup → "Save workflow" → NameWorkflowModal → confirm. A real
 *      `POST /api/user-workflows` fires (asserted via the network response).
 *   2. Appears in catalog: the saved row shows under "Your workflows" with its
 *      name + a kebab; built-in rows carry NO kebab.
 *   3. Rename (UI → real PATCH): kebab → Rename → new name → confirm → the row
 *      label updates (a real `PATCH /api/user-workflows/{id}` fires).
 *   4. Launch pre-loads (the load-bearing 21-03 change): clicking the saved row
 *      lands on the IdeaInputPage PRE-LOADED with the saved agents (NOT an empty
 *      `custom` composer). We prove the pre-load only — NO run is submitted
 *      (no Bedrock).
 *   5. Cleanup: the test row is deleted (UI kebab → Delete) AND a belt-and-braces
 *      API sweep in afterAll removes anything left, so the run is repeatable.
 *
 * It NEVER submits a run / waits for Bedrock — it is fast by design.
 *
 * ── PREREQUISITES (must hold or login fails) ─────────────────────────────────
 *   1. Backend up on :8000 (Phase-21 code, alembic 0021). `/api/user-workflows`
 *      CRUD is live; `market-research-agent` / `swot-analyst` exist in the custom
 *      agent pool.
 *   2. Frontend dev server on :3000 (auto-started/reused by playwright.config.ts).
 *   3. Seeded ENTERPRISE user (qa-enterprise). Creds resolve from env with the
 *      seed-script defaults (E2E_BASE_PASSWORD / E2E_ENTERPRISE_EMAIL).
 *
 * Run ONLY this suite live:
 *   cd frontend && npm run e2e:live -- e2e/tests/ts-z2.saved-workflows.live.spec.ts
 */
import { liveTest as test, expect, loginLive } from "../fixtures/live";
import type { Page } from "@playwright/test";

const API = process.env.E2E_API_URL || "http://localhost:8000";

// Unique, identifiable names per run so reruns never collide and so the afterAll
// API sweep can recognise this spec's rows. The `__e2e-z2-live__` prefix is the
// sweep key; the timestamp makes the saved name unique within a run.
const PREFIX = "__e2e-z2-live__";
const STAMP = Date.now();
const SAVED_NAME = `${PREFIX} saved ${STAMP}`;
const RENAMED_NAME = `${PREFIX} renamed ${STAMP}`;

// The two REAL custom-pool agents we assemble/seed. They render their `name` in
// the AgentsPopup grid and (post-launch) on the pre-loaded composer.
const AGENT_A = { id: "market-research-agent", name: "Market Research Agent" };
const AGENT_B = { id: "swot-analyst", name: "Strategy Analysis Agent" };

// ── REST helpers (owner-scoped; the harness adds the JWT) ─────────────────────
async function listSaved(page: Page, token: string) {
  const res = await page.request.get(`${API}/api/user-workflows`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok()) throw new Error(`GET /api/user-workflows failed (${res.status()})`);
  return (await res.json()) as Array<{ id: string; name: string }>;
}

async function deleteSaved(page: Page, token: string, id: string) {
  await page.request.delete(`${API}/api/user-workflows/${id}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
}

/** Remove every row this spec authored (by the PREFIX), so the run is repeatable. */
async function sweepSpecRows(page: Page, token: string) {
  const rows = await listSaved(page, token);
  for (const r of rows) {
    if (r.name.startsWith(PREFIX)) await deleteSaved(page, token, r.id);
  }
}

/** Seed one saved workflow directly via the API (the sanctioned fallback for
 *  steps 2-4 if the live AgentsPopup assembly proves brittle — see step 1). */
async function seedSaved(page: Page, token: string, name: string) {
  const res = await page.request.post(`${API}/api/user-workflows`, {
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    data: { name, description: "e2e live seed", base_pipeline_type: "custom", agent_ids: [AGENT_A.id, AGENT_B.id] },
  });
  if (!res.ok()) throw new Error(`seed POST /api/user-workflows failed (${res.status()})`);
}

/** Navigate to the in-dashboard Catalog view via the AppHeader "Catalog" nav. It
 *  re-mounts WorkflowCatalog → triggers a fresh `getUserWorkflows` GET. */
async function openCatalog(page: Page) {
  await page.getByRole("button", { name: /^Catalog$/ }).click();
  // The "What would you like to build today?" hero is the catalog's own header;
  // wait for it so subsequent assertions run against the settled catalog.
  await expect(page.getByRole("heading", { name: "What would you like to build today?" })).toBeVisible();
}

/** The saved-row container under "Your workflows" matching a given name (the
 *  `.group` row wrapping the name <h2>). Mirrors the mocked spec's locator. */
const savedRow = (page: Page, name: string) =>
  page.locator(".group", { has: page.getByRole("heading", { name }) });

test.describe("TS-Z2 (LIVE) — saved workflows (real backend, enterprise: Save → appears → rename → launch)", () => {
  test.describe.configure({ mode: "serial" });

  // A fresh login (token) the REST helpers reuse for seeding/cleanup. Captured in
  // beforeAll so the afterAll sweep has it even if a test step throws mid-way.
  let token = "";

  test.beforeAll(async ({ browser }) => {
    const page = await browser.newPage();
    token = await loginLive(page, "enterprise");
    await sweepSpecRows(page, token); // clean any leftovers from a prior aborted run
    await page.close();
  });

  test.afterAll(async ({ browser }) => {
    // Belt-and-braces: remove anything this spec authored, even if a UI delete was
    // skipped because an earlier step failed. Keeps the run idempotent.
    const page = await browser.newPage();
    try {
      const t = token || (await loginLive(page, "enterprise"));
      await sweepSpecRows(page, t);
    } finally {
      await page.close();
    }
  });

  test("TS-Z2-LIVE journey — Save persists → appears in catalog → rename → launch pre-loads agents", async ({
    authedPage: page,
  }) => {
    // Tracks whether the UI Save path produced the saved row. If the live
    // AgentsPopup assembly proves brittle (it should not), we fall back to an API
    // seed for steps 2-4 — but the modal→POST wiring is still asserted in step 1.
    let savedViaUi = false;

    // ───────────────────────────────────────────────────────────────────────────
    // STEP 1 — Save persists (UI → real POST /api/user-workflows)
    // ───────────────────────────────────────────────────────────────────────────
    await test.step("save-persists: compose custom → add agent → Save workflow → real POST", async () => {
      await openCatalog(page);

      // "+ Create workflow" → onSelectFeature("custom") → the custom composer
      // (IdeaInputPage). `custom` seeds ZERO agents → "Add agents first" until one
      // is added (the same gate as Save).
      await page.getByRole("button", { name: /Create workflow/i }).click();
      await expect(page.getByRole("heading", { name: "Describe the task" })).toBeVisible();
      // Save is disabled with zero agents.
      await expect(page.getByRole("button", { name: /Save workflow/i })).toBeDisabled();

      // Open Advanced (AgentsPopup) → "Workflow configuration".
      await page.getByRole("button", { name: /^Advanced/ }).click();
      await expect(page.getByRole("heading", { name: "Workflow configuration" })).toBeVisible();

      // Add a custom agent via the AgentLibrary ("+ Add agent" → its card's "+ Add").
      // Clicking "+ Add" closes the library (AgentLibrary.handleAdd → onClose) and
      // returns to the popup, so we reopen it for each agent. We add TWO so the
      // saved row carries a real 2-agent composition (the launch-preload proof).
      const addCustomAgent = async (agentName: string) => {
        // "+ Add agent (N left)" in the popup grid opens the AgentLibrary. The
        // library defaults its category to the current pipeline ("custom"), so the
        // custom agents show without changing the filter.
        await page.getByRole("button", { name: /\+ Add agent/i }).first().click();
        await expect(page.getByRole("heading", { name: "Add agent" })).toBeVisible();
        // The agent's library card: the container that holds BOTH its name and a
        // "+ Add" button (disambiguates from sibling cards).
        const card = page.locator("div").filter({ has: page.getByText(agentName, { exact: true }) }).filter({
          has: page.getByRole("button", { name: /^\+ Add$/ }),
        }).last();
        await card.getByRole("button", { name: /^\+ Add$/ }).click();
        // Back in the popup; the agent now appears in the flow grid.
        await expect(page.getByRole("heading", { name: "Workflow configuration" })).toBeVisible();
      };
      await addCustomAgent(AGENT_A.name);
      await addCustomAgent(AGENT_B.name);

      // Close the popup ("Save changes") back to the composer.
      await page.getByRole("button", { name: /Save changes/i }).click();

      // "Save workflow" is now enabled → NameWorkflowModal → unique name → Save.
      const saveWorkflowBtn = page.getByRole("button", { name: /Save workflow/i });
      await expect(saveWorkflowBtn).toBeEnabled();
      await saveWorkflowBtn.click();
      await expect(page.getByRole("heading", { name: "Save workflow" })).toBeVisible();
      await page.getByPlaceholder(/Competitive research/i).fill(SAVED_NAME);

      // Assert the REAL POST fires (201) when we confirm. The dialog "Save" button
      // is the modal's gray-900 pill (exact "Save").
      const [postResp] = await Promise.all([
        page.waitForResponse(
          (r) => r.url().includes("/api/user-workflows") && r.request().method() === "POST",
          { timeout: 20000 },
        ),
        page.getByRole("button", { name: /^Save$/ }).click(),
      ]);
      expect(postResp.status(), "POST /api/user-workflows should return 201").toBe(201);
      const created = await postResp.json();
      expect(created.name).toBe(SAVED_NAME);
      expect(created.base_pipeline_type).toBe("custom");
      // The composer assembled BOTH custom agents → the persisted triple carries
      // both ids (the 2-agent composition the launch-preload step then proves).
      expect(created.agent_ids).toEqual(expect.arrayContaining([AGENT_A.id, AGENT_B.id]));

      // The composer shows the "Saved" confirmation pill.
      await expect(page.getByText("Saved", { exact: true })).toBeVisible();
      savedViaUi = true;
    });

    // Safety net: if (and only if) the UI Save did not persist a row, seed one via
    // the API so steps 2-4 are deterministic. The step-1 modal→POST assertions
    // above already ran regardless, so we never silently skip the Save wiring.
    if (!savedViaUi || !(await listSaved(page, token)).some((r) => r.name === SAVED_NAME)) {
      await seedSaved(page, token, SAVED_NAME);
    }

    // ───────────────────────────────────────────────────────────────────────────
    // STEP 2 — Appears in catalog under "Your workflows" (built-ins have no kebab)
    // ───────────────────────────────────────────────────────────────────────────
    await test.step("appears: saved row renders under 'Your workflows' with a kebab; built-ins have none", async () => {
      await openCatalog(page);
      await expect(page.getByText("Your workflows")).toBeVisible();
      await expect(page.getByRole("heading", { name: SAVED_NAME })).toBeVisible();

      // The saved row exposes a per-row kebab (MoreHorizontal). Hover to reveal it
      // (it is opacity-0 until group-hover), then assert it is present/actionable.
      const row = savedRow(page, SAVED_NAME);
      await row.hover();
      const kebab = row.getByRole("button").last();
      await expect(kebab).toBeVisible();

      // Built-in rows (e.g. the friendly "Prototype" catalog row) carry NO kebab —
      // their right slot is the ArrowRight / Lock, never a Rename/Duplicate/Delete
      // menu. Opening the saved row's kebab surfaces "Rename"; a built-in row never
      // can. Assert the built-in "Prototype" row has no menu-trigger that yields it.
      const builtinRow = page.locator(".group", { has: page.getByRole("heading", { level: 2, name: "Prototype" }) });
      // The built-in catalog row IS the <button> (no inner kebab button); the saved
      // row is a <div.group> with an inner launch <button> + a kebab <button>.
      await expect(builtinRow.getByRole("button", { name: /Rename|Duplicate|Delete/i })).toHaveCount(0);
    });

    // ───────────────────────────────────────────────────────────────────────────
    // STEP 3 — Rename (UI → real PATCH /api/user-workflows/{id})
    // ───────────────────────────────────────────────────────────────────────────
    await test.step("rename: kebab → Rename → new name → real PATCH → label updates", async () => {
      const row = savedRow(page, SAVED_NAME);
      await row.hover();
      await row.getByRole("button").last().click(); // open the kebab
      await page.getByRole("button", { name: /^Rename$/ }).click();

      await expect(page.getByRole("heading", { name: "Rename workflow" })).toBeVisible();
      const nameInput = page.getByPlaceholder(/Competitive research/i);
      await expect(nameInput).toHaveValue(SAVED_NAME); // prefilled with the current name
      await nameInput.fill(RENAMED_NAME);

      // Assert the REAL PATCH fires (200) on confirm.
      const [patchResp] = await Promise.all([
        page.waitForResponse(
          (r) => /\/api\/user-workflows\/[^/?]+/.test(r.url()) && r.request().method() === "PATCH",
          { timeout: 20000 },
        ),
        page.getByRole("button", { name: /^Save$/ }).click(),
      ]);
      expect(patchResp.status(), "PATCH /api/user-workflows/{id} should return 200").toBe(200);
      expect((await patchResp.json()).name).toBe(RENAMED_NAME);

      // The row label updates (optimistic state ← the PATCH response).
      await expect(page.getByRole("heading", { name: RENAMED_NAME })).toBeVisible();
      await expect(page.getByRole("heading", { name: SAVED_NAME })).toHaveCount(0);
    });

    // ───────────────────────────────────────────────────────────────────────────
    // STEP 4 — Launch pre-loads the saved agents (the load-bearing 21-03 change)
    // ───────────────────────────────────────────────────────────────────────────
    await test.step("launch-preloads: click saved row → IdeaInputPage pre-loaded with the saved agents (NOT empty)", async () => {
      // Click the saved row's launch area → onLaunchSaved → DashboardLayout seeds
      // savedComposition → IdeaInputPage mounts PRE-LOADED.
      await page.getByRole("heading", { name: RENAMED_NAME }).click();

      // We land on the custom composer (IdeaInputPage, custom copy).
      await expect(page.getByRole("heading", { name: "Describe the task" })).toBeVisible();

      // PRE-LOAD PROOF (21-03): a freshly-launched `custom` workflow would seed ZERO
      // agents (Run = "Add agents first", disabled). Here the seed loaded TWO agents:
      //   (a) the "Advanced … 2 agents" affordance is non-zero, and
      //   (b) the seeded agents resolve by NAME in the Advanced popup grid, and
      //   (c) Run reads "Run workflow" (NOT "Add agents first") once a brief is typed.
      await expect(page.getByRole("button", { name: /Advanced/ })).toBeVisible();
      await expect(page.getByText(/2 agents/)).toBeVisible();

      // The Run button must NOT say "Add agents first" — i.e. the pipeline is
      // non-empty purely from the saved-workflow seed.
      await expect(page.getByRole("button", { name: /Add agents first/ })).toHaveCount(0);

      // Open Advanced and confirm BOTH seeded agents are present by name.
      await page.getByRole("button", { name: /^Advanced/ }).click();
      await expect(page.getByRole("heading", { name: "Workflow configuration" })).toBeVisible();
      await expect(page.getByText(AGENT_A.name, { exact: true }).first()).toBeVisible();
      await expect(page.getByText(AGENT_B.name, { exact: true }).first()).toBeVisible();
      await page.getByRole("button", { name: /Cancel/ }).first().click();

      // Type a brief → Run becomes "Run workflow" and is ENABLED (we do NOT click it).
      await page.locator("textarea").first().fill("Research the AI coding-assistant market and produce a SWOT.");
      const runBtn = page.getByRole("button", { name: /Run workflow/ });
      await expect(runBtn).toBeVisible();
      await expect(runBtn).toBeEnabled();
    });

    // ───────────────────────────────────────────────────────────────────────────
    // CATALOG SCREENSHOT — "Your workflows" section (the live artifact)
    // ───────────────────────────────────────────────────────────────────────────
    await test.step("screenshot: capture the catalog 'Your workflows' section", async () => {
      await openCatalog(page);
      await expect(page.getByText("Your workflows")).toBeVisible();
      // Wait for the saved row itself (the getUserWorkflows GET + its motion
      // fade-in) so the artifact shows the populated section, not a mid-transition
      // frame. Pin to the renamed row + let the AnimatePresence settle.
      const shotRow = page.getByRole("heading", { name: RENAMED_NAME });
      await expect(shotRow).toBeVisible();
      // The catalog scrolls inside an inner `overflow-y-auto` container (not the
      // document body), so a `fullPage` page shot frames only the hero (the document
      // body is viewport-height; fullPage resets the inner scroll). Scroll the saved
      // row into view inside that inner scroller and capture the "Your workflows"
      // <section> element directly — the faithful artifact of the required section.
      await shotRow.scrollIntoViewIfNeeded();
      await page.waitForTimeout(500); // settle the inner scroll + row fade-in
      const section = page.locator("section", { has: page.getByText("Your workflows") });
      await expect(section).toBeVisible();
      await section.screenshot({ path: "/tmp/phase21-saved-workflows-live.png" });
    });

    // ───────────────────────────────────────────────────────────────────────────
    // STEP 5 — Cleanup via the UI kebab → Delete (the afterAll sweep is the net)
    // ───────────────────────────────────────────────────────────────────────────
    await test.step("cleanup: kebab → Delete removes the saved row (real DELETE)", async () => {
      const row = savedRow(page, RENAMED_NAME);
      await row.hover();
      await row.getByRole("button").last().click(); // open the kebab
      // The kebab menu's "Delete" item (inside the saved-rows <section>) opens the
      // DeleteModal. Scope to the section so it never collides with the modal pill.
      await page.locator("section").getByRole("button", { name: /^Delete$/ }).click();

      // The DeleteModal confirm. Scope the confirm to the modal dialog (the card
      // holding the "Delete workflow" heading) so it doesn't strict-mode-collide
      // with the still-mounted kebab "Delete" item. Assert the REAL DELETE (204).
      await expect(page.getByRole("heading", { name: "Delete workflow" })).toBeVisible();
      const deleteModal = page
        .locator("div.fixed.inset-0")
        .filter({ has: page.getByRole("heading", { name: "Delete workflow" }) });
      const [delResp] = await Promise.all([
        page.waitForResponse(
          (r) => /\/api\/user-workflows\/[^/?]+/.test(r.url()) && r.request().method() === "DELETE",
          { timeout: 20000 },
        ),
        // The modal's gray-900 confirm pill (exact "Delete", scoped to the modal).
        deleteModal.getByRole("button", { name: /^Delete$/ }).click(),
      ]);
      expect(delResp.status(), "DELETE /api/user-workflows/{id} should return 204").toBe(204);

      // The row is gone (server delete resolved → row removed from the list).
      await expect(page.getByRole("heading", { name: RENAMED_NAME })).toHaveCount(0);
    });
  });
});
