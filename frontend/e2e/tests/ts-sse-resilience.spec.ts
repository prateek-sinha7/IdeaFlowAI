/**
 * TS-SSE-RESILIENCE — the FE SSE transport resilience contract (Phase 29,
 * CHAT-07, D-14). Drives the ADDITIVE 29-06 `mockSse` transport driver through
 * the real browser network layer (Playwright `page.route`) and asserts the exact
 * resilience behaviors `useRunStream` + `RunConnectionProvider` implement:
 *
 *   01 page reload → native `Last-Event-ID` resume resumes the transcript
 *   02 route-change survives (app-level ownership keeps the resume cursor)
 *   03 auto-reconnect after a transport drop replays only past-cursor frames
 *   04 multi-tab — two consumers ride ONE monotonic seq/event_id space
 *
 * WHY a modeled fetch consumer (not the mounted app): per LOCK-B this phase is
 * additive and does NOT mount the provider in the app root (that layout wiring
 * is a deferred, supervised follow-up). The consumer here mirrors `useRunStream`
 * EXACTLY — a `fetch`-stream attach carrying `Last-Event-ID: <max-seen seq>`,
 * dedup by `data.event_id`, resume by `data.seq` — which is the very mechanism
 * the hook uses (it uses fetch+ReadableStream, not `EventSource`, so it can send
 * the Authorization + Last-Event-ID headers). The persisted cursor is modeled in
 * `sessionStorage` (D-14c), exactly as the provider persists it.
 *
 * Fully offline: no backend, no Bedrock — `page.route` serves the event-stream
 * body. Uses reskin-resilient behavior (transport-level), not app-UI text
 * locators, so it is independent of the pre-existing feat/ui-2 home redesign
 * (DEF-29-06-1).
 */
import { test, expect } from "../fixtures/test";
import { SSE_URL_RE } from "../fixtures/mockSse";
import { AGENTS } from "../fixtures/scenarios";

interface WireEvent {
  seq: number;
  type: string;
  data: { event_id: string; seq: number; [k: string]: unknown };
}

/**
 * A minimal in-page SSE consumer mirroring `useRunStream`: GET the stream
 * (optionally carrying `Last-Event-ID`), read the buffered `text/event-stream`
 * body, and parse it into wire events.
 */
async function fetchSse(
  page: import("@playwright/test").Page,
  path: string,
  headers: Record<string, string> = {},
): Promise<WireEvent[]> {
  return page.evaluate(
    async ({ path, headers }) => {
      const res = await fetch(path, { headers });
      const text = await res.text();
      const events: WireEvent[] = [];
      // Mirror useRunStream: normalize CRLF -> LF so `\r\n\r\n` frames split, then
      // tolerantly unwrap the real `{type,data}` envelope (BUG-014-B).
      for (const block of text.replace(/\r\n/g, "\n").split("\n\n")) {
        if (!block.trim()) continue;
        let id: string | undefined;
        let type: string | undefined;
        let dataLine: string | undefined;
        for (const line of block.split("\n")) {
          if (line.startsWith("id:")) id = line.slice(3).trim();
          else if (line.startsWith("event:")) type = line.slice(6).trim();
          else if (line.startsWith("data:")) dataLine = line.slice(5).trim();
        }
        const parsed = (dataLine ? JSON.parse(dataLine) : {}) as Record<string, unknown>;
        let evType = type ?? "";
        let data = parsed;
        if (typeof parsed.type === "string") {
          evType = parsed.type;
          data = (parsed.data as Record<string, unknown>) ?? {};
        }
        events.push({ seq: Number(id), type: evType, data: data as WireEvent["data"] });
      }
      return events;
    },
    { path, headers },
  );
}

/** Persist the resume cursor the way RunConnectionProvider does (D-14c). */
async function persistCursor(
  page: import("@playwright/test").Page,
  runId: string,
  seq: number,
): Promise<void> {
  await page.evaluate(
    ({ runId, seq }) => sessionStorage.setItem(`run_cursor:${runId}`, String(seq)),
    { runId, seq },
  );
}
async function readCursor(
  page: import("@playwright/test").Page,
  runId: string,
): Promise<number | null> {
  return page.evaluate((runId) => {
    const v = sessionStorage.getItem(`run_cursor:${runId}`);
    return v == null || v === "" ? null : Number(v);
  }, runId);
}

