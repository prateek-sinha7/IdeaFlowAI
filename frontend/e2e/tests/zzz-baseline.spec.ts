/**
 * FIDELITY CAPTURE spec (our-side of the D39-6 oracle) — RETAINED, but GATED.
 *
 * Drives our CURRENT run/execution screen into settled / live / failed via the
 * mocked harness and screenshots every tab into `frontend/e2e/fidelity/shots/
 * current/`, tagged `{surface}__{state}` (e.g. `steps__settled`, `audit__failed`,
 * `leftlane__live`). These become the RIGHT column of the side-by-side gallery
 * (`assemble-gallery.mjs`); the LEFT column comes from `capture-mocks.mjs`.
 *
 * It is NOT an assertion suite: gated behind FIDELITY_CAPTURE=1 so a normal
 * `npm run e2e` skips it entirely (it never gates CI green).
 *   Capture:  FIDELITY_CAPTURE=1 npm run e2e -- zzz-baseline
 *
 * The home-grid / run-family / audit REST stubs it used to define inline now
 * live in the SHARED MockApi fixture (INV-12 — no dual stub); this spec only
 * drives the WS timeline + screenshots.
 */
import { test, expect } from "../fixtures/test";
import { AGENTS } from "../fixtures/scenarios";
import type { MockWs } from "../fixtures/mockWs";
import type { Page } from "@playwright/test";
import { mkdirSync } from "fs";
import { resolve } from "path";

// Only run when explicitly capturing — a normal `npm run e2e` skips the file.
test.skip(!process.env.FIDELITY_CAPTURE, "fidelity capture only (set FIDELITY_CAPTURE=1)");

// Playwright's cwd is the config dir (frontend/); write repo-relative outputs.
const OUT = resolve(process.cwd(), "e2e/fidelity/shots/current");
mkdirSync(OUT, { recursive: true });

test.use({ viewport: { width: 1440, height: 900 } });

const PROTO_HTML =
  "<!DOCTYPE html><html><head><title>Apple Reference</title></head><body>" +
  "<header>northwind</header><h1>Titanium. So strong. So light. So Pro.</h1>" +
  "<p>The most advanced reference build we've ever made.</p></body></html>";

/** Screenshot our surface, tagged `{surface}__{state}`. */
const shot = async (page: Page, surface: string, state: string) =>
  page.screenshot({ path: `${OUT}/${surface}__${state}.png`, fullPage: false });

// Phase 39 (RUNUI-06/07) — the run-header row crop (Version ▾ / Share / Download
// in settled; the status badge + version chip in live/failed). The right column
// starts after the ~360px lane and below the ~64px top bar. `header__{state}`
// pairs against the target mock header crop in the fidelity gallery.
const HEADER_CLIP = { x: 360, y: 64, width: 1080, height: 132 };
const headerShot = async (page: Page, state: string, clip = HEADER_CLIP) =>
  page.screenshot({ path: `${OUT}/header__${state}.png`, clip });

// The current launch flow: click the home deliverable row → a "Provide the brief"
// wizard screen → fill the brief → "Run workflow" → run_pipeline → execution view.
// The home / family / audit REST stubs are now the shared MockApi's (INV-12).
async function launch(page: Page, ws: MockWs, idea: string) {
  await page.getByRole("button", { name: /Generate product requirements/i }).first().click();
  await expect(page.getByRole("heading", { name: /Provide the brief/i })).toBeVisible({ timeout: 15000 });
  const brief = page.locator("textarea").first();
  await brief.click();
  await brief.fill(idea);
  const run = page.getByRole("button", { name: /Run workflow/i });
  await expect(run).toBeEnabled({ timeout: 10000 });
  await run.click();
  await ws.waitForClientFrame("run_pipeline", 20000);
  await page.getByTestId("execution-chat-lane").waitFor({ state: "visible", timeout: 15000 }).catch(() => {});
  await ws.ready();
}

