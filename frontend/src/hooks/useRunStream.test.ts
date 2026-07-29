/**
 * useRunStream — SSE frame-parser transport unit tests (BUG-014-B).
 *
 * These drive the hook through its REAL transport path: a mocked `fetch` whose
 * response body is a `ReadableStream` yielding the exact bytes the backend
 * (`sse-starlette==3.0.2`) puts on the wire — `id: N\r\ndata: {"type","data"}\r\n\r\n`.
 *
 * The parser must:
 *   (a) split CRLF frames and unwrap the `{type,data}` envelope so a single live
 *       frame dispatches `{type, data}` (RED today: the CRLF split never matches,
 *       so only the on-close flush fires ONCE with type==="" and the un-unwrapped
 *       envelope as data);
 *   (b) dispatch once per frame on a multi-frame chunk (RED today: 1 call, not 2);
 *   (c) stay TOLERANT of the legacy `\n\n` + `event:` line shape (GREEN both ways).
 *
 * SC-001: the fixtures key on frame structure + pipeline event-type strings — no
 * workflow-name literal.
 */
import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useRunStream } from "./useRunStream";

// Let connect() pass its token guard; env stays real (ENV.API_URL only shapes the URL).
vi.mock("@/lib/api", () => ({
  getToken: () => "t.t.t",
  setToken: vi.fn(),
  clearToken: vi.fn(),
}));

/** A one-shot ReadableStream that enqueues `text` as UTF-8 bytes then closes. */
function wireStream(text: string): ReadableStream<Uint8Array> {
  return new ReadableStream<Uint8Array>({
    start(c) {
      c.enqueue(new TextEncoder().encode(text));
      c.close();
    },
  });
}

/** Point global.fetch at a 200 response whose body streams `wire`. */
function serveWire(wire: string) {
  global.fetch = vi.fn(
    async () =>
      ({ status: 200, ok: true, body: wireStream(wire) }) as unknown as Response,
  );
}

const realFetch = global.fetch;

beforeEach(() => {
  vi.clearAllMocks();
});
afterEach(() => {
  global.fetch = realFetch;
});

/** The REAL backend single frame: CRLF-separated, `{type,data}` envelope, no `event:` line. */
const QUESTIONNAIRE_FRAME =
  'id: 1\r\ndata: {"type":"questionnaire_ready","data":{"pipeline_run_id":"r","questions":[{"question_id":"q1","question_text":"Q?"}]}}\r\n\r\n';

describe("useRunStream — SSE frame parser (BUG-014-B)", () => {
  it("(a) parses a single real-wire frame and unwraps the {type,data} envelope", async () => {
    serveWire(QUESTIONNAIRE_FRAME);
    const onMessage = vi.fn();

    renderHook(() =>
      useRunStream({ runId: "r", token: "t.t.t", onMessage, enabled: true }),
    );

    await waitFor(() =>
      // `runId` is the transport's source-run stamp — the hook is instantiated
      // per run, so every dispatched envelope carries it. Downstream run-scoping
      // (the foreign-run bleed guard in dashboard/page.tsx) depends on it.
      expect(onMessage).toHaveBeenCalledWith({
        type: "questionnaire_ready",
        data: {
          pipeline_run_id: "r",
          questions: [{ question_id: "q1", question_text: "Q?" }],
        },
        runId: "r",
      }),
    );
  });

  it("(b) dispatches once per frame on a multi-frame chunk and advances the cursor", async () => {
    const frame1 =
      'id: 1\r\ndata: {"type":"questionnaire_ready","data":{"pipeline_run_id":"r","seq":1}}\r\n\r\n';
    const frame2 =
      'id: 2\r\ndata: {"type":"review_gate_ready","data":{"gate_key":"g1","seq":2}}\r\n\r\n';
    serveWire(frame1 + frame2);
    const onMessage = vi.fn();

    const { result } = renderHook(() =>
      useRunStream({ runId: "r", token: "t.t.t", onMessage, enabled: true }),
    );

    await waitFor(() => expect(onMessage).toHaveBeenCalledTimes(2));

    expect(onMessage.mock.calls[0][0]).toMatchObject({ type: "questionnaire_ready" });
    expect(onMessage.mock.calls[1][0]).toMatchObject({ type: "review_gate_ready" });

    // The seq cursor still advances now that the type lives inside the envelope.
    await waitFor(() => expect(result.current.cursor).toBe(2));
  });

  it("(c) stays tolerant of the legacy \\n\\n + event: line shape (green both ways)", async () => {
    serveWire(
      'id: 1\nevent: agent_start\ndata: {"agent_id":"a1","seq":1,"event_id":"e1"}\n\n',
    );
    const onMessage = vi.fn();

    renderHook(() =>
      useRunStream({ runId: "r", token: "t.t.t", onMessage, enabled: true }),
    );

    await waitFor(() =>
      expect(onMessage).toHaveBeenCalledWith({
        type: "agent_start",
        data: { agent_id: "a1", seq: 1, event_id: "e1" },
        // Source-run stamp (see the note above) — additive on every envelope.
        runId: "r",
      }),
    );
  });
});

// ─────────────────────────────────────────────────────────────────
// BUG-015 — a completed, still-viewed run reconnects forever. The backend
// closes a TERMINAL run's stream after replay (`stream_attached {live:false}`
// then close, no `event: done`). The hook must NOT reconnect after a non-live
// attach closes (it would re-replay ~14k events in a loop), while a GENUINE
// live-stream drop MUST still reconnect. SC-001: fixtures key on the
// `stream_attached`/`live` frame + run-id strings only — no workflow-name literal.
// ─────────────────────────────────────────────────────────────────
describe("useRunStream — non-live close does not reconnect (BUG-015)", () => {
  const NON_LIVE_ATTACH =
    'id: 5\r\ndata: {"type":"stream_attached","data":{"pipeline_run_id":"r","live":false,"replayed_through_seq":5}}\r\n\r\n';
  const LIVE_ATTACH =
    'id: 5\r\ndata: {"type":"stream_attached","data":{"pipeline_run_id":"r","live":true,"replayed_through_seq":5}}\r\n\r\n';

  it("A1 (PRIMARY): a non-live attach that closes settles `disconnected` — no reconnect", async () => {
    serveWire(NON_LIVE_ATTACH);

    const { result } = renderHook(() =>
      useRunStream({ runId: "r", token: "t.t.t", onMessage: vi.fn(), enabled: true }),
    );

    // FAIL-BEFORE: the close branch runs scheduleReconnect() → phase "reconnecting"
    // + a "Reconnecting…" banner, so phase never reaches "disconnected" (RED).
    await waitFor(() => expect(result.current.phase).toBe("disconnected"));
    expect(result.current.lastError ?? "").not.toMatch(/Reconnecting/i);
  });

  it("A2 (CONTROL): a live attach that drops STILL reconnects", async () => {
    serveWire(LIVE_ATTACH);

    const { result } = renderHook(() =>
      useRunStream({ runId: "r", token: "t.t.t", onMessage: vi.fn(), enabled: true }),
    );

    // A genuine live drop keeps reconnecting (liveness is judged per-connection —
    // the ref resets at the top of every connect()). scheduleReconnect sets
    // "reconnecting" synchronously; test cleanup aborts the pending 1s reconnect.
    await waitFor(() => expect(result.current.phase).toBe("reconnecting"));
  });
});
