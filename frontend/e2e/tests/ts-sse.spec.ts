/**
 * TS-SSE — mock-SSE transport driver smoke (Phase-29 CHAT-07 harness).
 *
 * Exercises the ADDITIVE `mockSse` transport driver end-to-end through the real
 * browser network layer (Playwright `page.route`): attach → replay-from-cursor
 * → drop → reattach, asserting a consumer dedups by `event_id` and resumes its
 * cursor from `seq`.
 *
 * WHY a modeled consumer (not the live app): per LOCK-B this phase does NOT
 * touch `useWebSocket.ts`, so the app has no SSE consumer yet — the FE transport
 * adapter that reads this stream lands in 29-07. This smoke therefore drives the
 * driver through a minimal in-page `fetch` consumer that mimics the exact
 * dedup-by-`data.event_id` + resume-by-`data.seq` contract the WS handler uses
 * today (mockWs.ts header) and the 29-07 adapter will use. It proves the driver
 * routes the SSE endpoint, frames `id:{seq}`, replays from `Last-Event-ID`, and
 * shares ONE monotonic seq/event_id space with MockWs.
 *
 * Fully offline: no backend, no Bedrock — the mocked project's `page.route`
 * interception serves the event-stream body.
 */
import { test, expect } from "../fixtures/test";
import { installMockSse } from "../fixtures/mockSse";

interface WireEvent {
  seq: number; // the SSE `id:` line
  type: string; // the SSE `event:` line
  data: { event_id: string; seq: number; [k: string]: unknown };
}

/**
 * A minimal in-page SSE consumer: GET the stream (optionally carrying
 * `Last-Event-ID`), read the buffered `text/event-stream` body, and parse it
 * into wire events. A same-origin relative path avoids any CORS concern; the
 * driver's route regex matches regardless of host.
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
      for (const block of text.split("\n\n")) {
        if (!block.trim()) continue;
        let id: string | undefined;
        let type: string | undefined;
        let dataLine: string | undefined;
        for (const line of block.split("\n")) {
          if (line.startsWith("id:")) id = line.slice(3).trim();
          else if (line.startsWith("event:")) type = line.slice(6).trim();
          else if (line.startsWith("data:")) dataLine = line.slice(5).trim();
        }
        const data = dataLine ? JSON.parse(dataLine) : {};
        events.push({ seq: Number(id), type: type ?? "", data });
      }
      return events;
    },
    { path, headers },
  );
}

test.describe("TS-SSE — mock-SSE transport driver", () => {
  test("TS-SSE-01 attach → replay-from-cursor → drop → reattach dedups by event_id and resumes from seq", async ({
    dashboard,
    mockWs,
    page,
  }) => {
    await dashboard.goto();

    // Install the SSE transport, sharing the MockWs seq/event_id source.
    const sse = await installMockSse(page, mockWs);
    const runId = mockWs.currentRunId;
    const streamPath = `/api/runs/${runId}/events/stream`;

    // Seed the durable tail on the SHARED sequence.
    sse.streamAttached({ live: true }); //                 seq 1
    sse.chatMessage({ messageId: "m1", text: "hello" }); // seq 2
    sse.chatReply({ cardKind: "pipeline", text: "started" }); // seq 3

    // ── attach (no Last-Event-ID) → the full tail, in seq order ──────────────
    const first = await fetchSse(page, streamPath);
    expect(first.map((e) => e.seq)).toEqual([1, 2, 3]);
    expect(first.map((e) => e.type)).toEqual(["stream_attached", "chat_message", "chat_reply"]);
    expect(sse.connectionCount).toBe(1);
    expect(sse.lastAttachCursor).toBeNull();

    // A consumer dedups by data.event_id and tracks its resume cursor = max seq.
    const seen = new Set(first.map((e) => e.data.event_id));
    let cursor = Math.max(...first.map((e) => e.seq));
    expect(cursor).toBe(3);
    expect(seen.size).toBe(3); // event_ids are unique

    // ── a new frame arrives on the live tail after the consumer's cursor ──────
    sse.chatReply({ cardKind: "deliverable", text: "done" }); // seq 4

    // ── drop → reattach carrying Last-Event-ID = cursor → replay-from-cursor ──
    sse.drop();
    expect(sse.isDropped).toBe(true);
    const replay = await fetchSse(page, streamPath, { "Last-Event-ID": String(cursor) });

    // The reattach re-established the transport and replayed ONLY seq > cursor.
    expect(sse.connectionCount).toBe(2);
    expect(sse.isDropped).toBe(false);
    expect(sse.lastAttachCursor).toBe(3);
    expect(replay.map((e) => e.seq)).toEqual([4]);

    // Dedup: none of the replayed frames were already seen by the consumer.
    for (const e of replay) expect(seen.has(e.data.event_id)).toBe(false);

    // Resume: the cursor advances monotonically past the replayed tail.
    for (const e of replay) {
      seen.add(e.data.event_id);
      cursor = Math.max(cursor, e.seq);
    }
    expect(cursor).toBe(4);

    // ── one monotonic seq/event_id space shared with MockWs ──────────────────
    // mockSse advanced the SAME MockWs seq counter 4 times — no second seq space.
    expect(mockWs.currentSeq).toBe(4);
    // event_ids are globally unique across every emitted frame (dedup integrity).
    const allEventIds = sse.frames.map((f) => f.data.event_id);
    expect(new Set(allEventIds).size).toBe(allEventIds.length);
  });

  test("TS-SSE-02 an empty tail replayed past the head yields no frames (idempotent reattach)", async ({
    dashboard,
    mockWs,
    page,
  }) => {
    await dashboard.goto();
    const sse = await installMockSse(page, mockWs);
    const streamPath = `/api/runs/${mockWs.currentRunId}/events/stream`;

    sse.streamAttached({ live: true }); // seq 1
    const full = await fetchSse(page, streamPath);
    expect(full.map((e) => e.seq)).toEqual([1]);

    // Reattaching past the head (Last-Event-ID = 1) replays nothing — a resumed
    // consumer that already saw seq 1 receives an empty tail (no re-delivery).
    const empty = await fetchSse(page, streamPath, { "Last-Event-ID": "1" });
    expect(empty).toEqual([]);
    expect(sse.connectionCount).toBe(2);
  });
});
