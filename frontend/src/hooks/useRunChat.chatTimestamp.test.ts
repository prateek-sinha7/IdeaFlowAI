/**
 * ISS-358 / ISS-595 — chat message timestamps must reflect the real send
 * time, not the moment the transcript happens to fold the frame.
 *
 * Register entry: BUG-20260828-095700-runs-id-chat-timestamp
 * (bug-hunter/ledger.md).
 *
 * Root cause (ISS-358): `upsertUserMessage` / `upsertNarratorMessage`
 * (useRunChat.ts:354, :393) unconditionally stamp `createdAt: new
 * Date().toISOString()` on every "create" fold, ignoring any `created_at`
 * the frame's `data` payload might carry. Every historical frame replayed
 * on a cold reload takes this "create" branch (seedRunChatTranscript resets
 * `messages` to `[]` first), so the displayed time always becomes the
 * reload's wall-clock "now" instead of the original send time.
 *
 * ISS-595 is the same defect reached via `seedTranscript` (the
 * still-generating-run switch path, not just a full reload) — the fold
 * function folded is identical, so the same frame-with-created_at case
 * proves both entry points share one root cause.
 */
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useRunChat, type RunChatFrame } from "./useRunChat";

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

afterEach(() => {
  vi.useRealTimers();
});

describe("useRunChat — ISS-358 chat message timestamp must be the real send time", () => {
  it("a chat_message frame carrying created_at must render with THAT time, not the fold-time now", () => {
    const REAL_SEND_TIME = "2026-08-28T09:51:00.000Z";
    const RELOAD_TIME = "2026-08-28T09:56:00.000Z";

    vi.useFakeTimers();
    vi.setSystemTime(new Date(RELOAD_TIME));

    const conn = makeConn();
    const { result } = renderHook(() =>
      useRunChat({ runId: "run-1", subscribe: conn.subscribe, sendCommand: conn.sendCommand }),
    );

    // Simulates a replayed durable row for a message that was actually sent
    // at REAL_SEND_TIME, folded during a reload happening at RELOAD_TIME.
    conn.emit(
      frame("chat_message", {
        message_id: "m1",
        text: "Can you make the title larger?",
        run_id: "run-1",
        created_at: REAL_SEND_TIME,
      }),
    );

    expect(result.current.messages).toHaveLength(1);
    // FAILS TODAY: the hook stamps new Date().toISOString() (RELOAD_TIME)
    // regardless of data.created_at, so the reload keeps overwriting the
    // displayed time with whatever moment the page happened to load.
    expect(result.current.messages[0].createdAt).toBe(REAL_SEND_TIME);
    expect(result.current.messages[0].createdAt).not.toBe(RELOAD_TIME);
  });

  it("a chat_reply frame carrying created_at must render with THAT time, not the fold-time now", () => {
    const REAL_SEND_TIME = "2026-08-28T09:51:30.000Z";
    const RELOAD_TIME = "2026-08-28T09:56:00.000Z";

    vi.useFakeTimers();
    vi.setSystemTime(new Date(RELOAD_TIME));

    const conn = makeConn();
    const { result } = renderHook(() =>
      useRunChat({ runId: "run-1", subscribe: conn.subscribe, sendCommand: conn.sendCommand }),
    );

    conn.emit(
      frame("chat_reply", {
        message_id: "r1",
        text: "Sure, I'll bump the title size.",
        run_id: "run-1",
        created_at: REAL_SEND_TIME,
      }),
    );

    expect(result.current.messages).toHaveLength(1);
    expect(result.current.messages[0].createdAt).toBe(REAL_SEND_TIME);
    expect(result.current.messages[0].createdAt).not.toBe(RELOAD_TIME);
  });
});

describe("useRunChat — ISS-595 seedTranscript replay must also honour created_at", () => {
  it("seedTranscript-replayed frames (still-generating-run switch) must keep their real send time, not the switch-time now", () => {
    const REAL_SEND_TIME = "2026-08-28T09:13:00.000Z";
    const SWITCH_TIME = "2026-08-28T09:17:00.000Z";

    vi.useFakeTimers();
    vi.setSystemTime(new Date(SWITCH_TIME));

    const conn = makeConn();
    const { result } = renderHook(() =>
      useRunChat({ runId: "run-2", subscribe: conn.subscribe, sendCommand: conn.sendCommand }),
    );

    // handleSwitchToLiveRun's path: seedTranscript replays the durable frames
    // for a run that is still generating, through the SAME "create" fold.
    act(() => {
      result.current.seedTranscript([
        {
          type: "chat_message",
          data: {
            event_id: "user-evt:1",
            message_id: "m1",
            text: "earlier question",
            run_id: "run-2",
            created_at: REAL_SEND_TIME,
          },
        },
      ]);
    });

    expect(result.current.messages).toHaveLength(1);
    // FAILS TODAY: seedTranscript clears messages first, so the replayed
    // frame takes the same unconditional new Date().toISOString() branch —
    // the switch-time now, not the original send time.
    expect(result.current.messages[0].createdAt).toBe(REAL_SEND_TIME);
    expect(result.current.messages[0].createdAt).not.toBe(SWITCH_TIME);
  });
});
