import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import type { ConnectorToolsResponse } from "@/types/connectors";
import { buildConnector, buildConnectedConnector } from "@/test/connectorFixtures";

// Boundary: the Connectors REST client. The hook's own cache logic runs for real.
const mockList = vi.fn();
const mockTools = vi.fn();
vi.mock("@/store/api/connectors", () => ({
  connectorsApi: {
    list: (...a: unknown[]) => mockList(...a),
    tools: (...a: unknown[]) => mockTools(...a),
  },
}));

import {
  useConnectedApps,
  resetConnectedAppsCache,
  CONNECTED_APPS_CACHE_TTL_MS,
} from "./useConnectedApps";

const GITHUB = buildConnectedConnector({ key: "github", display_name: "GitHub" });
const JIRA = buildConnector({ key: "jira", display_name: "Jira", status: "not_connected" });

function toolsResponse(overrides: Partial<ConnectorToolsResponse> = {}): ConnectorToolsResponse {
  return {
    connector: "github",
    status: "connected",
    listed_at: "2026-09-01T12:00:00Z",
    tools: [
      {
        name: "github__get_issue",
        source_name: "get_issue",
        title: "Get issue",
        description: "Read one issue.",
        write_capable: false,
      },
    ],
    ...overrides,
  };
}

function envelopeError(text: string): Error {
  const detail = { error: text, code: "connector_error", recoverable: false };
  return Object.assign(new Error(JSON.stringify(detail)), { status: 409, detail });
}
beforeEach(() => {
  vi.clearAllMocks();
  resetConnectedAppsCache();
  mockList.mockResolvedValue({ connectors: [GITHUB, JIRA] });
  mockTools.mockResolvedValue(toolsResponse());
});

afterEach(() => {
  vi.useRealTimers();
});

