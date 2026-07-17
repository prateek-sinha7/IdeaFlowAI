/**
 * useRunChat — the chat lane's family-anchored transcript DATA layer (Phase 31,
 * CHATUI-01). These tests drive the hook through its transport-agnostic
 * contract: a controllable `subscribe` fan-out pushes Phase-29 chat frames
 * (`chat_message` / `chat_reply` / `stream_attached`) and a `sendCommand` spy
 * captures the up-channel.
 *
 * Proves:
 *   1. a `chat_message` frame appends a user turn keyed by `message_id`;
 *   2. a `chat_reply` frame appends an assistant NARRATOR turn carrying
 *      `cardKind` + `deepLink`;
 *   3. the transcript ACCUMULATES — later frames APPEND, and a `pipeline_complete`
 *      state-change frame does NOT wipe a prior turn (LIVE-STATE-CONTRACT §0);
 *   4. duplicate frames (same `event_id`) are deduped;
 *   5. `sendMessage` optimistically renders, and the server echo reconciles by
 *      `message_id` (no duplicate bubble); the up-channel carries the id;
 *   6. family anchoring (D-02) — a child run's frames stitch into the SAME array;
 *   7. `legacyWsSend` (flag-OFF) routes the send through the legacy `user_message`
 *      frame instead of `sendCommand` — same transcript.
 */
import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useRunChat, type RunChatFrame } from "./useRunChat";

/** A controllable fan-out: `subscribe` records the sink; `emit` pushes a frame. */
function makeConn() {
  let sink: ((m: RunChatFrame) => void) | null = null;
  const sendCommand = vi.fn(async () => {});
  return {
    subscribe: (fn: (m: RunChatFrame) => void) => {
      sink = fn;
      return () => {
        sink = null;
      };
    },
    sendCommand,
    emit(frame: RunChatFrame) {
      act(() => {
        sink?.(frame);
      });
    },
  };
}

let evt = 0;
function frame(type: string, data: Record<string, unknown>): RunChatFrame {
  return { type, data: { event_id: `evt-${++evt}`, seq: evt, ...data } };
}

beforeEach(() => {
  evt = 0;
});

