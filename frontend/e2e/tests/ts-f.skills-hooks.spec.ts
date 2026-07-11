/**
 * TS-F — Skills & Hooks tab (AgentsPopup → SkillsHooksTab). Proves the
 * skills/hooks attach UX (empty states, picker, search, category/event
 * filters, count pills), payload threading into `run_pipeline`
 * (attached_skills / attached_hooks), and persistence across popup reopen via
 * the global SkillsHooksContext.
 *
 * Flow: from home → select `user_stories` ("Generate product requirements") +
 * type a brief → click `Advanced` (opens AgentsPopup) → `Skills & Hooks` tab.
 * We do NOT run first (the Advanced button only lives on IdeaInputPage); for
 * TS-F-05 we Save the popup, then Run from the same idea page.
 *
 * Names are read from the data files (not guessed):
 *   - FIRST skill in src/data/skills.ts → "Brainstorming Ideas Into Designs"
 *     (id superpowers-brainstorming, category `planning`).
 *   - FIRST testing-category skill → "Dispatching Parallel Agents".
 *   - FIRST hook in src/data/hooks.ts → "Quality Gate"
 *     (id ecc-post-quality-gate, event PostToolUse).
 */
import { test, expect } from "../fixtures/test";

const WORKFLOW = "Generate product requirements"; // TYPE_CONFIG.user_stories.tag
const IDEA = "Generate epics for a refunds workflow";

// First entry in src/data/skills.ts (category: planning).
const SKILL_NAME = "Brainstorming Ideas Into Designs";
// First category:"testing" entry in src/data/skills.ts.
const TESTING_SKILL_NAME = "Dispatching Parallel Agents";
// First entry in src/data/hooks.ts (event: PostToolUse).
const HOOK_NAME = "Quality Gate";

/** Open the AgentsPopup from the idea page and switch to the Skills & Hooks tab. */
async function openSkillsHooksTab(dashboard: { page: import("@playwright/test").Page; selectWorkflow: (l: string) => Promise<void>; fillIdea: (t: string) => Promise<void>; openAdvanced: () => Promise<void> }) {
  await dashboard.selectWorkflow(WORKFLOW);
  // Wait for the brief screen to mount before filling — else the fill races the
  // still-mounted home composer and the idea never lands in the brief textarea,
  // leaving Run disabled at TS-F-05 (mirrors dashboard.runWith's guard).
  await expect(
    dashboard.page.getByRole("heading", { name: /Provide the brief/i }),
  ).toBeVisible({ timeout: 15000 });
  await dashboard.fillIdea(IDEA);
  await dashboard.openAdvanced(); // asserts "Workflow configuration"
  // Phase 39 redesign: the old "Skills & Hooks" tab is now the "Workflow" tab
  // (Puzzle icon; still hosts the SkillsHooksTab body unchanged).
  await dashboard.page.getByRole("button", { name: /^Workflow/ }).click();
}

/** The Add/Added button inside a specific skill/hook picker row (deepest match). */
function rowButton(page: import("@playwright/test").Page, rowText: string, btn: RegExp) {
  return page
    .locator("div")
    .filter({ has: page.getByText(rowText, { exact: true }) })
    .filter({ has: page.getByRole("button", { name: btn }) })
    .last()
    .getByRole("button", { name: btn });
}