const CTX = [
  { type: "summary", agent_name: "prompt.md", summary_length: 120, full_output_length: 200 },
  { type: "artifact", artifact_type: "clarifications.md", artifact_size_chars: 1900 },
];

// The run's input attachments — surfaced as the mock's chip tray above the
// composer. Seeded onto the brief turn so the lane derives them live.
const BRIEF_ATTACH = [
  { kind: "file", name: "brief.md", sizeBytes: 1240, retained: true },
  { kind: "image", name: "apple-hero.png", sizeBytes: 512_000, retained: true },
  { kind: "file", name: "voice-note.m4a", mimeType: "audio/mp4", sizeBytes: 48_000, retained: true },
  { kind: "file", name: "spec.pdf", sizeBytes: 98_000, retained: true },
];

const CLARIFY_Q = [
  { id: "q1", text: "Which pages should the reference cover?", options: ["Home + 5", "Home only"], answerType: "single_choice" },
  { id: "q2", text: "Light or dark theme?", options: ["Light", "Dark"], answerType: "single_choice" },
  { id: "q3", text: "Any real brand assets?", options: ["Reference-only", "Use brand"], answerType: "single_choice" },
];

/** Seed the user's brief turn (with run attachments) into the chat transcript. */
async function seedBrief(mockWs: MockWs, text: string) {
  mockWs.chatMessage({ messageId: "u-brief", text, attachments: BRIEF_ATTACH });
}

