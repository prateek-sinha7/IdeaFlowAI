import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { useConnectorAuthorization } from "./useConnectorAuthorization";
import type { ConnectorSummary } from "@/types/connectors";

const { authorize, disconnect } = vi.hoisted(() => ({ authorize: vi.fn(), disconnect: vi.fn() }));
vi.mock("@/store/api/connectors", () => ({ connectorsApi: { authorize, disconnect } }));

const START = new Date("2026-09-01T10:00:00Z");
const EXPIRES_AT = "2026-09-01T10:10:00Z";
const AUTH_URL = "https://github.com/login/oauth/authorize?state=abc";

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

/** BroadcastChannel stand-in: the test posts messages by hand, nothing crosses a thread. */
class FakeChannel {
  static instances: FakeChannel[] = [];
  onmessage: ((event: MessageEvent<unknown>) => void) | null = null;
  closed = false;
  constructor(public name: string) {
    FakeChannel.instances.push(this);
  }
  close() {
    this.closed = true;
  }
  receive(data: unknown) {
    this.onmessage?.({ data } as MessageEvent<unknown>);
  }
}

function envelopeError(text: string): Error {
  const detail = { error: text, code: "connector_error", recoverable: false };
  return Object.assign(new Error(JSON.stringify(detail)), { status: 409, detail });
}

function fakePopup() {
  return { opener: "original" as unknown, location: { href: "about:blank" }, close: vi.fn() };
}

