/**
 * TS-Z (LIVE) — Workflow Catalog against the REAL Phase-20 backend.
 *
 * ── THIS IS A LIVE SUITE ──────────────────────────────────────────────────────
 * NO mocks. It logs in via the real `POST /api/auth/login` (live.ts harness) and
 * drives the real Catalog view, which fetches the live `GET /api/workflows` list
 * (the Phase-20 payload with the new `user_launchable` / `launch_surface` /
 * `display_name` fields). It is the live analog of the mocked `ts-z.catalog.spec.ts`.
 *
 * It is FAST by design — it asserts the catalog's TWO-GATE filter, the friendly
 * labels, the no-leak invariant, the tier-gating affordance, and that a launch
 * NAVIGATES to the right surface. It NEVER submits a run / waits for Bedrock.
 *
 * ── PREREQUISITES (must hold or login fails) ─────────────────────────────────
 *   1. Backend up on :8000 (Phase-20 code). `GET /api/workflows` returns
 *      user_launchable / launch_surface / display_name.
 *   2. Frontend dev server on :3000 (auto-started/reused by playwright.config.ts).
 *   3. Seeded users (qa-basic / qa-enterprise). Creds resolve from env with the
 *      seed-script defaults (E2E_BASE_PASSWORD / E2E_<TIER>_EMAIL).
 *
 * Run ONLY this suite live:
 *   cd frontend && npm run e2e:live -- e2e/tests/ts-z.catalog.live.spec.ts
 *
 * ── EXPECTED ROW SET (computed from the live backend + the FE two-gate) ───────
 * GATE 1 (`user_launchable`): the backend marks exactly 7 launchable
 *   → user_stories, ppt, prototype, app_builder, mulesoft_to_springboot,
 *     dotnet_to_azure, custom. The catalog renders a row for ALL 7 (any tier).
 * GATE 2 (`canRunPipeline(tier, id)`, entitlements.TIER_PIPELINES): ENABLES rows;
 *   a launchable-but-unentitled row is SHOWN-LOCKED (Lock + "Requires … plan"),
 *   never hidden (mirrors CreationHub).
 *     - enterprise → all 7 enabled (no lock).
 *     - basic      → 2 enabled (user_stories, ppt); the other 5 shown-locked.
 * display_name is null for every workflow → labels come from getWorkflowLabel
 *   (WORKFLOW_LABELS), NOT the title-cased API `name` (UI-SPEC §4).
 *
 * NOT launchable (gate 1) → must NEVER be a catalog row, regardless of tier:
 *   *_revision, od_ppt, od_ppt_revision, chat, reverse_engineer.
 */
import { liveTest as test, expect } from "../fixtures/live";
import type { Page } from "@playwright/test";

// ── Expected catalog contents (GATE 1 — the 7 user_launchable workflows) ──────
// FRIENDLY MUST mirror WORKFLOW_LABELS (frontend/src/hooks/useNotifications.ts).
// It is inlined (not imported) because that module resolves the `@/` path alias,
// which Playwright's TS loader does not honour — inlining keeps the spec robust
// and the labels are explicitly verified against the live render below.
const FRIENDLY = {
  user_stories: "User Stories",
  ppt: "Presentation",
  prototype: "Prototype",
  app_builder: "App Builder",
  mulesoft_to_springboot: "Mulesoft Migration",
  dotnet_to_azure: ".NET Migration",
  custom: "Custom Workflow",
} as const;

const LAUNCHABLE_IDS = Object.keys(FRIENDLY) as (keyof typeof FRIENDLY)[];

// The non-launchable workflows (gate 1) — never a row. Both ids and the raw
// title-cased API `name` are asserted absent.
const NON_LAUNCHABLE_LABELS = [
  // raw API title-case `name` (what would wrongly render if gate 1 leaked / if
  // the FE rendered `name` instead of the friendly label):
  /User Stories Revision/i,
  /Od Ppt/i,
  /Ppt Revision/i,
  /Prototype Revision/i,
  /App Builder Revision/i,
  /Reverse Engineer/i,
  // friendly revision labels (WORKFLOW_LABELS) — also must not appear:
  /\(Revised\)/i,
];

