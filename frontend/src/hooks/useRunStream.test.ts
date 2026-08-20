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
import { STREAM_TERMINAL_TYPES } from "@/types";
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

/**
 * SSE-003: a MULTI-chunk body. `serveWire` above enqueues the whole wire in one
 * chunk, so it can never exercise a chunk-boundary split. This cuts the encoded
 * BYTES at the given offsets and enqueues each piece separately, which is what
 * the network actually does.
 */
function serveWireSplitAtBytes(wire: string, ...offsets: number[]) {
  const bytes = new TextEncoder().encode(wire);
  const cuts = [0, ...offsets, bytes.length];
  const chunks: Uint8Array[] = [];
  for (let i = 0; i < cuts.length - 1; i++) {
    chunks.push(bytes.slice(cuts[i], cuts[i + 1]));
  }
  global.fetch = vi.fn(
    async () =>
      ({
        status: 200,
        ok: true,
        body: new ReadableStream<Uint8Array>({
          start(c) {
            for (const ch of chunks) c.enqueue(ch);
            c.close();
          },
        }),
      }) as unknown as Response,
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
      // `_sourceRunId` is the transport's source-run stamp — the hook is instantiated
      // per run, so every dispatched envelope carries it. Downstream run-scoping
      // (the foreign-run bleed guard in dashboard/page.tsx) depends on it.
      expect(onMessage).toHaveBeenCalledWith({
        type: "questionnaire_ready",
        data: {
          pipeline_run_id: "r",
          questions: [{ question_id: "q1", question_text: "Q?" }],
        },
        _sourceRunId: "r",
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
        _sourceRunId: "r",
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

describe("useRunStream — terminal event types mark non-live close (ISS-147 / R-07)", () => {
  // ISS-147 / SSE-002: the frontend's terminal-event guard now uses the canonical
  // STREAM_TERMINAL_TYPES constant (shared with backend's _STREAM_TERMINAL_TYPES
  // via frontend/src/types/index.ts). Test that every member prevents reconnect
  // (marks the connection non-live before the stream close fires).

  const createTerminalFrame = (type: string, seq: number) =>
    `id: ${seq}\r\ndata: {"type":"${type}","data":{"pipeline_run_id":"r","seq":${seq}}}\r\n\r\n`;

  for (const terminalType of Array.from(STREAM_TERMINAL_TYPES)) {
    it(`${terminalType}: terminal frame settles disconnected without reconnect`, async () => {
      const onMessage = vi.fn();
      serveWire(createTerminalFrame(terminalType, 100));

      const { result } = renderHook(() =>
        useRunStream({ runId: "r", token: "t.t.t", onMessage, enabled: true }),
      );

      // Each terminal type should receive its frame (envelope parsing works) AND
      // the connection should settle to "disconnected" without scheduling a reconnect.
      await waitFor(() =>
        expect(onMessage).toHaveBeenCalledWith(expect.objectContaining({ type: terminalType })),
      );
      await waitFor(() => expect(result.current.phase).toBe("disconnected"));
      expect(result.current.lastError ?? "").not.toMatch(/Reconnecting/i);
    });
  }
});


describe("useRunStream — chunk-boundary parser edge cases (SSE-003)", () => {
  const frame = (seq: number, type: string, extra = "") =>
    `id: ${seq}\r\ndata: {"type":"${type}","data":{"pipeline_run_id":"r","seq":${seq}${extra}}}\r\n\r\n`;

  it("re-assembles a frame terminator split between the CR and the LF", async () => {
    // Two frames, with the cut landing INSIDE frame 1's `\r\n\r\n` terminator —
    // specifically between its second `\r` and that `\r`'s `\n`. Neither chunk then
    // contains a complete `\r\n` pair at the seam.
    //
    // Two frames matter: with a single frame the missed boundary is masked by the
    // post-loop `if (buf.trim()) dispatchBlock(buf)` flush, so the bug is invisible.
    // With two, the un-normalized `\r` prevents `indexOf("\n\n")` from matching
    // frame 1's terminator, both frames coalesce into ONE block, and frame 1 is lost.
    const f1 = frame(1, "agent_start");
    const wire = f1 + frame(2, "agent_complete");
    // Frame content is ASCII, so byte offset == char index. Cut 1 byte before the
    // end of f1, i.e. between the final `\r` and `\n`.
    const cut = f1.length - 1;
    expect(wire[cut - 1]).toBe("\r"); // sanity: the seam really is mid-CRLF
    expect(wire[cut]).toBe("\n");

    serveWireSplitAtBytes(wire, cut);
    const onMessage = vi.fn();

    const { unmount } = renderHook(() =>
      useRunStream({ runId: "r", token: "t.t.t", onMessage, enabled: true }),
    );

    // BOTH frames must arrive as distinct dispatches.
    await waitFor(() =>
      expect(onMessage).toHaveBeenCalledWith(
        expect.objectContaining({ type: "agent_start" }),
      ),
    );
    await waitFor(() =>
      expect(onMessage).toHaveBeenCalledWith(
        expect.objectContaining({ type: "agent_complete" }),
      ),
    );
    // Neither frame is terminal, so the stream's end schedules a reconnect. Unmount
    // to cancel that timer — otherwise the backoff loop keeps issuing fetches for the
    // rest of the file's lifetime, adding contention that surfaces timeout flakes in
    // unrelated suites during a batch run.
    unmount();
  });

  it("re-assembles a multi-byte UTF-8 character split across chunks", async () => {
    // Regression guard rather than a bug repro: `decode(value, { stream: true })`
    // already handles this correctly. It was simply never exercised, because every
    // other test enqueues the body as a single chunk.
    const wire = frame(1, "agent_chunk", ',"text":"café ☕"');
    const bytes = new TextEncoder().encode(wire);
    // The last byte of a 3-byte char is a continuation byte (0b10xxxxxx). Cut
    // immediately before it so one code point straddles the chunk seam.
    const cut = bytes.length - 1 - new TextEncoder().encode('"}}\r\n\r\n').length;
    expect(bytes[cut] & 0b11000000).toBe(0b10000000); // sanity: mid-code-point

    serveWireSplitAtBytes(wire, cut);
    const onMessage = vi.fn();

    const { unmount } = renderHook(() =>
      useRunStream({ runId: "r", token: "t.t.t", onMessage, enabled: true }),
    );

    await waitFor(() => expect(onMessage).toHaveBeenCalled());
    const dispatched = onMessage.mock.calls[0][0];
    expect(dispatched.type).toBe("agent_chunk");
    // The character survives the seam intact — no U+FFFD replacement char.
    expect(dispatched.data.text).toBe("café ☕");
    unmount(); // cancel the post-stream reconnect timer (see note above)
  });
});