test("CAPTURE settled prototype run", async ({ dashboard, mockWs, page }) => {
  test.setTimeout(120_000);
  await dashboard.goto();
  await launch(page, mockWs, "build prototype mimicking apple website just for reference");

  const agents = AGENTS.od_prototype; // specify, plan, build, validate
  // A run created ~23h ago so the settled header shows a realistic relative age.
  const createdAt = new Date(Date.now() - 23 * 3_600_000).toISOString();
  mockWs.start(agents, { pipelineType: "od_prototype", runId: "run-e2e-1", createdAt });
  // Seed the conversation: the user's brief turn (+ run attachments) so the
  // transcript renders bubbles + the attachment-chip tray like the mock.
  await seedBrief(mockWs, "build prototype mimicking apple website just for reference");
  mockWs.chatNarration("Before I build, I confirmed the scope with a few clarifications and locked one shared design system.");
  mockWs.plannerStart();
  mockWs.plannerComplete("Build an Apple-style reference prototype", "PROCEED");

  // Clarify round — answer it so pipelineState.clarifications is populated and
  // the settled "N clarifying questions" inline card renders (live count).
  mockWs.questionnaireReady(CLARIFY_Q);
  await page.getByTestId("chat-clarify-actions").waitFor({ state: "visible", timeout: 10_000 }).catch(() => {});
  await page.getByTestId("chat-clarify-chip").first().click({ timeout: 6_000 }).catch(() => {});
  await page.getByTestId("chat-clarify-submit").click({ timeout: 6_000 }).catch(() => {});
  mockWs.questionnaireComplete();
  mockWs.chatNarration("Got it — running the build pipeline now.");

  // 1) Spec Writer (+ gate)
  mockWs.agentStart("prototype-specify");
  mockWs.emit("agent_input", { agent_id: "prototype-specify", context_message: "You are the Spec Writer. Read prompt.md and clarifications.md. Produce spec.md: six pages on one shared design system, a single type scale and a 12-column grid. Reference-only, light theme, no real trademarks.", context_sources: CTX });
  mockWs.agentThinking("prototype-specify", "The prompt asks for an Apple-style reference site and the clarifications lock it to a static, reference-only build. I will define six pages sharing one design system, type scale and 12-column grid.");
  mockWs.emit("tool_call", { agent_id: "prototype-specify", tool: "read_file", args: { path: "prompt.md" } });
  mockWs.emit("tool_result", { agent_id: "prototype-specify", tool: "read_file", result: "57 B" });
  mockWs.emit("tool_call", { agent_id: "prototype-specify", tool: "write_file", args: { path: "spec.md" } });
  mockWs.emit("tool_result", { agent_id: "prototype-specify", tool: "write_file", result: "36.4 KB" });
  // Real spec-writer output is ALWAYS wrapped in <spec>…</spec> (prototype-specify/AGENT.md
  // makes an unwrapped response a "CRITICAL FAILURE"), so the settled L2 detail renders the
  // sections/pages artifact card off the wrapper. Feed the faithful wrapped form.
  mockWs.agentChunk("prototype-specify", "<spec>\n# Apple Reference — Specification\n\n## Home\nLanding hero, product grid and closing CTA on the shared grid.\n## Product detail\nGallery, spec table and buy-bar.\n## Compare\nComparison table with a sticky header.\n## Accessories\nAccessories grid plus the search overlay.\n## Search\nSearch overlay with keyboard focus trapping.\n## Shared chrome\nShared nav + footer, one type scale, a 12-column grid.\n</spec>");
  mockWs.agentComplete("prototype-specify", { inputTokens: 2400, outputTokens: 12100, totalTokens: 30100, duration: 84 });
  mockWs.reviewGateReady({ gateKey: "spec", agentId: "prototype-specify", agentName: "Spec Writer", output: "Specification approved" });
  mockWs.reviewGateApproved();

  // 2) Task Planner
  mockWs.agentStart("prototype-plan");
  mockWs.emit("agent_input", { agent_id: "prototype-plan", context_message: "You are the Task Planner. Decompose spec.md into an ordered, dependency-aware build task list.", context_sources: [{ type: "artifact", artifact_type: "spec.md", artifact_size_chars: 36400 }] });
  mockWs.agentThinking("prototype-plan", "With the spec fixed I decompose it into seven tasks so shared scaffolding lands first.");
  mockWs.emit("tool_call", { agent_id: "prototype-plan", tool: "write_file", args: { path: "tasks.md" } });
  mockWs.emit("tool_result", { agent_id: "prototype-plan", tool: "write_file", result: "36.1 KB" });
  // Real planner output is a <tasks> block (prototype-plan/AGENT.md), so the settled
  // Task-Planner detail selects the tasks artifact card off the wrapper.
  mockWs.agentChunk("prototype-plan", "<tasks>\n## Task 1: Scaffold shared layout, nav & footer\n**Goal**: shared nav, footer and the 12-column grid every page inherits.\n## Task 2: Home / landing page\n**Goal**: hero, product grid and CTA on the shared type scale.\n## Task 3: Compare page\n**Goal**: comparison grid reusing the shared table + type scale.\n</tasks>");
  mockWs.agentComplete("prototype-plan", { totalTokens: 42200, duration: 47 });

  // 3) Build Agent (+ wave / subagents)
  mockWs.agentStart("prototype-build");
  // Seed the Build Agent's assembled context (tasks.md + spec.md) so the L2
  // "Context received" panel shows real sources fed in, not "0 sources".
  mockWs.emit("agent_input", { agent_id: "prototype-build", context_message: "You are the Build Agent. Read spec.md and tasks.md, then build each task in dependency order, verifying each before moving on.", context_sources: [{ type: "artifact", artifact_type: "tasks.md", artifact_size_chars: 36100 }, { type: "artifact", artifact_type: "spec.md", artifact_size_chars: 36400 }] });
  mockWs.agentThinking("prototype-build", "I build task by task and verify each before moving on.");
  mockWs.waveStarted(0, "prototype-build", ["t1", "t2", "t3"]);
  mockWs.subagentSpawned(0, "prototype-build", "build-task-1", 1, "running");
  mockWs.subagentResult(0, "prototype-build", "build-task-1", 1, "completed");
  mockWs.subagentSpawned(0, "prototype-build", "build-task-2", 2, "running");
  mockWs.subagentResult(0, "prototype-build", "build-task-2", 2, "completed");
  mockWs.waveCompleted(0, "prototype-build");
  // task_progress → protoCompletedTasks (title + summary per task) so the L2
  // construction block shows titled task rows and the L3 task-detail renders each
  // task's live reasoning (summary). Live data — never the mock's fixed transcript.
  mockWs.emit("task_progress", {
    completed_count: 3,
    completed_tasks: [
      { number: 1, title: "Scaffold shared layout, nav & footer", summary: "Built the shared nav, footer and the 12-column grid every page inherits, so the six pages stay on one design system." },
      { number: 2, title: "Home / landing page", summary: "Composed the landing hero and feature grid on the shared type scale, wired the primary nav links." },
      { number: 3, title: "Compare page", summary: "Rendered the product comparison grid reusing the shared table + type scale; no real trademarks." },
    ],
  });
  mockWs.agentChunk("prototype-build", "[HTML artifact — apple-reference-prototype.html — 151.6 KB]");
  mockWs.agentComplete("prototype-build", { totalTokens: 1102240, duration: 1180 });

  // 4) Validation Agent
  mockWs.agentStart("prototype-validate");
  // Real analyzer/validator output is an <analysis> block (prototype-analyze/AGENT.md), so the
  // settled detail selects the checks artifact card off the wrapper + the verdict text.
  mockWs.agentChunk("prototype-validate", "<analysis>\n### Readiness verdict\nREADY TO BUILD\n### Coverage\nCoverage 100% — every spec section maps to at least one task.\n</analysis>");
  mockWs.agentComplete("prototype-validate", { totalTokens: 8000, duration: 33 });

  // The deliverable filename + version ride pipeline_complete (D39-4). The lane
  // renders the SINGLE mock-styled deliverable card from pipelineState (INV-12) —
  // no interim narrator ResultCard stand-in is seeded.
  mockWs.complete({ pipelineType: "od_prototype", finalOutput: PROTO_HTML, deliverableFilename: "apple-reference-prototype.html", deliverableMimetype: "text/html", deliverableVersion: 1, totalTokens: 14_620_000, totalDuration: 1446 });

  await page.waitForTimeout(1500);
  await shot(page, "full", "settled");

  // tabs (role="tab" — Tabs.tsx:39; short per-click timeout so a miss fails fast)
  const tab = (name: string) => page.getByRole("tab", { name: new RegExp(name, "i") }).first();
  await tab("Preview").click({ timeout: 6000 }).catch(() => {}); await page.waitForTimeout(900); await shot(page, "preview", "settled");
  await tab("Steps").click({ timeout: 6000 }).catch(() => {}); await page.waitForTimeout(900); await shot(page, "steps", "settled");
  // drill into the first agent's L2 detail (the Steps overview spine row — NOT the
  // left-lane pipeline mini; scope to the steps-agent-row testid so we open L2).
  await page.getByTestId("steps-agent-row").first().click({ timeout: 6000 }).catch(() => {});
  await page.waitForTimeout(900); await shot(page, "steps-detail", "settled");
  // back to overview, then drill into the BUILD AGENT's L2 → the construction
  // artifact block (waves + navigable task rows), then a task row → L3 task detail.
  await page.getByRole("button", { name: /Steps \/ Spec Writer/i }).click({ timeout: 6000 }).catch(() => {});
  await page.waitForTimeout(400);
  await page.getByTestId("steps-agent-row").filter({ hasText: "Build Agent" }).first().click({ timeout: 6000 }).catch(() => {});
  await page.waitForTimeout(600);
  await page.getByTestId("construction-block").scrollIntoViewIfNeeded().catch(() => {});
  await page.waitForTimeout(400); await shot(page, "steps-construction", "settled");
  await page.getByTestId("construction-task-row").first().click({ timeout: 6000 }).catch(() => {});
  await page.waitForTimeout(700); await shot(page, "steps-task", "settled");
  await tab("Files").click({ timeout: 6000 }).catch(() => {}); await page.waitForTimeout(900); await shot(page, "files", "settled");
  // Sub-view: scroll the Files pane to the bottom so the "Run input" card pair
  // (below the fold on a settled run with 4 agent outputs) is fully captured.
  await page.evaluate(() => {
    const panes = Array.from(document.querySelectorAll<HTMLElement>(".overflow-y-auto"));
    const pane = panes.find((el) => el.scrollHeight > el.clientHeight && el.textContent?.includes("Run input"));
    if (pane) pane.scrollTop = pane.scrollHeight;
  });
  await page.waitForTimeout(500); await shot(page, "files-runinput", "settled");
  await tab("Audit").click({ timeout: 6000 }).catch(() => {}); await page.waitForTimeout(1200); await shot(page, "audit", "settled");
  // Audit sub-view: expand the first log entry so the "What is this?" explainer +
  // key/value detail body is captured (the human WILL catch an unshown section).
  await page.getByTestId("audit-row-toggle").first().click({ timeout: 6000 }).catch(() => {});
  await page.waitForTimeout(500); await shot(page, "audit-expanded", "settled");
  // left-lane clip (the conversation column) — reset to Preview first so it is calm
  await tab("Preview").click({ timeout: 6000 }).catch(() => {}); await page.waitForTimeout(600);
  await page.screenshot({ path: `${OUT}/leftlane__settled.png`, clip: { x: 0, y: 64, width: 360, height: 836 } });

  // Phase 39 run header (settled) — Version ▾ / Share / Download, closed then with
  // the Version menu OPEN (the human WILL catch an unshown state).
  await headerShot(page, "settled");
  const verBtn = page.getByRole("button", { name: /choose version/i }).first();
  await verBtn.click({ timeout: 6000 }).catch(() => {});
  await page.waitForTimeout(500);
  await headerShot(page, "settledmenu", { x: 360, y: 64, width: 1080, height: 360 });
  await verBtn.click({ timeout: 3000 }).catch(() => {}); // close the menu
});