// The catalog row buttons: each row is a <button> wrapping an <h2> (the label).
// Header nav buttons have no h2, so this isolates the catalog list. After the
// home→catalog AnimatePresence (mode="wait") settles, only catalog rows remain.
const catalogRows = (page: Page) =>
  page.getByRole("button").filter({ has: page.getByRole("heading", { level: 2 }) });

/** Navigate to the in-dashboard Catalog view via the AppHeader "Catalog" nav. */
async function openCatalog(page: Page) {
  await page.getByRole("button", { name: /^Catalog$/ }).click();
  // Settle the transition: the catalog mounts EXACTLY the 7 launchable rows
  // (gate 1). Pin the count so subsequent assertions run against the catalog
  // only (not the exiting CreationHub, which carries 6).
  await expect(catalogRows(page)).toHaveCount(LAUNCHABLE_IDS.length);
}

test.describe("TS-Z (LIVE) — workflow catalog (real backend, real /api/workflows)", () => {
  test.describe.configure({ mode: "serial" });

  // ── TS-Z-LIVE-01 — enterprise: rows + friendly labels + no leak ──────────────
  test("TS-Z-LIVE-01 enterprise — launchable rows render with FRIENDLY labels; no revision/od_*/chat/reverse_engineer leak", async ({
    authedPage: page,
  }) => {
    await openCatalog(page);

    // GATE 1 — all 7 launchable workflows render their FRIENDLY label (never the
    // raw API `name`). The mulesoft row is the headline check: friendly
    // "Mulesoft Migration", NOT the title-cased API "Mulesoft To Springboot".
    for (const id of LAUNCHABLE_IDS) {
      await expect(
        page.getByRole("heading", { level: 2, name: FRIENDLY[id] }),
        `launchable "${id}" should render friendly label "${FRIENDLY[id]}"`,
      ).toBeVisible();
    }
    // Explicit headline assertion for the friendly-vs-raw-name contract:
    await expect(page.getByText("Mulesoft Migration")).toBeVisible();
    await expect(page.getByText("Mulesoft To Springboot")).toHaveCount(0);
    await expect(page.getByText(".NET Migration")).toBeVisible();
    await expect(page.getByText("Dotnet To Azure")).toHaveCount(0);
    // (No raw-name check for user_stories: its friendly label "User Stories"
    //  happens to equal its title-cased API name, so they are indistinguishable.
    //  The mulesoft/dotnet rows above are the load-bearing friendly-vs-raw checks
    //  — there the strings genuinely differ.)

    // GATE 1 — non-launchable workflows are NEVER rows (any tier).
    for (const re of NON_LAUNCHABLE_LABELS) {
      await expect(page.getByText(re), `non-launchable label ${re} must not appear`).toHaveCount(0);
    }

    // We are on the Catalog view, NOT the home CreationHub: home-only rows
    // ("Pitch an idea", "Platform workflows") are absent.
    await expect(page.getByText("Pitch an idea")).toHaveCount(0);
    await expect(page.getByText("Platform workflows")).toHaveCount(0);

    // GATE 2 — at enterprise EVERY launchable row is entitled → no lock copy.
    await expect(page.getByText(/Requires .* plan/i)).toHaveCount(0);

    // Capture the enterprise catalog (full page) as the live artifact. Bring the
    // last row into view first so the (vertically-centered) row list is captured,
    // not just the hero header.
    await page
      .getByRole("heading", { level: 2, name: FRIENDLY.custom })
      .scrollIntoViewIfNeeded();
    await page.screenshot({ path: "/tmp/phase20-catalog-live.png", fullPage: true });
  });

  // ── TS-Z-LIVE-02 — basic tier gating: subset entitled, rest shown-locked ─────
  test("TS-Z-LIVE-02 basic — tier-gated subset: user_stories+ppt entitled, the rest shown-locked (Requires … plan)", async ({
    page,
  }) => {
    // Re-login as basic for this test (the serial fixture default is enterprise;
    // we drive the login ourselves to flip the tier without the fixture).
    const { loginLive } = await import("../fixtures/live");
    await loginLive(page, "basic");
    await page.goto("/dashboard");
    await expect(
      page.getByRole("heading", { name: "What would you like to build today?" }),
    ).toBeVisible({ timeout: 20000 });

    await openCatalog(page);

    // GATE 1 is tier-independent: the catalog still renders all 7 launchable
    // rows for basic (openCatalog already pinned the count to 7).

    // GATE 2 — basic entitles ONLY user_stories + ppt (TIER_PIPELINES.basic).
    // Those two rows are enabled (clickable buttons, not disabled).
    for (const id of ["user_stories", "ppt"] as const) {
      const btn = page.getByRole("button").filter({
        has: page.getByRole("heading", { level: 2, name: FRIENDLY[id] }),
      });
      await expect(btn, `${id} row should be entitled (enabled) at basic`).toBeEnabled();
    }

    // The other 5 launchable rows are SHOWN-LOCKED (gate 2): disabled + carry a
    // "Requires … plan" upgrade affordance (matches CreationHub's lock UX).
    for (const id of ["prototype", "app_builder", "mulesoft_to_springboot", "dotnet_to_azure", "custom"] as const) {
      const btn = page.getByRole("button").filter({
        has: page.getByRole("heading", { level: 2, name: FRIENDLY[id] }),
      });
      await expect(btn, `${id} row should be shown-locked (disabled) at basic`).toBeDisabled();
    }

    // The lock copy is present for the 5 gated rows: 2 → "Requires Pro plan"
    // (prototype, app_builder), 3 → "Requires Enterprise plan" (mulesoft, dotnet,
    // custom). Assert by count so the exact split is pinned.
    await expect(page.getByText("Requires Pro plan")).toHaveCount(2);
    await expect(page.getByText("Requires Enterprise plan")).toHaveCount(3);

    // The visible/ENTITLED set at basic (2) is a strict subset of enterprise (7):
    // fewer entitled rows than enterprise. Total rows stay 7 (gate 1).
    const entitled = page.getByRole("button").filter({ has: page.getByRole("heading", { level: 2 }) }).and(
      page.locator("button:not([disabled])"),
    );
    await expect(entitled).toHaveCount(2);

    // Gate 1 still hides the non-launchable rows at basic too.
    for (const re of NON_LAUNCHABLE_LABELS) {
      await expect(page.getByText(re)).toHaveCount(0);
    }
  });

  // ── TS-Z-LIVE-03 — launch routing (navigation only; NO Bedrock run) ──────────
  test("TS-Z-LIVE-03 launch routing — plain-run row → idea-input page; wizard rows → /workflow/{type}/templates", async ({
    authedPage: page,
  }) => {
    // (a) PLAIN-RUN: clicking user_stories lands on the IdeaInputPage (in-app
    // mainView "input"), NOT a hard nav. Its heading is "Provide the brief".
    await openCatalog(page);
    await page
      .getByRole("button", { name: new RegExp(FRIENDLY.user_stories, "i") })
      .first()
      .click();
    await expect(page.getByRole("heading", { name: "Provide the brief" })).toBeVisible();
    // The launch surface (idea textarea) is present — but we DO NOT run it.
    await expect(page.locator("textarea").first()).toBeVisible();

    // (b) WIZARD — prototype: clicking the prototype row hard-navs to the
    // template wizard route. Re-open the catalog (we navigated away in (a)).
    await openCatalog(page);
    await page
      .getByRole("button", { name: new RegExp(FRIENDLY.prototype, "i") })
      .first()
      .click();
    await page.waitForURL(/\/workflow\/prototype\/templates/, { timeout: 20000 });
    expect(page.url()).toContain("/workflow/prototype/templates");

    // (c) WIZARD — ppt: back to the dashboard catalog, click ppt → its wizard.
    await page.goto("/dashboard");
    await expect(
      page.getByRole("heading", { name: "What would you like to build today?" }),
    ).toBeVisible({ timeout: 20000 });
    await openCatalog(page);
    await page
      .getByRole("button", { name: new RegExp(FRIENDLY.ppt, "i") })
      .first()
      .click();
    await page.waitForURL(/\/workflow\/ppt\/templates/, { timeout: 20000 });
    expect(page.url()).toContain("/workflow/ppt/templates");
  });
});
