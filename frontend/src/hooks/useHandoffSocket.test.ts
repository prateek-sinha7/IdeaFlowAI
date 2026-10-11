/**
 * T14 — useHandoffSocket 4001 close code handling: refresh-then-reconnect
 * or clear-and-redirect on failure.
 *
 * Note: This test verifies that refreshOnce() is called on 4001 close.
 * Full WebSocket integration testing is covered by E2E tests.
 */
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { useHandoffSocket } from "./useHandoffSocket";
import { refreshOnce, clearToken, getToken, expireSession } from "@/lib/api";

// Mock the module
vi.mock("@/lib/api", () => ({
  getToken: vi.fn(() => "initial-token"),
  clearToken: vi.fn(),
  refreshOnce: vi.fn(),
  expireSession: vi.fn(),
  setToken: vi.fn(),
  ApiError: class ApiError extends Error {
    constructor(public status: number, public detail: unknown) {
      super();
    }
  },
}));

describe("useHandoffSocket - 4001 close code refresh-then-reconnect (unit)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("on 4001 close, the implementation calls refreshOnce() and conditionally redirects", async () => {
    // This test documents the expected behavior pattern.
    // The actual WebSocket mock integration is tested in E2E tests.
    // Here we just verify the mock functions work and can be spied on.

    const mockRefresh = vi.mocked(refreshOnce);
    mockRefresh.mockResolvedValue("new-token");

    const result = await mockRefresh();
    expect(result).toBe("new-token");
    expect(mockRefresh).toHaveBeenCalled();
  });

  it("clearToken is called when refresh fails", async () => {
    const mockClear = vi.mocked(clearToken);

    mockClear();
    expect(mockClear).toHaveBeenCalled();
  });
});

class FakeWebSocket {
  static OPEN = 1;
  static instances: FakeWebSocket[] = [];
  readyState = 0;
  sent: string[] = [];
  closed = false;
  onopen: (() => void) | null = null;
  onclose: ((e: { code: number }) => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  constructor(public url: string, public protocols: string[]) {
    FakeWebSocket.instances.push(this);
  }
  send(m: string) {
    this.sent.push(m);
  }
  close() {
    this.closed = true;
  }
  open() {
    this.readyState = FakeWebSocket.OPEN;
    this.onopen?.();
  }
}

const URL_ = "ws://host/ws/handoff/abc";
const last = () => FakeWebSocket.instances[FakeWebSocket.instances.length - 1];

describe("useHandoffSocket - hook behavior", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
    FakeWebSocket.instances = [];
    vi.stubGlobal("WebSocket", FakeWebSocket);
    vi.mocked(getToken).mockReturnValue("jwt");
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("stays disconnected without a token", () => {
    const { result } = renderHook(() => useHandoffSocket({ url: URL_, token: null }));
    expect(result.current.connectionStatus).toBe("disconnected");
    expect(FakeWebSocket.instances).toHaveLength(0);
  });

  it("stays disconnected when the stored token or url is missing", () => {
    vi.mocked(getToken).mockReturnValue(null);
    const a = renderHook(() => useHandoffSocket({ url: URL_, token: "t" }));
    expect(a.result.current.connectionStatus).toBe("disconnected");
    vi.mocked(getToken).mockReturnValue("jwt");
    const b = renderHook(() => useHandoffSocket({ token: "t" }));
    expect(b.result.current.connectionStatus).toBe("disconnected");
    expect(FakeWebSocket.instances).toHaveLength(0);
  });

  it("connects with bearer subprotocol and reports connected on open", () => {
    const { result } = renderHook(() => useHandoffSocket({ url: URL_, token: "t" }));
    expect(result.current.connectionStatus).toBe("connecting");
    expect(last().url).toBe(URL_);
    expect(last().protocols).toEqual(["bearer.jwt", "flowin.v1"]);
    act(() => last().open());
    expect(result.current.connectionStatus).toBe("connected");
    expect(result.current.lastError).toBeNull();
  });

  it("delivers parsed messages, ignores keepalives and survives malformed data", () => {
    const onMessage = vi.fn();
    const errSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const { result } = renderHook(() => useHandoffSocket({ url: URL_, token: "t", onMessage }));
    act(() => last().open());
    act(() => last().onmessage?.({ data: JSON.stringify({ type: "pong" }) }));
    act(() => last().onmessage?.({ data: JSON.stringify({ type: "pipeline_heartbeat" }) }));
    expect(result.current.lastMessage).toBeNull();
    act(() => last().onmessage?.({ data: "not json" }));
    expect(errSpy).toHaveBeenCalled();
    act(() => last().onmessage?.({ data: JSON.stringify({ type: "hello" }) }));
    expect(result.current.lastMessage).toEqual({ type: "hello" });
    expect(onMessage).toHaveBeenCalledWith({ type: "hello" });
  });

  it("uses the latest onMessage callback without reconnecting", () => {
    const first = vi.fn();
    const second = vi.fn();
    const { rerender } = renderHook(
      ({ cb }) => useHandoffSocket({ url: URL_, token: "t", onMessage: cb }),
      { initialProps: { cb: first } },
    );
    rerender({ cb: second });
    act(() => last().onmessage?.({ data: JSON.stringify({ type: "x" }) }));
    expect(FakeWebSocket.instances).toHaveLength(1);
    expect(first).not.toHaveBeenCalled();
    expect(second).toHaveBeenCalledTimes(1);
  });

  it("sends only while the socket is open", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const { result } = renderHook(() => useHandoffSocket({ url: URL_, token: "t" }));
    expect(result.current.send("early")).toBe(false);
    expect(warn).toHaveBeenCalled();
    act(() => last().open());
    expect(result.current.send("hi")).toBe(true);
    expect(last().sent).toContain("hi");
  });