test("CAPTURE live streaming run", async ({ dashboard, mockWs, page }) => {
  test.setTimeout(120_000);
  await dashboard.goto();
  await launch(page, mockWs, "build prototype mimicking apple website just for reference");
  const agents = AGENTS.od_prototype;
  mockWs.start(agents, { pipelineType: "od_prototype", runId: "run-e2e-1" });
  await seedBrief(mockWs, "build prototype mimicking apple website just for reference");
  mockWs.plannerStart();
  mockWs.plannerComplete("Build an Apple-style reference prototype", "PROCEED");
  // Answer a clarify round so the building 'N clarifications answered · task plan
  // approved' note renders (live count).
  mockWs.questionnaireReady(CLARIFY_Q);
  await page.getByTestId("chat-clarify-actions").waitFor({ state: "visible", timeout: 10_000 }).catch(() => {});
  await page.getByTestId("chat-clarify-chip").first().click({ timeout: 6_000 }).catch(() => {});
  await page.getByTestId("chat-clarify-submit").click({ timeout: 6_000 }).catch(() => {});
  mockWs.questionnaireComplete();
  mockWs.agentStart("prototype-specify"); mockWs.agentChunk("prototype-specify", "# Spec…"); mockWs.agentComplete("prototype-specify", { totalTokens: 30100, duration: 84 });
  mockWs.agentStart("prototype-plan"); mockWs.agentChunk("prototype-plan", "# Build tasks…"); mockWs.agentComplete("prototype-plan", { totalTokens: 42200, duration: 47 });
  // 3rd agent left RUNNING (streaming, no complete)
  mockWs.agentStart("prototype-build");
  mockWs.agentThinking("prototype-build", "building task 4 of 7 — compare page");
  mockWs.agentChunk("prototype-build", "<section class=\"compare\">building…");
  await page.waitForTimeout(1400);
  await shot(page, "full", "live");
  // Phase 39 run header (live) — the streaming status badge + 'vN draft' chip +
  // disabled Share (no Download while building).
  await headerShot(page, "live");
  // Phase 39 (RUNUI-06/07) — the Preview browser chrome in its STREAMING variant
  // (the 'building …' URL + the indeterminate progress bar, no image placeholder).
  // The Preview tab is the default; click to be explicit, then capture preview__live.
  await page.getByRole("tab", { name: /Preview/i }).first().click({ timeout: 6000 }).catch(() => {});
  await page.waitForTimeout(700); await shot(page, "preview", "live");
  await page.getByRole("tab", { name: /Steps/i }).first().click({ timeout: 6000 }).catch(() => {});
  await page.waitForTimeout(900); await shot(page, "steps", "live");
  await page.screenshot({ path: `${OUT}/leftlane__live.png`, clip: { x: 0, y: 64, width: 360, height: 836 } });
});

