/**
 * TS-F — Skills & Hooks in the Advanced popup (AgentsPopup). Proves the
 * attach UX (empty states, pickers, search, category/event filters, count
 * pills), payload threading into `run_pipeline` (attached_hooks), and
 * persistence across popup reopen via the global SkillsHooksContext.
 *
 * ADR-0010 split the old run-level "Skills & Hooks" tab:
 *   • SKILLS are attached PER AGENT (`Step.skills`) through the shared
 *     composer/AgentSkillsPicker — in this popup: select a canvas node, then the
 *     config rail's "Skills" tab. There is no run-level skills picker any more,
 *     so `attached_skills` is no longer a run_pipeline field.
 *   • HOOKS stay run-level: the popup's "Workflow" tab is now hooks-only
 *     (HooksTab), bound to SkillsHooksContext, and ride `attached_hooks`.
 *
 * Flow: from home → select `user_stories` ("Generate product requirements") +
 * type a brief → click `Advanced` (opens AgentsPopup). We do NOT run first (the
 * Advanced button only lives on IdeaInputPage); for TS-F-05 we close the popup,
 * then Run from the same idea page.
 *
 * Names come from the catalogs the UI renders (fixtures/mockApi.ts mirrors the
 * real scans): hooks from backend/hooks/global/<id>/HOOK.md, skills from
 * backend/skills/global/<id>/SKILL.md (plus the composer fixtures' Emoji/Joke/
 * HTML Page).
 */
import { test, expect } from "../fixtures/test";
import type { Page } from "@playwright/test";
import type { DashboardPage } from "../fixtures/dashboard";

const WORKFLOW = "Generate product requirements"; // TYPE_CONFIG.user_stories.tag
const IDEA = "Generate epics for a refunds workflow";
// A user_stories agent node to attach per-agent skills to.
const AGENT_ID = "domain-analyst";
// A planning-category skill and a testing-category skill.
const SKILL_NAME = "Coding Standards & Best Practices";
const TESTING_SKILL_NAME = "Test-Driven Development Workflow";
// A PostToolUse hook.
const HOOK_NAME = "Quality Gate";

/** Land on the brief screen with an idea typed, then open the Advanced popup. */
async function openPopup(dashboard: DashboardPage) {
  await dashboard.selectWorkflow(WORKFLOW);
  // Wait for the brief screen to mount before filling — else the fill races the
  // still-mounted home composer and the idea never lands in the brief textarea,
  // leaving Run disabled at TS-F-05 (mirrors dashboard.runWith's guard).
  await expect(
    dashboard.page.getByRole("heading", { name: /Provide the brief/i }),
  ).toBeVisible({ timeout: 15000 });
  await dashboard.fillIdea(IDEA);
  await dashboard.openAdvanced(); // asserts the "Advanced Workflow Configuration" heading
}

/** Open the popup on its run-level "Workflow" (hooks) tab. Scoped to the popup
 *  tab strip: the embedded canvas rail has its own "Workflow" toggle. */
async function openHooksTab(dashboard: DashboardPage) {
  await openPopup(dashboard);
  await dashboard.advancedTab(/^Workflow/).click();
}

/** Open the popup and the per-agent skills picker for AGENT_ID. */
async function openAgentSkills(dashboard: DashboardPage) {
  await openPopup(dashboard);
  await dashboard.page.getByTestId(`canvas-node-${AGENT_ID}`).click();
  await dashboard.page.getByRole("tab", { name: "Skills" }).click();
  const picker = dashboard.page.getByTestId(`agent-skills-picker-${AGENT_ID}`);
  await expect(picker).toBeVisible();
  return picker;
}