describe("useConnectedApps - connector list", () => {
  it("starts loading then becomes ready with the connectors", async () => {
    const { result } = renderHook(() => useConnectedApps("tok"));

    expect(result.current.state).toEqual({ status: "loading" });
    await waitFor(() => expect(result.current.state.status).toBe("ready"));

    expect(result.current.state).toEqual({ status: "ready", connectors: [GITHUB, JIRA] });
  });

  it("makes no request when there is no token", () => {
    const { result } = renderHook(() => useConnectedApps(null));

    expect(result.current.state).toEqual({ status: "loading" });
    expect(mockList).not.toHaveBeenCalled();
  });

  it("shows an error, then loads on Retry", async () => {
    mockList.mockRejectedValueOnce(new Error("boom"));
    const { result } = renderHook(() => useConnectedApps("tok"));
    await waitFor(() => expect(result.current.state).toEqual({ status: "error", message: "boom" }));

    act(() => result.current.retry());

    expect(result.current.state).toEqual({ status: "loading" });
    await waitFor(() => expect(result.current.state.status).toBe("ready"));
    expect(mockList).toHaveBeenCalledTimes(2);
  });

  it("shows detail.error, not the raw JSON, when the list fails with the error envelope", async () => {
    mockList.mockRejectedValueOnce(envelopeError("Connected apps are unavailable"));
    const { result } = renderHook(() => useConnectedApps("tok"));

    await waitFor(() =>
      expect(result.current.state).toEqual({ status: "error", message: "Connected apps are unavailable" }),
    );
  });

  it("shows detail.error, not the raw JSON, when the tools call fails with the error envelope", async () => {
    mockTools.mockRejectedValueOnce(envelopeError("Github is not configured on this server"));
    const { result } = renderHook(() => useConnectedApps("tok"));
    await waitFor(() => expect(result.current.state.status).toBe("ready"));

    act(() => result.current.loadTools("github"));

    await waitFor(() =>
      expect(result.current.toolsFor("github")).toEqual({
        status: "error",
        message: "Github is not configured on this server",
      }),
    );
  });

  it("uses a generic message when the failure carries none", async () => {
    mockList.mockRejectedValueOnce("nope");
    const { result } = renderHook(() => useConnectedApps("tok"));

    await waitFor(() => expect(result.current.state.status).toBe("error"));

    expect(result.current.state).toEqual({
      status: "error",
      message: "Connected apps could not be loaded.",
    });
  });

  it("serves a second mount from the cache without another request", async () => {
    const first = renderHook(() => useConnectedApps("tok"));
    await waitFor(() => expect(first.result.current.state.status).toBe("ready"));
    first.unmount();

    const second = renderHook(() => useConnectedApps("tok"));

    expect(second.result.current.state.status).toBe("ready");
    expect(mockList).toHaveBeenCalledTimes(1);
  });

  it("asks the server again once the cached list is older than the TTL", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    const first = renderHook(() => useConnectedApps("tok"));
    await waitFor(() => expect(first.result.current.state.status).toBe("ready"));
    first.unmount();

    vi.setSystemTime(Date.now() + CONNECTED_APPS_CACHE_TTL_MS + 1);
    const second = renderHook(() => useConnectedApps("tok"));

    expect(second.result.current.state).toEqual({ status: "loading" });
    await waitFor(() => expect(second.result.current.state.status).toBe("ready"));
    expect(mockList).toHaveBeenCalledTimes(2);
  });

  it("goes back to loading and refetches when the token changes", async () => {
    const { result, rerender } = renderHook(({ token }) => useConnectedApps(token), {
      initialProps: { token: "tok-a" as string | null },
    });
    await waitFor(() => expect(result.current.state.status).toBe("ready"));

    mockList.mockResolvedValueOnce({ connectors: [JIRA] });
    rerender({ token: "tok-b" });

    expect(result.current.state).toEqual({ status: "loading" });
    await waitFor(() =>
      expect(result.current.state).toEqual({ status: "ready", connectors: [JIRA] }),
    );
    expect(mockList).toHaveBeenCalledTimes(2);
  });

  it("refetches on window focus", async () => {
    const { result } = renderHook(() => useConnectedApps("tok"));
    await waitFor(() => expect(result.current.state.status).toBe("ready"));

    mockList.mockResolvedValueOnce({ connectors: [JIRA] });
    act(() => {
      window.dispatchEvent(new Event("focus"));
    });

    await waitFor(() =>
      expect(result.current.state).toEqual({ status: "ready", connectors: [JIRA] }),
    );
  });

  it("keeps the list on screen when a focus refresh fails", async () => {
    const { result } = renderHook(() => useConnectedApps("tok"));
    await waitFor(() => expect(result.current.state.status).toBe("ready"));

    mockList.mockRejectedValueOnce(new Error("offline"));
    act(() => {
      window.dispatchEvent(new Event("focus"));
    });
    await waitFor(() => expect(mockList).toHaveBeenCalledTimes(2));

    expect(result.current.state).toEqual({ status: "ready", connectors: [GITHUB, JIRA] });
  });

  it("stops listening for focus after unmount", async () => {
    const { result, unmount } = renderHook(() => useConnectedApps("tok"));
    await waitFor(() => expect(result.current.state.status).toBe("ready"));
    unmount();

    window.dispatchEvent(new Event("focus"));

    expect(mockList).toHaveBeenCalledTimes(1);
  });

  it("ignores a slow response for a token that has been replaced", async () => {
    let releaseFirst: (v: unknown) => void = () => {};
    mockList.mockReturnValueOnce(new Promise((resolve) => (releaseFirst = resolve)));
    const { result, rerender } = renderHook(({ token }) => useConnectedApps(token), {
      initialProps: { token: "tok-a" as string | null },
    });

    // The token changes while the first request is still open.
    mockList.mockResolvedValueOnce({ connectors: [JIRA] });
    rerender({ token: "tok-b" });
    await waitFor(() =>
      expect(result.current.state).toEqual({ status: "ready", connectors: [JIRA] }),
    );

    await act(async () => {
      releaseFirst({ connectors: [GITHUB] });
    });

    expect(result.current.state).toEqual({ status: "ready", connectors: [JIRA] });
  });
});