describe("useRunChat — family-anchored transcript reducer", () => {
  it("Test 1: a chat_message frame appends a user turn keyed by message_id", () => {
    const conn = makeConn();
    const { result } = renderHook(() =>
      useRunChat({ runId: "run-1", subscribe: conn.subscribe, sendCommand: conn.sendCommand }),
    );

    conn.emit(frame("chat_message", { message_id: "m1", text: "hello", run_id: "run-1" }));

    expect(result.current.messages).toHaveLength(1);
    const m = result.current.messages[0];
    expect(m.id).toBe("m1");
    expect(m.role).toBe("user");
    expect(m.content).toBe("hello");
    expect(m.runId).toBe("run-1");
  });

  it("Test 2: a chat_reply frame appends an assistant NARRATOR turn with cardKind + deepLink", () => {
    const conn = makeConn();
    const { result } = renderHook(() =>
      useRunChat({ runId: "run-1", subscribe: conn.subscribe, sendCommand: conn.sendCommand }),
    );

    conn.emit(
      frame("chat_reply", {
        message_id: "r1",
        text: "Paused — needs approval",
        card_kind: "gate",
        deep_link: { target: "steps", nonce: 7 },
        run_id: "run-1",
      }),
    );

    expect(result.current.messages).toHaveLength(1);
    const m = result.current.messages[0];
    expect(m.role).toBe("assistant");
    expect(m.cardKind).toBe("gate");
    expect(m.deepLink).toEqual({ tab: "steps", nonce: 7 });
  });

  it("Test 3: the transcript ACCUMULATES — later frames append, pipeline_complete does not wipe", () => {
    const conn = makeConn();
    const { result } = renderHook(() =>
      useRunChat({ runId: "run-1", subscribe: conn.subscribe, sendCommand: conn.sendCommand }),
    );

    conn.emit(frame("chat_message", { message_id: "m1", text: "first", run_id: "run-1" }));
    // A state-change frame (not a chat frame) must NOT clear the transcript.
    conn.emit(frame("pipeline_complete", { status: "completed", run_id: "run-1" }));
    conn.emit(frame("chat_reply", { message_id: "r1", text: "Delivered", card_kind: "deliverable", run_id: "run-1" }));

    expect(result.current.messages).toHaveLength(2);
    expect(result.current.messages[0].content).toBe("first"); // prior turn survived
    expect(result.current.messages[1].cardKind).toBe("deliverable");
  });

  it("Test 4: duplicate frames (same event_id) are deduped", () => {
    const conn = makeConn();
    const { result } = renderHook(() =>
      useRunChat({ runId: "run-1", subscribe: conn.subscribe, sendCommand: conn.sendCommand }),
    );

    const dup: RunChatFrame = {
      type: "chat_message",
      data: { event_id: "evt-fixed", seq: 1, message_id: "m1", text: "once", run_id: "run-1" },
    };
    conn.emit(dup);
    conn.emit(dup); // replayed with the SAME event_id → dropped

    expect(result.current.messages).toHaveLength(1);
  });

  it("Test 5: sendMessage optimistically renders and the server echo reconciles by message_id", () => {
    const conn = makeConn();
    const { result } = renderHook(() =>
      useRunChat({ runId: "run-9", subscribe: conn.subscribe, sendCommand: conn.sendCommand }),
    );

    let mid = "";
    act(() => {
      mid = result.current.sendMessage("optimistic hi");
    });

    // Optimistic bubble rendered immediately + up-channel carried the id.
    expect(result.current.messages).toHaveLength(1);
    expect(result.current.messages[0].content).toBe("optimistic hi");
    expect(conn.sendCommand).toHaveBeenCalledWith(
      "run-9",
      expect.objectContaining({ text: "optimistic hi", message_id: mid }),
    );

    // The server echo with the SAME message_id reconciles — no duplicate bubble.
    conn.emit(frame("chat_message", { message_id: mid, text: "optimistic hi", run_id: "run-9" }));
    expect(result.current.messages).toHaveLength(1);

    // A DIFFERENT id appends as a distinct turn (T-31-03-S).
    conn.emit(frame("chat_message", { message_id: "other", text: "someone else", run_id: "run-9" }));
    expect(result.current.messages).toHaveLength(2);
  });

  it("Test 6: family anchoring — a child run's frames stitch into the SAME transcript", () => {
    const conn = makeConn();
    const { result } = renderHook(() =>
      useRunChat({ runId: "run-parent", subscribe: conn.subscribe, sendCommand: conn.sendCommand }),
    );

    conn.emit(frame("chat_message", { message_id: "p1", text: "parent turn", run_id: "run-parent", thread_id: "t-parent" }));
    // A child (revision) run — DIFFERENT run_id — stitches into the same array.
    conn.emit(frame("chat_reply", { message_id: "c1", text: "v2 building…", card_kind: "spec_revision", run_id: "run-child", thread_id: "t-child" }));

    expect(result.current.messages).toHaveLength(1 + 1);
    expect(result.current.messages[0].runId).toBe("run-parent");
    expect(result.current.messages[1].runId).toBe("run-child");
    expect(result.current.messages[1].cardKind).toBe("spec_revision");
  });

  it("Test 7: legacyWsSend (flag-OFF) routes the send through user_message, not sendCommand", () => {
    const conn = makeConn();
    const legacyWsSend = vi.fn();
    const { result } = renderHook(() =>
      useRunChat({
        runId: "run-1",
        subscribe: conn.subscribe,
        sendCommand: conn.sendCommand,
        legacyWsSend,
      }),
    );

    act(() => {
      result.current.sendMessage("legacy path");
    });

    expect(conn.sendCommand).not.toHaveBeenCalled();
    expect(legacyWsSend).toHaveBeenCalledWith(
      expect.objectContaining({ type: "user_message", text: "legacy path" }),
    );
    expect(result.current.messages).toHaveLength(1); // same optimistic transcript
  });

  it("Test 9: sendMessage with { concierge: true } folds concierge onto the up-channel payload (43-02)", () => {
    const conn = makeConn();
    const { result } = renderHook(() =>
      useRunChat({ runId: "run-9", subscribe: conn.subscribe, sendCommand: conn.sendCommand }),
    );

    act(() => {
      result.current.sendMessage("what's the status?", [], { concierge: true });
    });

    expect(conn.sendCommand).toHaveBeenCalledWith(
      "run-9",
      expect.objectContaining({ text: "what's the status?", concierge: true }),
    );
  });

  it("Test 10: sendMessage with a confirm_proposal folds the exact { channel, params } (43-02)", () => {
    const conn = makeConn();
    const { result } = renderHook(() =>
      useRunChat({ runId: "run-9", subscribe: conn.subscribe, sendCommand: conn.sendCommand }),
    );

    act(() => {
      result.current.sendMessage("go", [], {
        concierge: true,
        confirm_proposal: { channel: "gate_action", params: { action: "approve" } },
      });
    });

    expect(conn.sendCommand).toHaveBeenCalledWith(
      "run-9",
      expect.objectContaining({
        concierge: true,
        confirm_proposal: { channel: "gate_action", params: { action: "approve" } },
      }),
    );
  });

  it("Test 11: sendMessage with NO options posts a payload with NO concierge key (dormant/unchanged)", () => {
    const conn = makeConn();
    const { result } = renderHook(() =>
      useRunChat({ runId: "run-9", subscribe: conn.subscribe, sendCommand: conn.sendCommand }),
    );

    act(() => {
      result.current.sendMessage("plain turn");
    });

    expect(conn.sendCommand).toHaveBeenCalledTimes(1);
    const payload = (conn.sendCommand.mock.calls[0] as unknown[])[1] as Record<
      string,
      unknown
    >;
    expect(payload).not.toHaveProperty("concierge");
    expect(payload).not.toHaveProperty("confirm_proposal");
    expect(payload).toMatchObject({ text: "plain turn" });
  });

  it("Test 12: a chat_reply keyed on a DISTINCT event_id appends as its own turn (DEF-44-12-2 de-collision)", () => {
    // The Concierge reply carries message_id === the user turn's id
    // (run_commands.py:994) but a DISTINCT event_id ("chat-reply:{id}"). Keying
    // the assistant bubble on event_id makes it append instead of matching-and-
    // overwriting the user's question bubble (the landmine).
    const conn = makeConn();
    const { result } = renderHook(() =>
      useRunChat({ runId: "run-9", subscribe: conn.subscribe, sendCommand: conn.sendCommand }),
    );

    // A prior user turn keyed on message_id "m-collide".
    conn.emit(frame("chat_message", { message_id: "m-collide", text: "what is the status?", run_id: "run-9" }));
    // The reply carries the SAME message_id but a distinct event_id.
    conn.emit(
      frame("chat_reply", {
        event_id: "chat-reply:m-collide",
        message_id: "m-collide",
        text: "Still building — 3 of 5 done.",
        run_id: "run-9",
      }),
    );

    expect(result.current.messages).toHaveLength(2);
    // The user's question bubble is preserved (role + text intact).
    expect(result.current.messages[0].role).toBe("user");
    expect(result.current.messages[0].content).toBe("what is the status?");
    // The reply is its OWN assistant turn.
    expect(result.current.messages[1].role).toBe("assistant");
    expect(result.current.messages[1].content).toBe("Still building — 3 of 5 done.");
  });

  it("Test 13: sendMessage re-fetches events after the up-channel and folds the reply idempotently (DEF-44-12-2)", async () => {
    const conn = makeConn();
    const replyFrame: RunChatFrame = {
      type: "chat_reply",
      data: {
        event_id: "chat-reply:r-once",
        message_id: "r-once",
        text: "Concierge reply",
        seq: 5,
        run_id: "run-9",
      },
    };
    const fetchEvents = vi.fn(async () => [replyFrame]);
    const { result } = renderHook(() =>
      useRunChat({
        runId: "run-9",
        subscribe: conn.subscribe,
        sendCommand: conn.sendCommand,
        fetchEvents,
      }),
    );

    await act(async () => {
      result.current.sendMessage("ask the concierge");
    });

    // The up-channel fired, then fetchEvents was awaited and the reply folded.
    expect(conn.sendCommand).toHaveBeenCalledTimes(1);
    expect(fetchEvents).toHaveBeenCalled();
    // optimistic user turn + the folded reply.
    expect(result.current.messages).toHaveLength(2);
    expect(result.current.messages[1].role).toBe("assistant");
    expect(result.current.messages[1].content).toBe("Concierge reply");

    // A second send re-fetches the SAME reply frame — deduped by event_id, so the
    // reply is NOT duplicated (only a fresh optimistic user turn is added).
    await act(async () => {
      result.current.sendMessage("again");
    });
    const replies = result.current.messages.filter((m) => m.role === "assistant");
    expect(replies).toHaveLength(1);
  });

  it("Test 8: stream_attached updates the handshake state without touching the transcript", () => {
    const conn = makeConn();
    const { result } = renderHook(() =>
      useRunChat({ runId: "run-1", subscribe: conn.subscribe, sendCommand: conn.sendCommand }),
    );

    conn.emit(frame("chat_message", { message_id: "m1", text: "hi", run_id: "run-1" }));
    conn.emit(frame("stream_attached", { live: true, replayed_through_seq: 42, run_id: "run-1" }));

    expect(result.current.streamAttached).toEqual({ live: true, replayedThroughSeq: 42 });
    expect(result.current.messages).toHaveLength(1); // transcript untouched
  });

  it("Test 14: fetchEvents fires ONLY after the up-channel send resolves (BUG-017 ordering guard)", async () => {
    const conn = makeConn();
    // A deferred up-channel: `innerSend` resolves ONLY when the test calls
    // `resolve()`, mimicking runConnection.sendCommand (whose /messages POST
    // resolves after the reply is persisted).
    let resolveSend!: () => void;
    const sendPromise = new Promise<void>((r) => {
      resolveSend = r;
    });
    const innerSend = vi.fn(() => sendPromise);
    // The adapter mirrors page.tsx's CURRENT (buggy) shape: it VOIDs innerSend
    // and returns undefined, so the hook's `await sendCommand(...)` awaits
    // `undefined` and resolves immediately — the re-fetch races ahead.
    const sendCommand = (r: string | null, p: Record<string, unknown>) => {
      void innerSend(r, p);
    };
    const fetchEvents = vi.fn(async () => []);

    const { result } = renderHook(() =>
      useRunChat({
        runId: "run-9",
        subscribe: conn.subscribe,
        sendCommand,
        fetchEvents,
      }),
    );

    // Drive the send, flushing a microtask WITHOUT resolving the deferred.
    await act(async () => {
      result.current.sendMessage("ask the concierge");
      await Promise.resolve();
    });

    // The up-channel fired once — but the re-fetch must NOT have run yet, since
    // the send has not settled (the load-bearing ordering assertion).
    expect(innerSend).toHaveBeenCalledTimes(1);
    expect(fetchEvents).not.toHaveBeenCalled();

    // Resolve the send → the re-fetch now runs (send-then-fetch ordering).
    await act(async () => {
      resolveSend();
      await sendPromise;
    });
    expect(fetchEvents).toHaveBeenCalled();
  });
});
