import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  expireSession: vi.fn(),
  getToken: vi.fn<() => string | null>(),
  getTokenExpiryMs: vi.fn<(token: string | null) => number | null>(),
  refreshOnce: vi.fn<() => Promise<string | null>>(),
}));

vi.mock("@/lib/api", () => ({
  expireSession: api.expireSession,
  getToken: api.getToken,
  getTokenExpiryMs: api.getTokenExpiryMs,
  refreshOnce: api.refreshOnce,
  SESSION_REFRESH_SKEW_MS: 60_000,
}));

import type { BuilderEvent } from "@/types/workflowBuilder";

import {
  builderBackoffDelayMs,
  useBuilderSessionStream,
  type BuilderStreamPhase,
} from "./useBuilderSessionStream";

const TS = "2026-01-01T00:00:00Z";
const encoder = new TextEncoder();

function frame(type: string, data: Record<string, unknown> = { ts: TS }): string {
  return `data: ${JSON.stringify({ type, data })}\n\n`;
}

const snapshotFrame = frame("snapshot", {
  ts: TS,
  state: "idle",
  running_turn: null,
  latest_message_id: null,
  latest_revision: null,
  latest_unproposed_revision: null,
});

interface FakeResponseOptions {
  /** Keep the stream open after the chunks are read, as a live server does. */
  hold?: boolean;
}

/**
 * A response whose body is read by hand, so no real stream or timer is involved
 * and the fake clock alone decides when the hook reconnects.
 */
function streamResponse(chunks: string[], options: FakeResponseOptions = {}): Response {
  const queue = chunks.map((chunk) => encoder.encode(chunk));
  const reader = {
    read: (): Promise<{ done: boolean; value?: Uint8Array }> => {
      const next = queue.shift();
      if (next !== undefined) return Promise.resolve({ done: false, value: next });
      if (options.hold) return new Promise(() => undefined);
      return Promise.resolve({ done: true });
    },
    cancel: () => Promise.resolve(),
  };
  return { status: 200, ok: true, body: { getReader: () => reader } } as unknown as Response;
}

function statusResponse(status: number): Response {
  return { status, ok: status >= 200 && status < 300, body: null } as unknown as Response;
}

type FetchFn = (url: string, init: RequestInit) => Promise<Response>;
const fetchMock = vi.fn<FetchFn>();