describe("useConnectedApps - tools", () => {
  it("reports idle until a connector's tools are requested", async () => {
    const { result } = renderHook(() => useConnectedApps("tok"));
    await waitFor(() => expect(result.current.state.status).toBe("ready"));

    expect(result.current.toolsFor("github")).toEqual({ status: "idle" });
    expect(mockTools).not.toHaveBeenCalled();
  });

  it("loads a connector's tools: loading, then ready", async () => {
    const { result } = renderHook(() => useConnectedApps("tok"));
    await waitFor(() => expect(result.current.state.status).toBe("ready"));

    act(() => result.current.loadTools("github"));

    expect(result.current.toolsFor("github")).toEqual({ status: "loading" });
    await waitFor(() => expect(result.current.toolsFor("github").status).toBe("ready"));
    expect(result.current.toolsFor("github")).toEqual({
      status: "ready",
      connection: "connected",
      tools: toolsResponse().tools,
    });
    expect(mockTools).toHaveBeenCalledWith("github");
  });

  it("reports an error, then loads again when forced", async () => {
    mockTools.mockRejectedValueOnce(new Error("bad gateway"));
    const { result } = renderHook(() => useConnectedApps("tok"));
    await waitFor(() => expect(result.current.state.status).toBe("ready"));

    act(() => result.current.loadTools("github"));
    await waitFor(() =>
      expect(result.current.toolsFor("github")).toEqual({ status: "error", message: "bad gateway" }),
    );

    act(() => result.current.loadTools("github", true));
    await waitFor(() => expect(result.current.toolsFor("github").status).toBe("ready"));
    expect(mockTools).toHaveBeenCalledTimes(2);
  });

  it("serves tools from the cache on a second request within the TTL", async () => {
    const { result } = renderHook(() => useConnectedApps("tok"));
    await waitFor(() => expect(result.current.state.status).toBe("ready"));
    act(() => result.current.loadTools("github"));
    await waitFor(() => expect(result.current.toolsFor("github").status).toBe("ready"));

    act(() => result.current.loadTools("github"));

    expect(result.current.toolsFor("github").status).toBe("ready");
    expect(mockTools).toHaveBeenCalledTimes(1);
  });

  it("shares one request between two callers that ask at the same time", async () => {
    const first = renderHook(() => useConnectedApps("tok"));
    const second = renderHook(() => useConnectedApps("tok"));
    await waitFor(() => expect(first.result.current.state.status).toBe("ready"));
    await waitFor(() => expect(second.result.current.state.status).toBe("ready"));

    act(() => {
      first.result.current.loadTools("github");
      second.result.current.loadTools("github");
    });

    await waitFor(() => expect(second.result.current.toolsFor("github").status).toBe("ready"));
    expect(mockTools).toHaveBeenCalledTimes(1);
  });

  it("drops a connector's cached tools when its status changes", async () => {
    const { result } = renderHook(() => useConnectedApps("tok"));
    await waitFor(() => expect(result.current.state.status).toBe("ready"));
    act(() => result.current.loadTools("github"));
    await waitFor(() => expect(result.current.toolsFor("github").status).toBe("ready"));

    // GitHub expired in the meantime; the focus refresh sees the new status.
    mockList.mockResolvedValueOnce({
      connectors: [buildConnectedConnector({ key: "github", status: "expired" }), JIRA],
    });
    act(() => {
      window.dispatchEvent(new Event("focus"));
    });
    await waitFor(() => expect(mockList).toHaveBeenCalledTimes(2));
    await waitFor(() => {
      const state = result.current.state;
      expect(state.status === "ready" && state.connectors[0].status).toBe("expired");
    });

    act(() => result.current.loadTools("github"));

    expect(mockTools).toHaveBeenCalledTimes(2);
  });

  it("forgets tool states when the token changes", async () => {
    const { result, rerender } = renderHook(({ token }) => useConnectedApps(token), {
      initialProps: { token: "tok-a" as string | null },
    });
    await waitFor(() => expect(result.current.state.status).toBe("ready"));
    act(() => result.current.loadTools("github"));
    await waitFor(() => expect(result.current.toolsFor("github").status).toBe("ready"));

    rerender({ token: "tok-b" });

    expect(result.current.toolsFor("github")).toEqual({ status: "idle" });
  });

  it("does not update after unmount when tools arrive late", async () => {
    let release: (v: unknown) => void = () => {};
    mockTools.mockReturnValueOnce(new Promise((resolve) => (release = resolve)));
    const errors = vi.spyOn(console, "error").mockImplementation(() => {});
    const { result, unmount } = renderHook(() => useConnectedApps("tok"));
    await waitFor(() => expect(result.current.state.status).toBe("ready"));
    act(() => result.current.loadTools("github"));
    unmount();

    await act(async () => {
      release(toolsResponse());
    });

    expect(errors).not.toHaveBeenCalled();
    errors.mockRestore();
  });
});