test.describe("TS-F — Skills & Hooks", () => {
  test.beforeEach(async ({ dashboard }) => {
    await dashboard.goto();
  });

  test("TS-F-01 empty states for skills and hooks", async ({ dashboard }) => {
    await openSkillsHooksTab(dashboard);

    await expect(
      dashboard.page.getByText('No skills attached · click "Add skill" to browse'),
    ).toBeVisible();
    await expect(
      dashboard.page.getByText('No hooks attached · click "Add hook" to browse'),
    ).toBeVisible();
  });

  test("TS-F-02 attach a skill → Add becomes Added, count pill increments", async ({ dashboard }) => {
    const page = dashboard.page;
    await openSkillsHooksTab(dashboard);

    // No skills count pill yet (the pill only renders when attachedSkills > 0).
    await expect(page.getByText('No skills attached · click "Add skill" to browse')).toBeVisible();

    // Open the picker → search input appears.
    await page.getByRole("button", { name: /Add skill/ }).click();
    const search = page.getByPlaceholder("Search skills...");
    await expect(search).toBeVisible();

    // Narrow to the first real skill and attach it.
    await search.fill(SKILL_NAME);
    const addBtn = rowButton(page, SKILL_NAME, /^Add$/);
    await expect(addBtn).toBeVisible();
    await addBtn.click();

    // Its button flips Add → Added (disabled, with the Check icon).
    const addedBtn = rowButton(page, SKILL_NAME, /^Added$/);
    await expect(addedBtn).toBeVisible();
    await expect(addedBtn).toBeDisabled();

    // The Skills section count pill now shows 1 — it's the dark rounded badge
    // immediately following the "Skills" section heading span.
    const skillsCountPill = page
      .locator("span.text-gray-800", { hasText: /^Skills$/ })
      .locator("xpath=following-sibling::span[1]");
    await expect(skillsCountPill).toHaveText("1");
    // The count is a rounded-full badge pill — a reskin-durable shape signal
    // (the dark fill is retokenised by the reskin; the pill shape is not).
    await expect(skillsCountPill).toHaveClass(/rounded-full/);
  });

  test("TS-F-03 skill category pills filter the list", async ({ dashboard }) => {
    const page = dashboard.page;
    await openSkillsHooksTab(dashboard);
    await page.getByRole("button", { name: /Add skill/ }).click();

    // Phase 39 renamed the popup tab to "Workflow", which now collides with the
    // "Workflow" skill-category pill under strict mode. The category pills are the
    // only rounded-full buttons on screen while the skills picker is open (the
    // tab is a border-b-2 button, the hooks picker is closed), so target by that
    // reskin-durable shape + exact label to exclude the tab.
    const catPill = (cat: string) =>
      page.locator("button.rounded-full").filter({ hasText: new RegExp(`^${cat}$`) });

    // Every category pill is present.
    for (const cat of ["All", "Planning", "Testing", "Workflow", "Security", "Debugging", "Collaboration", "Meta"]) {
      await expect(catPill(cat)).toBeVisible();
    }

    // Default ("All"): the planning-category first skill is in the list.
    await expect(page.getByText(SKILL_NAME, { exact: true })).toBeVisible();

    // Filter to Testing → the planning skill drops out, a testing skill appears.
    await catPill("Testing").click();
    await expect(page.getByText(SKILL_NAME, { exact: true })).toHaveCount(0);
    await expect(page.getByText(TESTING_SKILL_NAME, { exact: true }).first()).toBeVisible();

    // Filter to Planning → the planning skill is back, the testing skill drops out.
    await catPill("Planning").click();
    await expect(page.getByText(SKILL_NAME, { exact: true })).toBeVisible();
    await expect(page.getByText(TESTING_SKILL_NAME, { exact: true })).toHaveCount(0);
  });

  test("TS-F-04 hooks picker: search, the known hooks, and event filter pills", async ({ dashboard }) => {
    const page = dashboard.page;
    await openSkillsHooksTab(dashboard);

    await page.getByRole("button", { name: /Add hook/ }).click();
    await expect(page.getByPlaceholder("Search hooks...")).toBeVisible();

    // The 8 hooks include these named ones (read from src/data/hooks.ts).
    for (const name of ["Quality Gate", "Config Protection", "Format + Typecheck on Stop"]) {
      await expect(page.getByText(name, { exact: true }).first()).toBeVisible();
    }

    // Event filter pills.
    for (const ev of ["All Events", "Pre Tool Use", "Post Tool Use", "On Stop", "Session Start", "Session End"]) {
      await expect(page.getByRole("button", { name: ev, exact: true })).toBeVisible();
    }

    // Sanity: the On Stop filter narrows the list (Quality Gate is PostToolUse →
    // drops out; "Format + Typecheck on Stop" is a Stop hook → stays).
    await page.getByRole("button", { name: "On Stop", exact: true }).click();
    await expect(page.getByText("Quality Gate", { exact: true })).toHaveCount(0);
    await expect(page.getByText("Format + Typecheck on Stop", { exact: true }).first()).toBeVisible();
  });

  test("TS-F-05 attached skill + hook are persisted into the run_pipeline payload", async ({ dashboard, mockWs }) => {
    const page = dashboard.page;
    await openSkillsHooksTab(dashboard);

    // Attach one skill.
    await page.getByRole("button", { name: /Add skill/ }).click();
    await page.getByPlaceholder("Search skills...").fill(SKILL_NAME);
    await rowButton(page, SKILL_NAME, /^Add$/).click();
    await expect(rowButton(page, SKILL_NAME, /^Added$/)).toBeVisible();

    // Attach one hook.
    await page.getByRole("button", { name: /Add hook/ }).click();
    await page.getByPlaceholder("Search hooks...").fill(HOOK_NAME);
    await rowButton(page, HOOK_NAME, /^Add$/).click();
    await expect(rowButton(page, HOOK_NAME, /^Added$/)).toBeVisible();

    // The combined tab badge reflects both (1 skill + 1 hook = 2). Phase 39
    // relabelled the tab "Workflow"; the badge is its {totalAttached} span.
    await expect(
      page.getByRole("button", { name: /^Workflow/ }).locator("span", { hasText: /^2$/ }),
    ).toBeVisible();

    // Close the popup, then Run from the idea page. Phase 39 replaced the footer
    // "Save changes" with "Cancel" (config persists live via context/refs, so
    // closing retains the attachments) + a separate "Save workflow" (catalogue).
    await page.getByRole("button", { name: "Cancel", exact: true }).click();
    await expect(page.getByText("Workflow configuration")).toBeHidden();

    await expect(dashboard.runButton()).toBeEnabled();
    await dashboard.runButton().click();

    const f = await mockWs.waitForClientFrame("run_pipeline");

    // attached_skills: non-empty, each item carries id/name/content.
    expect(Array.isArray(f.attached_skills)).toBe(true);
    const skills = f.attached_skills as Array<Record<string, unknown>>;
    expect(skills.length).toBeGreaterThan(0);
    for (const s of skills) {
      expect(typeof s.id).toBe("string");
      expect((s.id as string).length).toBeGreaterThan(0);
      expect(typeof s.name).toBe("string");
      expect((s.name as string).length).toBeGreaterThan(0);
      expect(typeof s.content).toBe("string");
      expect((s.content as string).length).toBeGreaterThan(0);
    }
    expect(skills.some((s) => s.name === SKILL_NAME)).toBe(true);

    // attached_hooks: non-empty, each item carries id/name/event.
    expect(Array.isArray(f.attached_hooks)).toBe(true);
    const hooks = f.attached_hooks as Array<Record<string, unknown>>;
    expect(hooks.length).toBeGreaterThan(0);
    for (const h of hooks) {
      expect(typeof h.id).toBe("string");
      expect((h.id as string).length).toBeGreaterThan(0);
      expect(typeof h.name).toBe("string");
      expect((h.name as string).length).toBeGreaterThan(0);
      expect(typeof h.event).toBe("string");
      expect((h.event as string).length).toBeGreaterThan(0);
    }
    expect(hooks.some((h) => h.name === HOOK_NAME)).toBe(true);
  });

  test("TS-F-06 attachment survives closing and reopening the popup", async ({ dashboard }) => {
    const page = dashboard.page;
    await openSkillsHooksTab(dashboard);

    // Attach a skill.
    await page.getByRole("button", { name: /Add skill/ }).click();
    await page.getByPlaceholder("Search skills...").fill(SKILL_NAME);
    await rowButton(page, SKILL_NAME, /^Add$/).click();
    await expect(rowButton(page, SKILL_NAME, /^Added$/)).toBeVisible();

    // Close the popup (Phase 39: footer "Save changes" → "Cancel").
    await page.getByRole("button", { name: "Cancel", exact: true }).click();
    await expect(page.getByText("Workflow configuration")).toBeHidden();

    // Reopen via Advanced → Workflow tab (formerly "Skills & Hooks").
    await dashboard.openAdvanced();
    await page.getByRole("button", { name: /^Workflow/ }).click();

    // The attached skill is listed in the "attached" section (CheckCircle row),
    // and reopening the picker shows it as Added (context persisted globally).
    await expect(page.getByText(SKILL_NAME, { exact: true }).first()).toBeVisible();
    await page.getByRole("button", { name: /Add skill/ }).click();
    await page.getByPlaceholder("Search skills...").fill(SKILL_NAME);
    await expect(rowButton(page, SKILL_NAME, /^Added$/)).toBeVisible();
  });
});