test.describe("TS-SSE-RESILIENCE — sse-resilience transport (D-14)", () => {
  test("TS-SSE-RESILIENCE-01 sse-resilience: page reload resumes the transcript via native Last-Event-ID", async ({
    dashboard,
    mockSse,
    page,
  }) => {
    mockSse.autoAttach = false; // drive the transport by hand (no competing app stream)
    await dashboard.goto();
    const sse = mockSse;
    const runId = mockSse.currentRunId;
    const streamPath = `/api/runs/${runId}/events/stream`;

    // Seed + attach: the durable transcript so far.
    sse.streamAttached({ live: true }); // seq 1
    sse.chatMessage({ messageId: "m1", text: "hello" }); // seq 2
    sse.chatReply({ cardKind: "pipeline", text: "started" }); // seq 3

    const first = await fetchSse(page, streamPath);
    expect(first.map((e) => e.seq)).toEqual([1, 2, 3]);
    const seen = new Set(first.map((e) => e.data.event_id));
    let cursor = Math.max(...first.map((e) => e.seq));
    await persistCursor(page, runId, cursor); // D-14c

    // More transcript arrives after the consumer's cursor, then the tab reloads.
    sse.chatReply({ cardKind: "deliverable", text: "done" }); // seq 4

    await page.reload();

    // Native resume: reattach carrying Last-Event-ID = the persisted cursor.
    const resumeFrom = await readCursor(page, runId);
    expect(resumeFrom).toBe(3);
    const resumed = await fetchSse(page, streamPath, {
      "Last-Event-ID": String(resumeFrom),
    });

    // Only the post-cursor tail replays; nothing already-seen is re-delivered.
    expect(resumed.map((e) => e.seq)).toEqual([4]);
    for (const e of resumed) expect(seen.has(e.data.event_id)).toBe(false);
    for (const e of resumed) {
      seen.add(e.data.event_id);
      cursor = Math.max(cursor, e.seq);
    }
    expect(cursor).toBe(4);
    expect(sse.lastAttachCursor).toBe(3);
  });

  test("TS-SSE-RESILIENCE-02 sse-resilience: route-change keeps the resume cursor (app-level ownership)", async ({
    dashboard,
    mockSse,
    page,
  }) => {
    mockSse.autoAttach = false; // drive the transport by hand (no competing app stream)
    await dashboard.goto();
    const sse = mockSse;
    const runId = mockSse.currentRunId;
    const streamPath = `/api/runs/${runId}/events/stream`;

    sse.streamAttached({ live: true }); // seq 1
    sse.chatReply({ cardKind: "clarify", text: "need info" }); // seq 2
    const first = await fetchSse(page, streamPath);
    expect(first.map((e) => e.seq)).toEqual([1, 2]);
    const cursor = Math.max(...first.map((e) => e.seq));
    await persistCursor(page, runId, cursor); // provider owns + persists (D-14a/c)

    // A client-side route change WITHIN the app (dashboard → wizard-ish route).
    // Because ownership is app-level, the cursor survives — a later reattach
    // resumes from it rather than doing a full replay from scratch.
    await page.evaluate(() => history.pushState({}, "", "/dashboard?view=input"));
    expect(await readCursor(page, runId)).toBe(2);

    sse.chatReply({ cardKind: "gate", text: "review" }); // seq 3
    const afterRoute = await fetchSse(page, streamPath, {
      "Last-Event-ID": String(await readCursor(page, runId)),
    });
    // Resume (not full replay): the attach honored the surviving cursor.
    expect(sse.lastAttachCursor).toBe(2);
    expect(afterRoute.map((e) => e.seq)).toEqual([3]);
  });

  test("TS-SSE-RESILIENCE-03 sse-resilience: auto-reconnect after a drop replays only past-cursor frames", async ({
    dashboard,
    mockSse,
    page,
  }) => {
    mockSse.autoAttach = false; // drive the transport by hand (no competing app stream)
    await dashboard.goto();
    const sse = mockSse;
    const runId = mockSse.currentRunId;
    const streamPath = `/api/runs/${runId}/events/stream`;

    sse.streamAttached({ live: true }); // seq 1
    sse.chatReply({ cardKind: "pipeline", text: "running" }); // seq 2
    const first = await fetchSse(page, streamPath);
    const seen = new Set(first.map((e) => e.data.event_id));
    let cursor = Math.max(...first.map((e) => e.seq));
    expect(cursor).toBe(2);
    expect(sse.connectionCount).toBe(1);

    // A frame lands on the live tail, then the transport drops.
    sse.chatReply({ cardKind: "deliverable", text: "done" }); // seq 3
    sse.drop();
    expect(sse.isDropped).toBe(true);

    // Auto-reconnect: the hook re-issues the fetch carrying Last-Event-ID.
    const replay = await fetchSse(page, streamPath, {
      "Last-Event-ID": String(cursor),
    });
    expect(sse.connectionCount).toBe(2);
    expect(sse.isDropped).toBe(false);
    expect(replay.map((e) => e.seq)).toEqual([3]);
    for (const e of replay) expect(seen.has(e.data.event_id)).toBe(false);
    for (const e of replay) {
      seen.add(e.data.event_id);
      cursor = Math.max(cursor, e.seq);
    }
    expect(cursor).toBe(3);
  });

  test("TS-SSE-RESILIENCE-04 sse-resilience: mock harness shares ONE monotonic seq/event_id space across tabs (harness contract — not a backend delivery guarantee)", async ({
    dashboard,
    mockSse,
    page,
  }) => {
    // D1 (KAN-139): this test asserts the MOCK HARNESS contract — a shared MockSse
    // instance serves both tabs from the same frames array, so they receive the same
    // seq/event_id space. This does NOT assert the real backend's delivery guarantee
    // (a real backend queue is consume-once, so two tabs competing for the SAME live
    // queue would produce A2 event-theft). The test title has been retitled to avoid
    // claiming a backend invariant that only the mock enforces.
    // TS-SSE-RESILIENCE-05 (a separate test requiring two real browser tabs against
    // the mounted app + real backend) would be the proper measurement point for the
    // backend delivery property, but is out of scope for offline mocked testing.
    mockSse.autoAttach = false; // drive the transport by hand (no competing app stream)
    await dashboard.goto();
    const runId = mockSse.currentRunId;
    const streamPath = `/api/runs/${runId}/events/stream`;

    // One shared driver (the fixture's MockSse), its SSE route projected onto BOTH
    // tabs (real separate pages in the same context) — one monotonic seq space.
    const sse = mockSse;
    const tab2 = await page.context().newPage();
    await tab2.route(SSE_URL_RE, (route) => sse.route(route));
    await tab2.goto("/login", { waitUntil: "domcontentloaded" });

    sse.streamAttached({ live: true }); // seq 1
    sse.chatMessage({ messageId: "m1", text: "hi" }); // seq 2
    sse.chatReply({ cardKind: "pipeline", text: "go" }); // seq 3

    // Both tabs attach to the same run and each receive the full, ordered tail.
    const [a, b] = await Promise.all([
      fetchSse(page, streamPath),
      fetchSse(tab2, streamPath),
    ]);
    expect(a.map((e) => e.seq)).toEqual([1, 2, 3]);
    expect(b.map((e) => e.seq)).toEqual([1, 2, 3]);
    expect(sse.connectionCount).toBe(2); // two independent tab attaches

    // One monotonic seq space shared with MockWs; event_ids globally unique so
    // each tab dedups deterministically.
    expect(mockSse.currentSeq).toBe(3);
    const eventIds = a.map((e) => e.data.event_id);
    expect(new Set(eventIds).size).toBe(eventIds.length);
    // The two tabs saw identical event_ids for identical seqs (one space).
    expect(a.map((e) => e.data.event_id)).toEqual(b.map((e) => e.data.event_id));

    await tab2.close();
  });

  /**
   * TS-SSE-RESILIENCE-06 — the MOUNTED app, not a modeled consumer.
   *
   * The narrator's "Delivered" milestone card is projected AFTER the
   * `pipeline_complete` it is derived from, and the server's live drain returns the
   * moment `pipeline_complete` is drained — so the card is never delivered live on
   * that connection. `useRunStream` does not treat `pipeline_complete` as a
   * non-live attach, so the close schedules a RECONNECT carrying
   * `Last-Event-ID = <complete seq>`, and the server REPLAYS the card row off the
   * durable tail. In parallel the completion backfill (page.tsx → getRunEvents)
   * reads the same row from the durable REST twin.
   *
   * Those two deliveries must key IDENTICALLY. They only do so if the replay
   * serves the row's `event_id`/`seq` COLUMNS (the REST twin always has) — a
   * narrator card embeds NO identity in its payload, so an anonymous replay is
   * re-keyed by `upsertNarratorMessage`'s `chat-reply:{message_id}` fallback and
   * the card renders TWICE.
   *
   * NOT the naive "emit card, drop, assert" shape: `useRunStream` advances its
   * cursor from every dispatched frame, so a card already processed live is never
   * replayed and no duplicate can exist.
   *
   * The reconnect also needs one precondition that is easy to miss. On
   * `pipeline_complete` the page calls `detachRun` (page.tsx), which — see
   * `RunConnectionProvider.detachRun` — clears ONLY the sticky focus. Membership in
   * `liveRunIds` is `union(autoIdsRef, focusedRunIdRef)`, so a run that is ALSO in
   * `autoIdsRef` keeps its connection mounted and DOES reconnect after the terminal
   * close. `autoIdsRef` is populated only by `refreshLiveRuns()`, which requires
   * BOTH an AUTO_STREAM_STATUSES status from `GET /api/runs` AND the run id in
   * `sessionStorage["tab_launched_run_ids"]`; it runs on boot (too early) and on
   * `online`/`visibilitychange` (the one that matters). So the run must be launched
   * through the REAL flow and a wake fired WHILE it is still running — which is
   * exactly what a mid-run network blip does on the live stack.
   */
  test("TS-SSE-RESILIENCE-06 a narrator milestone card replayed after the terminal close renders exactly ONCE", async ({
    dashboard,
    mockSse,
    page,
  }) => {
    const MARKER = "3WO-DELIVERED-MARKER";
    const agents = AGENTS.user_stories;

    // Model TODAY's PRE-FIX server: its durable replay yields payload_json RAW, so
    // a replayed app-layer row arrives with no identity. (Removed once the mock
    // mirrors the shipped run_stream.py projection.)
    mockSse.simulatePreFixReplay = true;

    // Mount the real app on a live run (the launch→watch flow) — autoAttach stays
    // true so RunConnectionProvider/useRunStream/useRunChat are the real consumers.
    await dashboard.goto();
    await dashboard.runWith({
      workflow: "Generate product requirements",
      idea: "Generate epics for a refunds workflow",
    });
    mockSse.start(agents, { pipelineType: "user_stories" });
    await expect(page.getByTestId("run-chat-lane")).toBeVisible();
    // The stream must be genuinely ATTACHED and caught up before the terminal, so
    // pipeline_complete is delivered LIVE (production ordering) rather than as part
    // of a late catch-up replay.
    await mockSse.ready();

    // Precondition (b): the REAL launch flow above registered this run as
    // tab-owned. Read it back rather than assuming — without it `refreshLiveRuns`
    // filters the run out and `autoIdsRef` stays empty.
    const tabOwned = await page.evaluate(() =>
      JSON.parse(sessionStorage.getItem("tab_launched_run_ids") ?? "[]"),
    );
    expect(tabOwned).toContain(mockSse.currentRunId);

    for (const a of agents) {
      mockSse.agentStart(a.id);
      mockSse.agentComplete(a.id);
    }
    await expect(dashboard.stepsAgentRow(agents[agents.length - 1].name)).toBeVisible();

    // A mid-run network blip (what DROP=1 does on the live stack): `online` fires
    // `refreshLiveRuns()` WHILE the run is still `running`, which is what puts it in
    // `autoIdsRef` — the membership path `detachRun` cannot clear. Proven by the
    // resulting GET /api/runs round-trip, not by the dispatch alone.
    const listFetchesBeforeWake = mockSse.runListFetchCount;
    await page.evaluate(() => window.dispatchEvent(new Event("online")));
    await expect
      .poll(() => mockSse.runListFetchCount, { timeout: 15_000 })
      .toBeGreaterThan(listFetchesBeforeWake);

    const attachesBeforeTerminal = mockSse.connectionCount;

    // The terminal frame ships ALONE (mockSse batches it separately), and the
    // narrator card is queued in the SAME tick — so it lands on the durable tail
    // strictly AFTER the terminal frame was selected for delivery, exactly as the
    // engine queues the card after the live drain has already returned.
    mockSse.complete({ pipelineType: "user_stories", finalOutput: "# Product Backlog\n" });
    mockSse.chatReply({ cardKind: "deliverable", text: MARKER });

    await expect(dashboard.doneBadge()).toBeVisible();

    // Both delivery paths must have run before the count is meaningful:
    //   (1) the post-terminal RECONNECT replayed the card off the durable tail,
    //   (2) the completion backfill read the same row from the REST twin.
    await expect
      .poll(() => mockSse.connectionCount, { timeout: 20_000 })
      .toBeGreaterThan(attachesBeforeTerminal);
    await expect.poll(() => mockSse.eventsFetchCount, { timeout: 20_000 }).toBeGreaterThan(0);

    const cards = page.getByTestId("chat-result-card").filter({ hasText: MARKER });
    await expect(cards.first()).toBeVisible();
    // A duplicate arrives on the OTHER path, so proving its absence needs a bounded
    // settle — a web-first retry would otherwise pass the instant the first copy
    // committed (mirrors how -03 sequences its own transport steps).
    await page.waitForTimeout(1500);
    await expect(cards).toHaveCount(1);
  });
});