describe("useConnectorAuthorization", () => {
  let popup: ReturnType<typeof fakePopup>;
  let openSpy: ReturnType<typeof vi.fn>;
  let refresh: Mock<() => Promise<ConnectorSummary[] | null>>;
  let assign: ReturnType<typeof vi.fn>;

  function setup() {
    return renderHook(() => useConnectorAuthorization({ refresh }));
  }

  async function startFlow(result: { current: ReturnType<typeof setup>["result"]["current"] }, key = "github") {
    await act(async () => {
      await result.current.start(key);
    });
  }

  async function tick(ms: number) {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(ms);
    });
  }

  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(START);
    FakeChannel.instances = [];
    vi.stubGlobal("BroadcastChannel", FakeChannel);
    popup = fakePopup();
    openSpy = vi.fn(() => popup);
    vi.stubGlobal("open", openSpy);
    assign = vi.fn();
    vi.stubGlobal("location", { assign });
    refresh = vi.fn<() => Promise<ConnectorSummary[] | null>>().mockResolvedValue([connector("github"), connector("jira")]);
    authorize.mockReset();
    authorize.mockResolvedValue({ authorization_url: AUTH_URL, expires_at: EXPIRES_AT });
    disconnect.mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  describe("start", () => {
    it("opens a named popup, drops its opener and navigates it to the https URL", async () => {
      const { result } = setup();
      await startFlow(result);

      expect(openSpy).toHaveBeenCalledWith("", "flowin-connect-github", "popup,width=600,height=720");
      expect(popup.opener).toBeNull();
      expect(popup.location.href).toBe(AUTH_URL);
      expect(result.current.pending.github).toEqual({
        kind: "authorizing",
        deadline: Date.parse(EXPIRES_AT),
      });
    });

    it("caps the deadline at ten minutes when the server's expiry is later", async () => {
      authorize.mockResolvedValue({ authorization_url: AUTH_URL, expires_at: "2026-09-01T12:00:00Z" });
      const { result } = setup();
      await startFlow(result);
      expect(result.current.pending.github).toEqual({
        kind: "authorizing",
        deadline: START.getTime() + 10 * 60 * 1000,
      });
    });

    it("falls back to a ten-minute deadline when the expiry is not a date", async () => {
      authorize.mockResolvedValue({ authorization_url: AUTH_URL, expires_at: "soon" });
      const { result } = setup();
      await startFlow(result);
      expect(result.current.pending.github).toEqual({
        kind: "authorizing",
        deadline: START.getTime() + 10 * 60 * 1000,
      });
    });

    it.each([
      ["http", "http://github.com/login"],
      ["javascript:", "javascript:alert(1)"],
    ])("closes the popup and reports an error when the URL scheme is %s", async (_label, url) => {
      authorize.mockResolvedValue({ authorization_url: url, expires_at: EXPIRES_AT });
      const { result } = setup();
      await startFlow(result);

      expect(popup.close).toHaveBeenCalledTimes(1);
      expect(popup.location.href).toBe("about:blank");
      expect(result.current.pending).toEqual({});
      expect(result.current.notice).toMatchObject({ kind: "error", connector: "github" });
    });

    it("closes the popup and shows the server message when authorize fails", async () => {
      authorize.mockRejectedValue(new Error("Github is not configured on this server"));
      const { result } = setup();
      await startFlow(result);

      expect(popup.close).toHaveBeenCalledTimes(1);
      expect(result.current.pending).toEqual({});
      expect(result.current.notice).toEqual({
        kind: "error",
        connector: "github",
        reason: null,
        message: "Github is not configured on this server",
      });
    });

    it("shows detail.error, not the raw JSON, when authorize fails with the error envelope", async () => {
      authorize.mockRejectedValue(envelopeError("Github is not configured on this server"));
      const { result } = setup();
      await startFlow(result);

      expect(result.current.notice).toEqual({
        kind: "error",
        connector: "github",
        reason: null,
        message: "Github is not configured on this server",
      });
    });
    it("offers to continue in this tab when the popup is blocked", async () => {
      openSpy.mockReturnValue(null);
      const { result } = setup();
      await startFlow(result);

      expect(result.current.pending).toEqual({});
      expect(result.current.notice).toEqual({
        kind: "popup_blocked",
        connector: "github",
        authorizationUrl: AUTH_URL,
      });

      act(() => result.current.continueInThisTab());
      expect(assign).toHaveBeenCalledWith(AUTH_URL);
    });

    it("does not navigate this tab when no popup_blocked notice is showing", () => {
      const { result } = setup();
      act(() => result.current.continueInThisTab());
      expect(assign).not.toHaveBeenCalled();
    });

    it("ignores a second start for a key that is already authorizing", async () => {
      const { result } = setup();
      await startFlow(result);
      await startFlow(result);
      expect(authorize).toHaveBeenCalledTimes(1);
      expect(openSpy).toHaveBeenCalledTimes(1);
    });
  });

  describe("polling", () => {
    it("does not poll while nothing is pending", async () => {
      setup();
      await tick(10_000);
      expect(refresh).not.toHaveBeenCalled();
    });

    it("finishes with a connected notice when the connector becomes connected", async () => {
      const { result } = setup();
      await startFlow(result);
      refresh.mockClear();
      refresh.mockResolvedValue([
        connector("github", { status: "connected", connected_at: "2026-09-01T10:00:30Z" }),
      ]);

      await tick(2_000);

      expect(refresh).toHaveBeenCalledTimes(1);
      expect(result.current.pending).toEqual({});
      expect(result.current.notice).toEqual({ kind: "connected", connector: "github" });
      expect(popup.close).toHaveBeenCalledTimes(1);
    });

    it("keeps waiting while the status is unchanged", async () => {
      const { result } = setup();
      await startFlow(result);
      await tick(2_000);
      expect(result.current.pending.github).toMatchObject({ kind: "authorizing" });
      expect(result.current.notice).toBeNull();
    });

    it("keeps waiting on a reconnect until the connection is replaced", async () => {
      const before = connector("github", { status: "connected", connected_at: "2026-08-01T09:00:00Z" });
      refresh.mockResolvedValue([before]);
      const { result } = setup();
      await startFlow(result);

      await tick(2_000);
      expect(result.current.pending.github).toMatchObject({ kind: "authorizing" });

      refresh.mockResolvedValue([{ ...before, connected_at: "2026-09-01T10:00:40Z" }]);
      await tick(2_000);
      expect(result.current.pending).toEqual({});
      expect(result.current.notice).toEqual({ kind: "connected", connector: "github" });
    });

    it("keeps waiting when a poll fails", async () => {
      const { result } = setup();
      await startFlow(result);
      refresh.mockResolvedValue(null);
      await tick(2_000);
      expect(result.current.pending.github).toMatchObject({ kind: "authorizing" });
    });

    it("stops with a timed_out notice once the deadline passes", async () => {
      const { result } = setup();
      await startFlow(result);

      await tick(10 * 60 * 1000 + 2_000);

      expect(result.current.pending).toEqual({});
      expect(result.current.notice).toEqual({ kind: "timed_out", connector: "github" });
      expect(popup.close).toHaveBeenCalledTimes(1);

      refresh.mockClear();
      await tick(10_000);
      expect(refresh).not.toHaveBeenCalled();
    });
  });

  describe("cancel", () => {
    it("closes the popup, stops polling and shows a cancelled notice", async () => {
      const { result } = setup();
      await startFlow(result);

      act(() => result.current.cancel("github"));

      expect(popup.close).toHaveBeenCalledTimes(1);
      expect(result.current.pending).toEqual({});
      expect(result.current.notice).toEqual({ kind: "cancelled", connector: "github" });

      refresh.mockClear();
      await tick(10_000);
      expect(refresh).not.toHaveBeenCalled();
    });

    it("does nothing for a key that is not authorizing", () => {
      const { result } = setup();
      act(() => result.current.cancel("jira"));
      expect(result.current.notice).toBeNull();
    });
  });

  describe("BroadcastChannel", () => {
    const message = (overrides: Record<string, unknown> = {}) => ({
      type: "oauth-complete",
      connector: "github",
      result: "connected",
      reason: null,
      ...overrides,
    });

    it("listens on the flowin-connectors channel and closes it on unmount", () => {
      const { unmount } = setup();
      expect(FakeChannel.instances.map((c) => c.name)).toEqual(["flowin-connectors"]);
      unmount();
      expect(FakeChannel.instances[0].closed).toBe(true);
    });

    it("refreshes at once and finishes as connected when the landing page reports success", async () => {
      const { result } = setup();
      await startFlow(result);
      refresh.mockClear();

      await act(async () => {
        FakeChannel.instances[0].receive(message());
        await Promise.resolve();
      });

      expect(refresh).toHaveBeenCalledTimes(1);
      expect(result.current.pending).toEqual({});
      expect(result.current.notice).toEqual({ kind: "connected", connector: "github" });
    });

    it("finishes with the reason when the landing page reports an error", async () => {
      const { result } = setup();
      await startFlow(result);

      await act(async () => {
        FakeChannel.instances[0].receive(message({ result: "error", reason: "access_denied" }));
        await Promise.resolve();
      });

      expect(result.current.pending).toEqual({});
      expect(result.current.notice).toEqual({
        kind: "error",
        connector: "github",
        reason: "access_denied",
        message: null,
      });
    });

    it.each([
      ["a message for a key that is not authorizing", message({ connector: "jira" })],
      ["a malformed message", { type: "oauth-complete", connector: "github" }],
      ["a message with an unlisted reason", message({ result: "error", reason: "<script>" })],
      ["a non-object message", "connected"],
    ])("ignores %s", async (_label, data) => {
      const { result } = setup();
      await startFlow(result);
      refresh.mockClear();

      await act(async () => {
        FakeChannel.instances[0].receive(data);
        await Promise.resolve();
      });

      expect(refresh).not.toHaveBeenCalled();
      expect(result.current.pending.github).toMatchObject({ kind: "authorizing" });
      expect(result.current.notice).toBeNull();
    });
  });

  describe("disconnect", () => {
    it("shows disconnecting, then a disconnected notice with the revocation result, and refreshes", async () => {
      disconnect.mockResolvedValue({ status: "disconnected", provider_revocation: "revoked" });
      const { result } = setup();
      refresh.mockClear();

      let outcome: string | null = null;
      await act(async () => {
        outcome = await result.current.disconnect("jira");
      });

      expect(outcome).toBe("revoked");
      expect(disconnect).toHaveBeenCalledWith("jira");
      expect(refresh).toHaveBeenCalledTimes(1);
      expect(result.current.pending).toEqual({});
      expect(result.current.notice).toEqual({
        kind: "disconnected",
        connector: "jira",
        providerRevocation: "revoked",
      });
    });

    it("marks the key as disconnecting while the request is in flight", async () => {
      let finishRequest!: (value: unknown) => void;
      disconnect.mockReturnValue(new Promise((resolve) => (finishRequest = resolve)));
      const { result } = setup();

      let running!: Promise<unknown>;
      act(() => {
        running = result.current.disconnect("jira");
      });
      expect(result.current.pending.jira).toEqual({ kind: "disconnecting" });

      await act(async () => {
        finishRequest({ status: "disconnected", provider_revocation: "failed" });
        await running;
      });
      expect(result.current.pending).toEqual({});
    });

    it("returns null and reports an error when the request fails", async () => {
      disconnect.mockRejectedValue(new Error("Server error"));
      const { result } = setup();

      let outcome: string | null = "unset";
      await act(async () => {
        outcome = await result.current.disconnect("jira");
      });

      expect(outcome).toBeNull();
      expect(result.current.pending).toEqual({});
      expect(result.current.notice).toEqual({
        kind: "error",
        connector: "jira",
        reason: null,
        message: "Server error",
      });
    });
  });

  it("shows detail.error, not the raw JSON, when disconnect fails with the error envelope", async () => {
    disconnect.mockRejectedValue(envelopeError("Could not reach Jira"));
    const { result } = setup();

    await act(async () => {
      await result.current.disconnect("jira");
    });

    expect(result.current.notice).toEqual({
      kind: "error",
      connector: "jira",
      reason: null,
      message: "Could not reach Jira",
    });
  });
  it("clears the notice on request", async () => {
    const { result } = setup();
    await startFlow(result);
    act(() => result.current.cancel("github"));
    expect(result.current.notice).not.toBeNull();

    act(() => result.current.clearNotice());
    expect(result.current.notice).toBeNull();
  });
});