test("CAPTURE live — clarify-awaiting lane", async ({ dashboard, mockWs, page }) => {
  test.setTimeout(120_000);
  await dashboard.goto();
  await launch(page, mockWs, "build prototype mimicking apple website just for reference");
  const agents = AGENTS.od_prototype;
  mockWs.start(agents, { pipelineType: "od_prototype", runId: "run-e2e-1" });
  await seedBrief(mockWs, "build prototype mimicking apple website just for reference");
  mockWs.plannerStart();
  mockWs.plannerComplete("Build an Apple-style reference prototype", "CLARIFY_REQUIRED");
  // Questions surface and the lane pauses in the clarify state (NOT answered —
  // capture the Awaiting-you clarify card + the clarify composer).
  mockWs.questionnaireReady(CLARIFY_Q);
  await page.getByTestId("chat-clarify-actions").waitFor({ state: "visible", timeout: 10_000 }).catch(() => {});
  // The tall clarify composer squeezes the scroll region — pin it to the bottom
  // so the "Awaiting you" clarify status card is visible above the composer.
  await page.getByTestId("chat-transcript").evaluate((el) => { el.scrollTop = el.scrollHeight; }).catch(() => {});
  await page.waitForTimeout(700);
  await page.screenshot({ path: `${OUT}/leftlane__clarify.png`, clip: { x: 0, y: 64, width: 360, height: 836 } });
});

