/**
 * TS-P — Generic deliverable dispatch + iframe sandbox matrix (SECURITY-CRITICAL).
 *
 * The highest-value security assertions in the suite, proven IN A REAL BROWSER
 * (the locked component tests — PreviewPanel.genericDeliverable.test.tsx,
 * MarkdownPreview.security.test.tsx — assert the same invariants under jsdom).
 *
 * The crux is the EXACT `sandbox` attribute on each render channel:
 *   • generic text/html (custom pipeline) → "allow-scripts"  (NO same-origin) — T-18-05
 *   • non-od PPT deck                     → "allow-scripts"  (NO same-origin)
 *   • od_ppt deck                         → "allow-scripts allow-same-origin"
 *   • prototype                           → "allow-scripts allow-same-origin"
 *   • markdown                            → NO iframe at all (escaped via react-markdown)
 *   • unknown mimetype                    → NO iframe — a safe download affordance
 *
 * Dispatch is on the DECLARED mimetype / pipeline_type structurally, never a
 * workflow name (SC-001). A pipeline_type that is NOT user_stories / ppt /
 * prototype / app_builder (here: "custom") feeds the generic mimetype channel.
 *
 * Setup pattern: run a real pipeline (user_stories seeds agents so Run enables),
 * drive the agents (keeps pipelineState.isRunning true long enough for
 * DashboardLayout to sync workflowType from the declared pipeline_type), then
 * `mockWs.complete({...})` with the pipeline_type / mimetype under test.
 */
import { test, expect } from "../fixtures/test";
import { AGENTS, runAgent, SAMPLE_HTML, SAMPLE_DECK } from "../fixtures/scenarios";

// A small, valid HTML document for the prototype channel (PrototypePreview
// requires <!DOCTYPE html|<html to build its blob-url iframe).
const PROTOTYPE_HTML = `<!DOCTYPE html><html><head><title>Proto</title></head><body><h1>Prototype</h1><p>hi</p></body></html>`;

// Custom HTML carrying a parent-reaching XSS attempt — the sandbox (no
// allow-same-origin) must contain it so it cannot touch the parent window.
const XSS_HTML = `<!DOCTYPE html><html><head><title>Evil</title></head><body><h1>Evil</h1><script>try{parent.__xss=1;window.parent.__xss=1;top.__xss=1;}catch(e){}</script></body></html>`;