/** The Add/Added button inside a specific hook picker row (deepest match). */
function rowButton(page: Page, rowText: string, btn: RegExp) {
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
    const page = dashboard.page;
    await openHooksTab(dashboard);
    await expect(page.getByText('No hooks attached · click "Add hook" to browse')).toBeVisible();
    // ADR-0010: the run-level skills picker is gone from this tab.
    await expect(page.getByRole("button", { name: /Add skill/ })).toHaveCount(0);

    // Per-agent: a fresh agent has no skill attached — every row offers "Add".
    await dashboard.advancedTab(/^Agents/).click();
    await page.getByTestId(`canvas-node-${AGENT_ID}`).click();
    await page.getByRole("tab", { name: "Skills" }).click();
    const picker = page.getByTestId(`agent-skills-picker-${AGENT_ID}`);
    await expect(picker.getByRole("button", { name: /^Add / }).first()).toBeVisible();
    await expect(picker.getByRole("button", { name: /^Remove / })).toHaveCount(0);
  });

  test("TS-F-02 attach a skill → Add becomes Remove, the node shows the skill", async ({ dashboard }) => {
    const page = dashboard.page;
    const picker = await openAgentSkills(dashboard);

    await picker.getByRole("button", { name: `Add ${SKILL_NAME}` }).click();
    // The row's toggle flips Add → Remove.
    await expect(picker.getByRole("button", { name: `Remove ${SKILL_NAME}` })).toBeVisible();
    await expect(picker.getByRole("button", { name: `Add ${SKILL_NAME}` })).toHaveCount(0);
    // The canvas node lists the attached skill id as a removable chip.
    await expect(
      page.getByTestId(`canvas-node-${AGENT_ID}`).getByRole("button", { name: "Remove coding-standards" }),
    ).toBeVisible();
  });

  test("TS-F-03 skill category pills filter the list", async ({ dashboard }) => {
    const picker = await openAgentSkills(dashboard);

    // Search + category pills render once >6 skills are compatible.
    await expect(picker.getByTestId("agent-skills-search")).toBeVisible();
    for (const cat of ["All", "Planning", "Testing", "Security", "Debugging"]) {
      await expect(picker.getByRole("button", { name: cat, exact: true })).toBeVisible();
    }
    // Default ("All"): both skills are listed.
    await expect(picker.getByRole("button", { name: `Add ${SKILL_NAME}` })).toBeVisible();
    await expect(picker.getByRole("button", { name: `Add ${TESTING_SKILL_NAME}` })).toBeVisible();
    // Filter to Testing → the planning skill drops out, the testing skill stays.
    await picker.getByRole("button", { name: "Testing", exact: true }).click();
    await expect(picker.getByRole("button", { name: `Add ${SKILL_NAME}` })).toHaveCount(0);
    await expect(picker.getByRole("button", { name: `Add ${TESTING_SKILL_NAME}` })).toBeVisible();
    // Filter to Planning → back again, the testing skill drops out.
    await picker.getByRole("button", { name: "Planning", exact: true }).click();
    await expect(picker.getByRole("button", { name: `Add ${SKILL_NAME}` })).toBeVisible();
    await expect(picker.getByRole("button", { name: `Add ${TESTING_SKILL_NAME}` })).toHaveCount(0);
    // Search narrows by name.
    await picker.getByRole("button", { name: "All", exact: true }).click();
    await picker.getByTestId("agent-skills-search").fill("Test-Driven");
    await expect(picker.getByRole("button", { name: `Add ${TESTING_SKILL_NAME}` })).toBeVisible();
    await expect(picker.getByRole("button", { name: `Add ${SKILL_NAME}` })).toHaveCount(0);
  });

  test("TS-F-04 hooks picker: search, the known hooks, and event filter pills", async ({ dashboard }) => {
    const page = dashboard.page;
    await openHooksTab(dashboard);
    await page.getByRole("button", { name: /Add hook/ }).click();
    await expect(page.getByPlaceholder("Search hooks...")).toBeVisible();
    // The catalog's hooks include these named ones.
    for (const name of ["Quality Gate", "Config Protection", "Format + Typecheck on Stop"]) {
      await expect(page.getByText(name, { exact: true }).first()).toBeVisible();
    }
    // Event filter pills — the endpoint's derived event list (raw event names).
    for (const ev of ["All", "PreToolUse", "PostToolUse", "Stop", "SessionStart"]) {
      await expect(page.getByRole("button", { name: ev, exact: true })).toBeVisible();
    }
    // The Stop filter narrows the list (Quality Gate is PostToolUse → drops out;
    // "Format + Typecheck on Stop" is a Stop hook → stays).
    await page.getByRole("button", { name: "Stop", exact: true }).click();
    await expect(page.getByText("Quality Gate", { exact: true })).toHaveCount(0);
    await expect(page.getByText("Format + Typecheck on Stop", { exact: true }).first()).toBeVisible();
    // Search narrows by name.
    await page.getByRole("button", { name: "All", exact: true }).click();
    await page.getByPlaceholder("Search hooks...").fill("Config");
    await expect(page.getByText("Config Protection", { exact: true }).first()).toBeVisible();
    await expect(page.getByText("Quality Gate", { exact: true })).toHaveCount(0);
  });

  test("TS-F-05 an attached hook is persisted into the run_pipeline payload", async ({ dashboard, mockSse }) => {
    const page = dashboard.page;
    await openHooksTab(dashboard);
    await page.getByRole("button", { name: /Add hook/ }).click();
    await page.getByPlaceholder("Search hooks...").fill(HOOK_NAME);
    await rowButton(page, HOOK_NAME, /^Add$/).click();
    await expect(rowButton(page, HOOK_NAME, /^Added$/)).toBeVisible();
    // The tab badge is its {totalAttached} span (1 hook).
    await expect(dashboard.advancedTab(/^Workflow/).locator("span", { hasText: /^1$/ })).toBeVisible();

    // Close the popup (config persists live via context), then Run.
    await page.getByRole("button", { name: "Cancel", exact: true }).click();
    await expect(dashboard.advancedHeading()).toBeHidden();
    await expect(dashboard.runButton()).toBeEnabled();
    await dashboard.runButton().click();
    const f = await mockSse.waitForCommand("run_pipeline");

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
    // ADR-0010: no run-level skills bag on the wire.
    expect(f.attached_skills).toBeUndefined();
  });

  test("TS-F-06 attachment survives closing and reopening the popup", async ({ dashboard }) => {
    const page = dashboard.page;
    await openHooksTab(dashboard);
    await page.getByRole("button", { name: /Add hook/ }).click();
    await page.getByPlaceholder("Search hooks...").fill(HOOK_NAME);
    await rowButton(page, HOOK_NAME, /^Add$/).click();
    await expect(rowButton(page, HOOK_NAME, /^Added$/)).toBeVisible();

    await page.getByRole("button", { name: "Cancel", exact: true }).click();
    await expect(dashboard.advancedHeading()).toBeHidden();

    // Reopen → the hook is still attached (SkillsHooksContext is global) and the
    // picker shows it as Added.
    await dashboard.openAdvanced();
    await dashboard.advancedTab(/^Workflow/).click();
    await expect(page.getByText('No hooks attached · click "Add hook" to browse')).toHaveCount(0);
    await expect(page.getByText(HOOK_NAME, { exact: true }).first()).toBeVisible();
    await page.getByRole("button", { name: /Add hook/ }).click();
    await page.getByPlaceholder("Search hooks...").fill(HOOK_NAME);
    await expect(rowButton(page, HOOK_NAME, /^Added$/)).toBeVisible();
  });
});