test("CAPTURE live — gate-awaiting lane", async ({ dashboard, mockWs, page }) => {
  test.setTimeout(120_000);
  await dashboard.goto();
  await launch(page, mockWs, "build prototype mimicking apple website just for reference");
  const agents = AGENTS.od_prototype;
  mockWs.start(agents, { pipelineType: "od_prototype", runId: "run-e2e-1" });
  await seedBrief(mockWs, "build prototype mimicking apple website just for reference");
  mockWs.plannerStart();
  mockWs.plannerComplete("Build an Apple-style reference prototype", "PROCEED");
  // An agent produces output and a review gate opens — the lane pauses in the
  // gate state (NOT approved — capture the Awaiting-you approval card + gate UI).
  mockWs.agentStart("prototype-specify");
  mockWs.agentChunk("prototype-specify", "# Apple Reference — Specification\n\nSix pages, one design system.");
  mockWs.reviewGateReady({ gateKey: "spec", agentId: "prototype-specify", agentName: "Spec Writer", output: "Specification ready for your approval." });
  await page.getByTestId("chat-gate-actions").waitFor({ state: "visible", timeout: 10_000 }).catch(() => {});
  await page.waitForTimeout(700);
  await page.screenshot({ path: `${OUT}/leftlane__gate.png`, clip: { x: 0, y: 64, width: 360, height: 836 } });
});

// ── Phase 42 (W0 oracle) — PAUSED / PLANNING states ──────────────────────────
// These pause our run screen AT planning / clarify-awaiting / gate-awaiting and
// screenshot WITHOUT advancing past them (the opposite of the settled/live flow
// above, which answers clarify + approves the gate immediately). At Wave 1 our
// screen is still PRE-fix: the legacy full-screen right-panel takeover
// (PlanningOverlay / QuestionnairePanel / ReviewGatePanel) still owns the right
// column during these phases, so the "Steps" tab is not mounted and the
// `tab("Steps")` click best-effort no-ops — that captured legacy takeover IS the
// correct "before" baseline the later waves regenerate against the mock.