/** Let the connect loop's promise chain settle and fire timers up to `ms`. */
async function advance(ms: number): Promise<void> {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

function mountHook(
  overrides: { sessionId?: string | null; enabled?: boolean } = {},
): {
  events: BuilderEvent[];
  phase: () => BuilderStreamPhase;
  reconnect: () => void;
  unmount: () => void;
} {
  const events: BuilderEvent[] = [];
  const onEvent = (event: BuilderEvent) => {
    events.push(event);
  };
  const { result, unmount } = renderHook(() =>
    useBuilderSessionStream({
      sessionId: overrides.sessionId === undefined ? "s1" : overrides.sessionId,
      enabled: overrides.enabled ?? true,
      onEvent,
    }),
  );
  return {
    events,
    phase: () => result.current.phase,
    reconnect: () => result.current.reconnect(),
    unmount,
  };
}

describe("builderBackoffDelayMs", () => {
  it("doubles from 1 s and caps at 30 s", () => {
    expect([0, 1, 2, 3, 4, 5, 6].map(builderBackoffDelayMs)).toEqual([
      1000, 2000, 4000, 8000, 16000, 30000, 30000,
    ]);
  });
});

describe("useBuilderSessionStream", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    fetchMock.mockReset();
    api.expireSession.mockReset();
    api.getToken.mockReset().mockReturnValue("tok");
    api.getTokenExpiryMs.mockReset().mockReturnValue(null);
    api.refreshOnce.mockReset().mockResolvedValue(null);
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  describe("request", () => {
    it("sends the bearer token and event-stream accept, with no Last-Event-ID", async () => {
      fetchMock.mockResolvedValue(streamResponse([snapshotFrame], { hold: true }));

      const hook = mountHook({ sessionId: "a/b" });
      await advance(0);

      const [url, init] = fetchMock.mock.calls[0];
      expect(url).toMatch(/\/api\/workflow-builder\/sessions\/a%2Fb\/events$/);
      expect(init.headers).toEqual({ Accept: "text/event-stream", Authorization: "Bearer tok" });
      expect(Object.keys(init.headers as Record<string, string>)).not.toContain("Last-Event-ID");
      expect(hook.phase()).toBe("open");
    });

    it("stays idle and opens no connection when disabled or without a session", async () => {
      const disabled = mountHook({ enabled: false });
      const noSession = mountHook({ sessionId: null });
      await advance(60_000);

      expect(fetchMock).not.toHaveBeenCalled();
      expect(disabled.phase()).toBe("idle");
      expect(noSession.phase()).toBe("idle");
    });
  });

  describe("events", () => {
    it("merges the type into the event data and passes known events in order", async () => {
      fetchMock.mockResolvedValue(
        streamResponse([snapshotFrame, frame("stage", { ts: TS, turn_id: "t1", seq: 1 })], {
          hold: true,
        }),
      );

      const hook = mountHook();
      await advance(0);

      expect(hook.events.map((e) => e.type)).toEqual(["snapshot", "stage"]);
      expect(hook.events[1]).toMatchObject({ type: "stage", turn_id: "t1", seq: 1 });
    });

    it("drops keep-alive comments and unknown event names", async () => {
      fetchMock.mockResolvedValue(
        streamResponse([": keep-alive\n\n", frame("future_event"), snapshotFrame], { hold: true }),
      );

      const hook = mountHook();
      await advance(0);

      expect(hook.events.map((e) => e.type)).toEqual(["snapshot"]);
    });

    it("reassembles a frame split across chunks, including a split CRLF", async () => {
      const whole = snapshotFrame.replace(/\n/g, "\r\n");
      const cut = whole.indexOf("\r\n") + 1; // between \r and \n
      fetchMock.mockResolvedValue(
        streamResponse([whole.slice(0, 10), whole.slice(10, cut), whole.slice(cut)], {
          hold: true,
        }),
      );

      const hook = mountHook();
      await advance(0);

      expect(hook.events.map((e) => e.type)).toEqual(["snapshot"]);
    });
  });

  describe("backoff", () => {
    it("reconnects after 1, 2, 4, 8, 16 then 30 s while the server keeps failing", async () => {
      fetchMock.mockResolvedValue(statusResponse(500));

      const hook = mountHook();
      await advance(0);
      expect(fetchMock).toHaveBeenCalledTimes(1);
      expect(hook.phase()).toBe("reconnecting");

      let calls = 1;
      for (const delay of [1000, 2000, 4000, 8000, 16000, 30000, 30000]) {
        await advance(delay - 1);
        expect(fetchMock).toHaveBeenCalledTimes(calls);
        await advance(1);
        calls += 1;
        expect(fetchMock).toHaveBeenCalledTimes(calls);
      }
    });

    it("reconnects after a network error", async () => {
      fetchMock.mockRejectedValueOnce(new TypeError("network down"));
      fetchMock.mockResolvedValue(streamResponse([snapshotFrame], { hold: true }));

      const hook = mountHook();
      await advance(0);
      expect(hook.phase()).toBe("reconnecting");

      await advance(1000);

      expect(fetchMock).toHaveBeenCalledTimes(2);
      expect(hook.phase()).toBe("open");
    });

    it("reconnects when the server closes the stream, and resets the delay after an event", async () => {
      fetchMock
        .mockResolvedValueOnce(statusResponse(500))
        .mockResolvedValueOnce(statusResponse(500))
        // Third attempt delivers a snapshot, then the server closes.
        .mockResolvedValueOnce(streamResponse([snapshotFrame]))
        .mockResolvedValue(statusResponse(500));

      mountHook();
      await advance(0); // attempt 1 fails, next delay 1 s
      await advance(1000); // attempt 2 fails, next delay 2 s
      await advance(2000); // attempt 3 delivers an event and closes
      expect(fetchMock).toHaveBeenCalledTimes(3);

      // Without the reset the wait would be 4 s; with it, 1 s.
      await advance(999);
      expect(fetchMock).toHaveBeenCalledTimes(3);
      await advance(1);
      expect(fetchMock).toHaveBeenCalledTimes(4);
    });

    it("does not reset the delay when the server answers 200 and closes with no event", async () => {
      fetchMock
        .mockResolvedValueOnce(streamResponse([]))
        .mockResolvedValueOnce(streamResponse([]))
        .mockResolvedValue(streamResponse([], { hold: true }));

      mountHook();
      await advance(0); // closes at once, next delay 1 s
      await advance(1000); // closes at once, next delay 2 s
      expect(fetchMock).toHaveBeenCalledTimes(2);

      await advance(1999);
      expect(fetchMock).toHaveBeenCalledTimes(2);
      await advance(1);
      expect(fetchMock).toHaveBeenCalledTimes(3);
    });

    it("reconnect() attaches at once and restarts the schedule at 1 s", async () => {
      fetchMock.mockResolvedValue(statusResponse(500));

      const hook = mountHook();
      await advance(0);
      await advance(1000);
      await advance(2000); // three attempts, next delay would be 4 s
      expect(fetchMock).toHaveBeenCalledTimes(3);

      act(() => hook.reconnect());
      await advance(0);
      expect(fetchMock).toHaveBeenCalledTimes(4);

      // The failed manual attempt waits 1 s, not 8 s.
      await advance(1000);
      expect(fetchMock).toHaveBeenCalledTimes(5);
    });
  });

  describe("stopping for good", () => {
    it("stops on a 404 without reconnecting or expiring the session", async () => {
      fetchMock.mockResolvedValue(statusResponse(404));

      const hook = mountHook();
      await advance(0);

      expect(hook.phase()).toBe("closed_not_found");
      await advance(120_000);
      expect(fetchMock).toHaveBeenCalledTimes(1);
      expect(api.expireSession).not.toHaveBeenCalled();

      act(() => hook.reconnect());
      await advance(0);
      expect(fetchMock).toHaveBeenCalledTimes(1);
    });

    it("stops on session_deleted without calling expireSession", async () => {
      fetchMock.mockResolvedValue(streamResponse([snapshotFrame, frame("session_deleted")]));

      const hook = mountHook();
      await advance(0);

      expect(hook.events.map((e) => e.type)).toEqual(["snapshot", "session_deleted"]);
      expect(hook.phase()).toBe("closed_deleted");
      await advance(120_000);
      expect(fetchMock).toHaveBeenCalledTimes(1);
      expect(api.expireSession).not.toHaveBeenCalled();
    });

    it("stops on session_revoked, delivers it, and calls expireSession once", async () => {
      fetchMock.mockResolvedValue(
        streamResponse([
          frame("session_revoked", { ts: TS, session_id: "s1", reason: "logout" }),
          frame("stage", { ts: TS, turn_id: "t1", seq: 1 }),
        ]),
      );

      const hook = mountHook();
      await advance(0);

      expect(hook.events.map((e) => e.type)).toEqual(["session_revoked"]);
      expect(hook.phase()).toBe("closed_revoked");
      expect(api.expireSession).toHaveBeenCalledTimes(1);
      await advance(120_000);
      expect(fetchMock).toHaveBeenCalledTimes(1);
    });

    it("expires the session when there is no token", async () => {
      api.getToken.mockReturnValue(null);

      const hook = mountHook();
      await advance(0);

      expect(fetchMock).not.toHaveBeenCalled();
      expect(hook.phase()).toBe("closed_auth");
      expect(api.expireSession).toHaveBeenCalledTimes(1);
    });
  });

  describe("authentication", () => {
    it("retries once after a silent refresh on 401", async () => {
      api.refreshOnce.mockResolvedValue("fresh");
      fetchMock
        .mockResolvedValueOnce(statusResponse(401))
        .mockResolvedValue(streamResponse([snapshotFrame], { hold: true }));

      const hook = mountHook();
      await advance(0);

      expect(api.refreshOnce).toHaveBeenCalledTimes(1);
      expect(fetchMock).toHaveBeenCalledTimes(2);
      expect(hook.phase()).toBe("open");
      expect(api.expireSession).not.toHaveBeenCalled();
    });

    it("expires the session when a second 401 follows the refresh", async () => {
      api.refreshOnce.mockResolvedValue("fresh");
      fetchMock.mockResolvedValue(statusResponse(401));

      const hook = mountHook();
      await advance(0);

      expect(fetchMock).toHaveBeenCalledTimes(2);
      expect(api.refreshOnce).toHaveBeenCalledTimes(1);
      expect(hook.phase()).toBe("closed_auth");
      expect(api.expireSession).toHaveBeenCalledTimes(1);
      await advance(120_000);
      expect(fetchMock).toHaveBeenCalledTimes(2);
    });

    it("expires the session on 403 when the refresh yields no token", async () => {
      fetchMock.mockResolvedValue(statusResponse(403));

      const hook = mountHook();
      await advance(0);

      expect(fetchMock).toHaveBeenCalledTimes(1);
      expect(hook.phase()).toBe("closed_auth");
      expect(api.expireSession).toHaveBeenCalledTimes(1);
    });
  });

  describe("silent token refresh", () => {
    it("refreshes one skew before expiry and re-attaches with the new token", async () => {
      const expiry = Date.now() + 120_000;
      api.getTokenExpiryMs.mockReturnValueOnce(expiry).mockReturnValue(expiry + 3_600_000);
      api.refreshOnce.mockResolvedValue("fresh");
      api.getToken.mockReturnValueOnce("tok").mockReturnValue("fresh");
      fetchMock.mockImplementation(() => Promise.resolve(streamResponse([], { hold: true })));

      mountHook();
      await advance(0);
      expect(fetchMock).toHaveBeenCalledTimes(1);

      await advance(59_999);
      expect(api.refreshOnce).not.toHaveBeenCalled();
      await advance(1);

      expect(api.refreshOnce).toHaveBeenCalledTimes(1);
      expect(fetchMock).toHaveBeenCalledTimes(2);
      const init = fetchMock.mock.calls[1][1];
      expect(init.headers).toMatchObject({ Authorization: "Bearer fresh" });
    });

    it("keeps the stream through a failed refresh and expires the session at true expiry", async () => {
      const expiry = Date.now() + 90_000;
      api.getTokenExpiryMs.mockReturnValue(expiry);
      api.refreshOnce.mockResolvedValue(null);
      fetchMock.mockResolvedValue(streamResponse([], { hold: true }));

      const hook = mountHook();
      await advance(0);

      await advance(30_000); // refresh fires, fails, token not yet expired
      expect(api.refreshOnce).toHaveBeenCalledTimes(1);
      expect(api.expireSession).not.toHaveBeenCalled();

      await advance(60_000); // second attempt at expiry
      expect(api.refreshOnce).toHaveBeenCalledTimes(2);
      expect(api.expireSession).toHaveBeenCalledTimes(1);
      expect(hook.phase()).toBe("closed_auth");
    });
  });

  describe("unmount", () => {
    it("aborts the request and cancels a pending reconnect", async () => {
      fetchMock.mockResolvedValue(statusResponse(500));

      const hook = mountHook();
      await advance(0);
      expect(fetchMock).toHaveBeenCalledTimes(1);
      const signal = fetchMock.mock.calls[0][1].signal;

      hook.unmount();
      await advance(120_000);

      expect(signal?.aborted).toBe(true);
      expect(fetchMock).toHaveBeenCalledTimes(1);
    });
  });
});