test.describe("TS-P — generic deliverable dispatch + iframe sandbox matrix", () => {
  test.beforeEach(async ({ dashboard }) => {
    await dashboard.goto();
    // user_stories seeds default agents → Run enables once an idea is typed.
    await dashboard.runWith({ workflow: "Generate product requirements", idea: "Custom deliverable run" });
  });

  // ── Drive a real run, then complete it with the given deliverable. The agents
  //    are driven so pipelineState.isRunning is true while DashboardLayout syncs
  //    workflowType from the declared pipeline_type (its sync effect is gated on
  //    isRunning); completing afterwards routes finalOutput by pipeline_type.
  async function runThenComplete(
    mockWs: import("../fixtures/mockWs").MockWs,
    pipelineType: string,
    complete: { finalOutput: string; deliverableMimetype?: string; deliverableFilename?: string },
  ) {
    const agents = AGENTS.user_stories;
    mockWs.start(agents, { pipelineType });
    for (const a of agents) await runAgent(mockWs, a.id);
    mockWs.complete({ pipelineType, ...complete });
  }

  test("TS-P-01 custom HTML → sandboxed iframe (allow-scripts, NO same-origin)", async ({ dashboard, mockWs }) => {
    await runThenComplete(mockWs, "custom", {
      finalOutput: SAMPLE_HTML,
      deliverableMimetype: "text/html",
    });

    const iframe = dashboard.genericIframe();
    await expect(iframe).toBeVisible();
    const sandbox = await iframe.getAttribute("sandbox");
    // T-18-05 (BLOCKING): exactly allow-scripts, never same-origin.
    expect(sandbox).toBe("allow-scripts");
    expect(sandbox || "").not.toContain("allow-same-origin");
    // The HTML is framed via srcDoc (not escaped through markdown).
    expect(await iframe.getAttribute("srcdoc")).toContain("Habit Tracker");
  });

  test("TS-P-02 markdown deliverable → escaped via MarkdownPreview (NO iframe, no script exec)", async ({ dashboard, page, mockWs }) => {
    await runThenComplete(mockWs, "custom", {
      finalOutput: "# Hi\n<script>window.__pwned=1</script>\n<img src=x onerror=alert(1)>",
      deliverableMimetype: "text/markdown",
    });

    // Renders through MarkdownPreview — its "Output" header is the marker — and
    // NOT an iframe.
    await expect(page.getByText("Output", { exact: true }).first()).toBeVisible();
    await expect(dashboard.genericIframe()).toHaveCount(0);

    // The raw <script> was escaped to literal text, never parsed into the DOM:
    // window.__pwned must be undefined and the literal "<script>" must appear.
    expect(await page.evaluate(() => (window as unknown as { __pwned?: number }).__pwned)).toBeUndefined();
    await expect(page.getByText("<script>window.__pwned=1</script>", { exact: false })).toBeVisible();
    // No live <script> from the markdown content exists in the document.
    expect(
      await page.evaluate(() =>
        Array.from(document.querySelectorAll("script")).some((s) => s.textContent?.includes("__pwned")),
      ),
    ).toBe(false);
  });

  test("TS-P-04 unknown mimetype → safe download card, no iframe", async ({ dashboard, page, mockWs }) => {
    await runThenComplete(mockWs, "custom", {
      finalOutput: "binarydata",
      deliverableMimetype: "application/octet-stream",
      deliverableFilename: "data.bin",
    });

    // A safe download affordance — never inline/iframe an unknown type (T-18-06).
    await expect(page.getByText("Deliverable ready")).toBeVisible();
    await expect(page.getByRole("button", { name: /download/i })).toBeVisible();
    await expect(page.getByRole("button", { name: "Download data.bin" })).toBeVisible();
    await expect(dashboard.genericIframe()).toHaveCount(0);
  });

  test("TS-P-05a od_ppt deck → iframe sandbox = allow-scripts allow-same-origin", async ({ dashboard, mockWs }) => {
    await runThenComplete(mockWs, "od_ppt", { finalOutput: SAMPLE_DECK });

    const deck = dashboard.deckIframe();
    await expect(deck).toBeVisible();
    const sandbox = await deck.getAttribute("sandbox");
    // od_ppt is a trusted Flowin-authored deck → same-origin is granted.
    expect(sandbox).toBe("allow-scripts allow-same-origin");
  });

  test("TS-P-05b plain ppt deck → iframe sandbox = allow-scripts (NO same-origin)", async ({ dashboard, mockWs }) => {
    await runThenComplete(mockWs, "ppt", { finalOutput: SAMPLE_DECK });

    const deck = dashboard.deckIframe();
    await expect(deck).toBeVisible();
    const sandbox = await deck.getAttribute("sandbox");
    // Plain "ppt" (non-od) does NOT get same-origin.
    expect(sandbox).toBe("allow-scripts");
    expect(sandbox || "").not.toContain("allow-same-origin");
  });

  test("TS-P-05c prototype → iframe sandbox = allow-scripts allow-same-origin", async ({ dashboard, mockWs }) => {
    await runThenComplete(mockWs, "od_prototype", { finalOutput: PROTOTYPE_HTML });

    const proto = dashboard.prototypeIframe();
    await expect(proto).toBeVisible();
    const sandbox = await proto.getAttribute("sandbox");
    expect(sandbox).toBe("allow-scripts allow-same-origin");
  });

  test("TS-P-06 XSS containment — custom HTML script cannot reach the parent window", async ({ dashboard, page, mockWs }) => {
    await runThenComplete(mockWs, "custom", {
      finalOutput: XSS_HTML,
      deliverableMimetype: "text/html",
    });

    const iframe = dashboard.genericIframe();
    await expect(iframe).toBeVisible();
    // Re-assert the sandbox is the containment mitigation under test.
    expect(await iframe.getAttribute("sandbox")).toBe("allow-scripts");

    // Give any in-iframe script a chance to run, then prove it could NOT write to
    // the parent: with no allow-same-origin the iframe is a unique opaque origin,
    // so parent/top access is a cross-origin SecurityError (swallowed by the
    // try/catch in the payload) and window.__xss stays undefined.
    await expect
      .poll(
        async () => page.evaluate(() => (window as unknown as { __xss?: number }).__xss),
        { timeout: 3000 },
      )
      .toBeUndefined();
  });
});
