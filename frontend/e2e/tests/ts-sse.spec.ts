/**
 * TS-SSE — the mocked SSE/REST run harness, driven through the MOUNTED app.
 *
 * SSE is the sole run transport (44-06 hard cutoff). This spec drives the REAL
 * dashboard through the re-pointed page-object + `mockSse` harness: a launch
 * (`POST /api/runs`) attaches the run's SSE stream, the pipeline renders from the
 * SSE `pipeline_start`/`agent_*`/`pipeline_complete` emit, and the up-channel
 * commands (gate → `POST /{id}/gate`, cancel → `POST /{id}/cancel`) are asserted
 * against the recorded REST commands — NOT a synthetic `fetch` consumer.
 *
 * The transport-level resilience contract (attach → replay-from-cursor → drop →
 * reattach, native `Last-Event-ID` resume, multi-tab one-seq-space) lives in
 * ts-sse-resilience.spec.ts; revisions over `POST /{id}/revisions` live in
 * ts-u.revisions.spec.ts. Fully offline: no backend, no Bedrock.
 */
import { test, expect } from "../fixtures/test";
import { AGENTS } from "../fixtures/scenarios";

test.describe("TS-SSE — mounted-app SSE/REST run harness", () => {
  test("TS-SSE-01 a launch attaches the SSE stream and the pipeline renders from the emit", async ({
    dashboard,
    mockSse,
  }) => {
    const agents = AGENTS.user_stories;
    await dashboard.goto();
    // Launch over REST — the page-object waits for the recorded POST /api/runs.
    await dashboard.runWith({ workflow: "Generate product requirements", idea: "Generate epics for a refunds workflow" });

    // The launch command was recorded on the REST up-channel.
    const launch = await mockSse.waitForCommand("run_pipeline");
    expect(launch.type).toBe("run_pipeline");

    // Drive the pipeline over the SSE down-channel; the app renders from the emit.
    mockSse.start(agents, { pipelineType: "user_stories" });
    mockSse.agentStart(agents[0].id);
    await expect(dashboard.runningBadge().first()).toBeVisible();
    await expect(dashboard.stopButton()).toBeVisible();

    // Finish the run → the settled Done status token appears.
    for (const a of agents) {
      mockSse.agentStart(a.id);
      mockSse.agentComplete(a.id);
    }
    mockSse.complete({ pipelineType: "user_stories", finalOutput: "# Product Backlog\n" });
    await expect(dashboard.doneBadge()).toBeVisible();
  });

  test("TS-SSE-02 a review gate approve posts the gate command over REST (POST /{id}/gate)", async ({
    dashboard,
    mockSse,
  }) => {
    const agents = AGENTS.user_stories;
    await dashboard.goto();
    await dashboard.runWith({ workflow: "Generate product requirements", idea: "Refunds backlog" });

    mockSse.start(agents, { pipelineType: "user_stories" });
    mockSse.agentStart(agents[0].id);

    // Arm a review gate over SSE; the gate quick-actions surface in the Steps spine.
    mockSse.reviewGateReady({
      gateKey: "spec-gate",
      agentId: agents[1].id,
      agentName: agents[1].name,
      output: "Draft spec ready for review.",
    });
    await dashboard.thinkingTab().click();
    const gate = dashboard.page.getByTestId("chat-gate-actions");
    await expect(gate).toBeVisible();

    // Approve → POST /api/runs/{id}/gate, recorded as an approve_review command.
    await dashboard.page.getByTestId("chat-gate-approve").click();
    const approval = await mockSse.waitForCommand(
      (c) => c.type === "approve_review" && c.approved === true,
    );
    expect(String(approval.gate_key)).toBe("spec-gate");
  });

  test("TS-SSE-03 Stop posts the cancel command over REST (POST /{id}/cancel)", async ({
    dashboard,
    mockSse,
  }) => {
    const agents = AGENTS.user_stories;
    await dashboard.goto();
    await dashboard.runWith({ workflow: "Generate product requirements", idea: "Refunds backlog" });

    mockSse.start(agents, { pipelineType: "user_stories" });
    mockSse.agentStart(agents[0].id);
    await expect(dashboard.runningBadge().first()).toBeVisible();

    await dashboard.stopButton().click();
    const cancel = await mockSse.waitForCommand("cancel_pipeline");
    expect(cancel.type).toBe("cancel_pipeline");

    // The inbound teardown settles the run to the "Cancelled by you" terminal card.
    mockSse.cancelled({ duration: 8 });
    await expect(dashboard.page.getByText("Cancelled by you")).toBeVisible();
    await expect(dashboard.runningBadge()).toHaveCount(0);
  });
});