/** role="tab" locator (short per-click timeout so a miss fails fast, like the settled flow). */
const stepsTab = (page: Page) => page.getByRole("tab", { name: /Steps/i }).first();

test("CAPTURE paused — planning", async ({ dashboard, mockWs, page }) => {
  test.setTimeout(120_000);
  await dashboard.goto();
  await launch(page, mockWs, "build prototype mimicking apple website just for reference");
  const agents = AGENTS.od_prototype;
  mockWs.start(agents, { pipelineType: "od_prototype", runId: "run-e2e-1" });
  await seedBrief(mockWs, "build prototype mimicking apple website just for reference");
  // running & 0 agents & no clarify & no gate → §2 branch 1 (PlanningOverlay).
  // STOP here: do NOT call plannerComplete — capture the pre-agent planning state.
  mockWs.plannerStart();
  await page.waitForTimeout(1200);
  await shot(page, "full", "planning");
  // Best-effort Steps tab (dead during the pre-fix takeover — captures whatever shows).
  await stepsTab(page).click({ timeout: 6000 }).catch(() => {});
  await page.waitForTimeout(700);
  await page.screenshot({ path: `${OUT}/leftlane__planning.png`, clip: { x: 0, y: 64, width: 360, height: 836 } });
});

test("CAPTURE paused — clarify-awaiting", async ({ dashboard, mockWs, page }) => {
  test.setTimeout(120_000);
  await dashboard.goto();
  await launch(page, mockWs, "build prototype mimicking apple website just for reference");
  const agents = AGENTS.od_prototype;
  mockWs.start(agents, { pipelineType: "od_prototype", runId: "run-e2e-1" });
  await seedBrief(mockWs, "build prototype mimicking apple website just for reference");
  mockWs.plannerStart();
  mockWs.plannerComplete("Build an Apple-style reference prototype", "CLARIFY_REQUIRED");
  // Questions surface and the lane PAUSES in the clarify state — do NOT submit.
  mockWs.questionnaireReady(CLARIFY_Q);
  await page.getByTestId("chat-clarify-actions").waitFor({ state: "visible", timeout: 10_000 }).catch(() => {});
  await page.waitForTimeout(700);
  await shot(page, "full", "clarifyawaiting");
  // Steps surface (inline clarify-in-Steps — dead behind the pre-fix takeover at W0).
  await stepsTab(page).click({ timeout: 6000 }).catch(() => {});
  await page.waitForTimeout(900);
  await shot(page, "steps", "clarifyawaiting");
  await page.screenshot({ path: `${OUT}/leftlane__clarifyawaiting.png`, clip: { x: 0, y: 64, width: 360, height: 836 } });
});

test("CAPTURE paused — gate-awaiting", async ({ dashboard, mockWs, page }) => {
  test.setTimeout(120_000);
  await dashboard.goto();
  await launch(page, mockWs, "build prototype mimicking apple website just for reference");
  const agents = AGENTS.od_prototype;
  mockWs.start(agents, { pipelineType: "od_prototype", runId: "run-e2e-1" });
  await seedBrief(mockWs, "build prototype mimicking apple website just for reference");
  mockWs.plannerStart();
  mockWs.plannerComplete("Build an Apple-style reference prototype", "PROCEED");
  // The spec agent produces output and a review gate opens — the lane PAUSES in
  // the gate state (do NOT approve — capture the Awaiting-you approval card + gate UI).
  mockWs.agentStart("prototype-specify");
  mockWs.agentChunk("prototype-specify", "# Apple Reference — Specification\n\nSix pages, one design system.");
  mockWs.reviewGateReady({ gateKey: "spec", agentId: "prototype-specify", agentName: "Spec Writer", output: "Specification ready for your approval." });
  await page.getByTestId("chat-gate-actions").waitFor({ state: "visible", timeout: 10_000 }).catch(() => {});
  await page.waitForTimeout(700);
  await shot(page, "full", "gateawaiting");
  // Steps surface (inline gate-in-Steps — dead behind the pre-fix takeover at W0).
  await stepsTab(page).click({ timeout: 6000 }).catch(() => {});
  await page.waitForTimeout(900);
  await shot(page, "steps", "gateawaiting");
  await page.screenshot({ path: `${OUT}/leftlane__gateawaiting.png`, clip: { x: 0, y: 64, width: 360, height: 836 } });
});

