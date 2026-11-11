import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { useConnectors } from "./useConnectors";
import type { ConnectorSummary } from "@/types/connectors";

const { list } = vi.hoisted(() => ({ list: vi.fn() }));
vi.mock("@/store/api/connectors", () => ({ connectorsApi: { list } }));

function connector(key: string, overrides: Partial<ConnectorSummary> = {}): ConnectorSummary {
  return {
    key,
    display_name: key,
    description: "",
    icon: key,
    docs_url: "https://example.test",
    mode: "remote_mcp",
    status: "not_connected",
    account: null,
    requested_scopes: [],
    granted_scopes: [],
    sites: [],
    connected_at: null,
    last_refreshed_at: null,
    ...overrides,
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function envelopeError(text: string): Error {
  const detail = { error: text, code: "connector_error", recoverable: false };
  return Object.assign(new Error(JSON.stringify(detail)), { status: 409, detail });
}
describe("useConnectors", () => {
  beforeEach(() => {
    list.mockReset();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("stays loading and sends no request when there is no token", () => {
    const { result } = renderHook(() => useConnectors(null));
    expect(result.current.state).toEqual({ status: "loading" });
    expect(list).not.toHaveBeenCalled();
  });

  it("becomes ready with the connectors when the request succeeds", async () => {
    const github = connector("github");
    list.mockResolvedValue({ connectors: [github] });
    const { result } = renderHook(() => useConnectors("t"));
    await waitFor(() => expect(result.current.state).toEqual({ status: "ready", connectors: [github] }));
  });

  it("becomes empty when the server returns no connectors", async () => {
    list.mockResolvedValue({ connectors: [] });
    const { result } = renderHook(() => useConnectors("t"));
    await waitFor(() => expect(result.current.state).toEqual({ status: "empty" }));
  });

  it("becomes error with the failure message when the request rejects", async () => {
    list.mockRejectedValue(new Error("Service unavailable"));
    const { result } = renderHook(() => useConnectors("t"));
    await waitFor(() =>
      expect(result.current.state).toEqual({ status: "error", message: "Service unavailable" }),
    );
  });

  it("shows detail.error, not the raw JSON, when the server sends the error envelope", async () => {
    list.mockRejectedValue(envelopeError("Connectors are unavailable"));
    const { result } = renderHook(() => useConnectors("t"));
    await waitFor(() =>
      expect(result.current.state).toEqual({ status: "error", message: "Connectors are unavailable" }),
    );
  });

  it("uses a generic message when the rejection is not an Error", async () => {
    list.mockRejectedValue("nope");
    const { result } = renderHook(() => useConnectors("t"));
    await waitFor(() =>
      expect(result.current.state).toEqual({ status: "error", message: "Failed to load connectors" }),
    );
  });

  it("shows loading again and then ready when refresh is called from the error state", async () => {
    list.mockRejectedValueOnce(new Error("down"));
    const { result } = renderHook(() => useConnectors("t"));
    await waitFor(() => expect(result.current.state.status).toBe("error"));

    const retry = deferred<{ connectors: ConnectorSummary[] }>();
    list.mockReturnValueOnce(retry.promise);
    let refreshed: Promise<ConnectorSummary[] | null> | undefined;
    act(() => {
      refreshed = result.current.refresh();
    });
    expect(result.current.state).toEqual({ status: "loading" });

    const github = connector("github");
    await act(async () => {
      retry.resolve({ connectors: [github] });
      await refreshed;
    });
    expect(result.current.state).toEqual({ status: "ready", connectors: [github] });
  });

  it("returns the fresh connectors from refresh", async () => {
    list.mockResolvedValueOnce({ connectors: [connector("github")] });
    const { result } = renderHook(() => useConnectors("t"));
    await waitFor(() => expect(result.current.state.status).toBe("ready"));

    const jira = connector("jira", { status: "connected" });
    list.mockResolvedValueOnce({ connectors: [jira] });
    let returned: ConnectorSummary[] | null = null;
    await act(async () => {
      returned = await result.current.refresh();
    });
    expect(returned).toEqual([jira]);
  });

  it("keeps the connectors on screen and returns null when a later refresh fails", async () => {
    const github = connector("github");
    list.mockResolvedValueOnce({ connectors: [github] });
    const { result } = renderHook(() => useConnectors("t"));
    await waitFor(() => expect(result.current.state.status).toBe("ready"));

    list.mockRejectedValueOnce(new Error("blip"));
    let returned: ConnectorSummary[] | null = [];
    await act(async () => {
      returned = await result.current.refresh();
    });
    expect(returned).toBeNull();
    expect(result.current.state).toEqual({ status: "ready", connectors: [github] });
  });

  it("ignores a slow earlier response that arrives after a newer one", async () => {
    const first = deferred<{ connectors: ConnectorSummary[] }>();
    list.mockReturnValueOnce(first.promise);
    const { result } = renderHook(() => useConnectors("t"));

    const newer = connector("jira", { status: "connected" });
    list.mockResolvedValueOnce({ connectors: [newer] });
    await act(async () => {
      await result.current.refresh();
    });
    expect(result.current.state).toEqual({ status: "ready", connectors: [newer] });

    await act(async () => {
      first.resolve({ connectors: [connector("github")] });
      await first.promise;
    });
    expect(result.current.state).toEqual({ status: "ready", connectors: [newer] });
  });

  it("refetches when the window regains focus", async () => {
    list.mockResolvedValue({ connectors: [connector("github")] });
    const { result } = renderHook(() => useConnectors("t"));
    await waitFor(() => expect(result.current.state.status).toBe("ready"));
    expect(list).toHaveBeenCalledTimes(1);

    await act(async () => {
      window.dispatchEvent(new Event("focus"));
    });
    await waitFor(() => expect(list).toHaveBeenCalledTimes(2));
  });

  it("stops listening for focus after unmount", async () => {
    list.mockResolvedValue({ connectors: [connector("github")] });
    const { result, unmount } = renderHook(() => useConnectors("t"));
    await waitFor(() => expect(result.current.state.status).toBe("ready"));
    unmount();

    window.dispatchEvent(new Event("focus"));
    expect(list).toHaveBeenCalledTimes(1);
  });

  it("drops a response that lands after unmount", async () => {
    const pending = deferred<{ connectors: ConnectorSummary[] }>();
    list.mockReturnValueOnce(pending.promise);
    const { result, unmount } = renderHook(() => useConnectors("t"));
    unmount();
    pending.resolve({ connectors: [connector("github")] });
    await pending.promise;
    expect(result.current.state).toEqual({ status: "loading" });
  });

  it("resets to loading and refetches when the token changes", async () => {
    list.mockResolvedValueOnce({ connectors: [connector("github")] });
    const { result, rerender } = renderHook(({ token }) => useConnectors(token), {
      initialProps: { token: "a" },
    });
    await waitFor(() => expect(result.current.state.status).toBe("ready"));

    const next = deferred<{ connectors: ConnectorSummary[] }>();
    list.mockReturnValueOnce(next.promise);
    rerender({ token: "b" });
    await waitFor(() => expect(result.current.state).toEqual({ status: "loading" }));
    expect(list).toHaveBeenCalledTimes(2);

    await act(async () => {
      next.resolve({ connectors: [] });
      await next.promise;
    });
    expect(result.current.state).toEqual({ status: "empty" });
  });
});