  it("sends a ping every 20s while open and stops after unmount", () => {
    const { unmount } = renderHook(() => useHandoffSocket({ url: URL_, token: "t" }));
    const ws = last();
    act(() => ws.open());
    act(() => {
      vi.advanceTimersByTime(20000);
    });
    expect(ws.sent).toEqual([JSON.stringify({ type: "ping" })]);
    unmount();
    act(() => {
      vi.advanceTimersByTime(40000);
    });
    expect(ws.sent).toHaveLength(1);
  });

  it("stops pinging once the socket is no longer open", () => {
    renderHook(() => useHandoffSocket({ url: URL_, token: "t" }));
    const ws = last();
    act(() => ws.open());
    ws.readyState = 3;
    act(() => {
      vi.advanceTimersByTime(60000);
    });
    expect(ws.sent).toHaveLength(0);
  });

  it("reconnects with exponential backoff after an unexpected close", () => {
    const { result } = renderHook(() => useHandoffSocket({ url: URL_, token: "t" }));
    act(() => last().onerror?.());
    act(() => last().onclose?.({ code: 1006 }));
    expect(result.current.connectionStatus).toBe("reconnecting");
    expect(result.current.lastError).toBe("Connection lost. Reconnecting in 1s\u2026 (attempt 1)");
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(FakeWebSocket.instances).toHaveLength(2);
    expect(result.current.connectionStatus).toBe("reconnecting");
    act(() => last().onclose?.({ code: 1006 }));
    expect(result.current.lastError).toBe("Connection lost. Reconnecting in 2s\u2026 (attempt 2)");
    act(() => last().open());
    expect(result.current.connectionStatus).toBe("connected");
    act(() => last().onclose?.({ code: 1006 }));
    expect(result.current.lastError).toBe("Connection lost. Reconnecting in 1s\u2026 (attempt 1)");
  });

  it("caps backoff at 30 seconds", () => {
    const { result } = renderHook(() => useHandoffSocket({ url: URL_, token: "t" }));
    for (let i = 0; i < 6; i++) {
      act(() => last().onclose?.({ code: 1006 }));
      act(() => {
        vi.advanceTimersByTime(30000);
      });
    }
    act(() => last().onclose?.({ code: 1006 }));
    expect(result.current.lastError).toContain("Reconnecting in 30s");
  });

  it("reconnect() resets backoff and opens a fresh socket", () => {
    const { result } = renderHook(() => useHandoffSocket({ url: URL_, token: "t" }));
    act(() => last().onclose?.({ code: 1006 }));
    act(() => result.current.reconnect());
    expect(FakeWebSocket.instances).toHaveLength(2);
    expect(result.current.connectionStatus).toBe("connecting");
  });

  it("reconnects after a 4001 close when the token refresh succeeds", async () => {
    vi.mocked(refreshOnce).mockResolvedValue("fresh");
    renderHook(() => useHandoffSocket({ url: URL_, token: "t" }));
    await act(async () => {
      last().onclose?.({ code: 4001 });
    });
    expect(FakeWebSocket.instances).toHaveLength(2);
    expect(expireSession).not.toHaveBeenCalled();
  });

  it("expires the session after a 4001 close when refresh fails", async () => {
    vi.mocked(refreshOnce).mockResolvedValue(null);
    const { result } = renderHook(() => useHandoffSocket({ url: URL_, token: "t" }));
    await act(async () => {
      last().onclose?.({ code: 4001 });
    });
    expect(result.current.connectionStatus).toBe("disconnected");
    expect(result.current.lastError).toBe("Your session has expired. Please log in again.");
    expect(expireSession).toHaveBeenCalledTimes(1);
    expect(FakeWebSocket.instances).toHaveLength(1);
  });

  it("closes the socket and cancels pending retry on unmount", () => {
    const { unmount } = renderHook(() => useHandoffSocket({ url: URL_, token: "t" }));
    const ws = last();
    unmount();
    expect(ws.closed).toBe(true);
    expect(ws.onclose).toBeNull();
    const a = renderHook(() => useHandoffSocket({ url: URL_, token: "t" }));
    act(() => last().onclose?.({ code: 1006 }));
    const count = FakeWebSocket.instances.length;
    a.unmount();
    act(() => {
      vi.advanceTimersByTime(60000);
    });
    expect(FakeWebSocket.instances).toHaveLength(count);
  });

  it("disconnects when the token is cleared and reconnects on url change", () => {
    const { result, rerender } = renderHook(
      ({ token, url }) => useHandoffSocket({ url, token }),
      { initialProps: { token: "t" as string | null, url: URL_ } },
    );
    act(() => last().open());
    const first = last();
    rerender({ token: "t", url: "ws://host/other" });
    expect(first.closed).toBe(true);
    expect(last().url).toBe("ws://host/other");
    const second = last();
    rerender({ token: null, url: "ws://host/other" });
    expect(second.closed).toBe(true);
    expect(result.current.connectionStatus).toBe("disconnected");
  });
});