test("CAPTURE failed run", async ({ dashboard, mockWs, mockApi, page }) => {
  test.setTimeout(120_000);
  // Seed the failed (blocked / denied / secrets-hit) audit set so the Audit tab
  // renders the red 'governance stopped this run' variant (W6 states).
  mockApi.setAuditVariant("failed");
  await dashboard.goto();
  await launch(page, mockWs, "Build a full inventory app with a seed script that writes credentials to .env");
  const agents = AGENTS.od_prototype;
  mockWs.start(agents, { pipelineType: "od_prototype", runId: "run-e2e-1" });
  await seedBrief(mockWs, "Build a full inventory app with a seed script that writes credentials to .env");
  // An assistant explanation line precedes the failure card (like the mock).
  mockWs.chatReply({ cardKind: "pipeline", text: "The run stopped at the security gate — a step tried to write secrets to disk and run code the workspace policy doesn't allow. Nothing was written outside the sandbox." });
  // Seed the two planning agents' output so the failed Files tab shows the real
  // (reduced) planning artifacts — the mock's "only planning artifacts" list is
  // LIVE agent outputs here (ND-D), not a fabricated file list.
  mockWs.agentStart("prototype-specify");
  mockWs.agentChunk("prototype-specify", "# Apple Reference — Specification\n\nSix pages, one shared design system, a single type scale and a 12-column grid.");
  mockWs.agentComplete("prototype-specify", { totalTokens: 30100 });
  mockWs.agentStart("prototype-plan");
  mockWs.agentChunk("prototype-plan", "# Build tasks\n1. Scaffold shared layout, nav & footer\n2. Home / landing page…");
  mockWs.agentComplete("prototype-plan", { totalTokens: 42200 });
  mockWs.agentStart("prototype-build"); mockWs.agentError("prototype-build", "The run stopped at the security gate. A step tried to write secrets to disk.");
  // Only the build agent hard-fails; the downstream Validation Agent never runs
  // (stays idle → renders as a "Not run" row + drives the "Pipeline halted — N
  // agents did not run" banner, mirroring the mock's failed Steps).
  mockWs.failed({ agentsFailed: ["prototype-build"], error: "Blocked by the security gate", totalDuration: 401 });
  await page.waitForTimeout(1400);
  await shot(page, "full", "failed");
  // Phase 39 run header (failed) — the red 'Run failed' badge + 'vN · partial'
  // chip (no Share / Download).
  await headerShot(page, "failed");
  await page.getByRole("tab", { name: /Steps/i }).first().click({ timeout: 6000 }).catch(() => {});
  await page.waitForTimeout(900); await shot(page, "steps", "failed");
  // Files tab (failed): the amber "Build incomplete" banner + only the live
  // planning-artifact files (reduced live outputs, ND-D — no fabricated rows).
  await page.getByRole("tab", { name: /Files/i }).first().click({ timeout: 6000 }).catch(() => {});
  await page.waitForTimeout(900); await shot(page, "files", "failed");
  // Audit tab (failed): the red 'governance stopped this run' banner + the
  // blocked/denied/secrets-hit stats over the failed audit set.
  await page.getByRole("tab", { name: /Audit/i }).first().click({ timeout: 6000 }).catch(() => {});
  await page.waitForTimeout(1200); await shot(page, "audit", "failed");
  await page.screenshot({ path: `${OUT}/leftlane__failed.png`, clip: { x: 0, y: 64, width: 360, height: 836 } });
});
