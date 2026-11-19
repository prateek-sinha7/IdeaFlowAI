import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, onCapacityRejected, onSessionExpired } from "@/lib/api";
import {
  cancelTurn,
  createSession,
  deleteSession,
  getBuilderModels,
  getSession,
  linkSession,
  listSessions,
  newClientMessageId,
  retryTurn,
  sendMessage,
  undoLastChange,
} from "@/lib/workflowBuilderApi";

const TOKEN = "tok";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("workflowBuilderApi", () => {
  const fetchMock = vi.fn<typeof fetch>();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  function lastCall(): { url: string; init: RequestInit } {
    const [url, init] = fetchMock.mock.calls[fetchMock.mock.calls.length - 1];
    return { url: String(url), init: init ?? {} };
  }

  it("sends the bearer token and returns the parsed body on success", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(200, { models: [], default_model_id: "m", default_efforts: {} }),
    );

    const result = await getBuilderModels(TOKEN);

    const { url, init } = lastCall();
    expect(url).toMatch(/\/api\/workflow-builder\/models$/);
    expect(init.method).toBe("GET");
    expect(new Headers(init.headers).get("Authorization")).toBe(`Bearer ${TOKEN}`);
    expect(result.default_model_id).toBe("m");
  });

  it("posts the create-session body as JSON", async () => {
    fetchMock.mockResolvedValue(jsonResponse(201, { id: "s1" }));

    await createSession(TOKEN, { mode: "edit", workflow_id: "w1", model_id: "m", effort: null });

    const { url, init } = lastCall();
    expect(url).toMatch(/\/api\/workflow-builder\/sessions$/);
    expect(init.method).toBe("POST");
    expect(new Headers(init.headers).get("Content-Type")).toBe("application/json");
    expect(JSON.parse(String(init.body))).toEqual({
      mode: "edit",
      workflow_id: "w1",
      model_id: "m",
      effort: null,
    });
  });

  it("builds the list query from cursor and limit, and omits it when empty", async () => {
    fetchMock.mockImplementation(() =>
      Promise.resolve(jsonResponse(200, { items: [], next_cursor: null })),
    );

    await listSessions(TOKEN, { cursor: "a b", limit: 5 });
    expect(lastCall().url).toMatch(/\/sessions\?cursor=a\+b&limit=5$/);

    await listSessions(TOKEN);
    expect(lastCall().url).toMatch(/\/sessions$/);

    await listSessions(TOKEN, { limit: 5, workflowId: "w 1" });
    expect(lastCall().url).toMatch(/\/sessions\?limit=5&workflow_id=w\+1$/);

    await listSessions(TOKEN, { workflowId: null });
    expect(lastCall().url).toMatch(/\/sessions$/);
  });

  it("encodes ids into the path of every session route", async () => {
    fetchMock.mockImplementation(() => Promise.resolve(jsonResponse(200, {})));

    await getSession(TOKEN, "a/b");
    expect(lastCall().url).toMatch(/\/sessions\/a%2Fb$/);

    await retryTurn(TOKEN, "s1", "t 1");
    expect(lastCall().url).toMatch(/\/sessions\/s1\/turns\/t%201\/retry$/);
    expect(lastCall().init.method).toBe("POST");
    expect(lastCall().init.body).toBeUndefined();

    await undoLastChange(TOKEN, "s1", { expected_revision: 3 });
    expect(lastCall().url).toMatch(/\/sessions\/s1\/undo$/);
    expect(JSON.parse(String(lastCall().init.body))).toEqual({ expected_revision: 3 });

    await linkSession(TOKEN, "s1", { workflow_id: "w9" });
    expect(lastCall().url).toMatch(/\/sessions\/s1\/link$/);
    expect(JSON.parse(String(lastCall().init.body))).toEqual({ workflow_id: "w9" });
  });

  it("resolves void for 204 delete and for cancel", async () => {
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }));
    await expect(deleteSession(TOKEN, "s1")).resolves.toBeUndefined();
    expect(lastCall().init.method).toBe("DELETE");

    fetchMock.mockResolvedValueOnce(new Response(null, { status: 202 }));
    await expect(cancelTurn(TOKEN, "s1", "t1")).resolves.toBeUndefined();
    expect(lastCall().url).toMatch(/\/sessions\/s1\/turns\/t1\/cancel$/);
  });

  describe("sendMessage", () => {
    const message = {
      content: "hi",
      model_id: "m",
      effort: null,
      canvas_state: { steps: [] },
    };

    it("generates a client_message_id the server pattern accepts", async () => {
      fetchMock.mockImplementation(() =>
        Promise.resolve(jsonResponse(202, { turn_id: "t", message_id: "m", replayed: false })),
      );

      await sendMessage(TOKEN, "s1", message);
      const first = JSON.parse(String(lastCall().init.body)) as { client_message_id: string };
      await sendMessage(TOKEN, "s1", message);
      const second = JSON.parse(String(lastCall().init.body)) as { client_message_id: string };

      expect(first.client_message_id).toMatch(/^[A-Za-z0-9_-]{8,64}$/);
      expect(second.client_message_id).not.toBe(first.client_message_id);
      expect(newClientMessageId()).toMatch(/^[A-Za-z0-9_-]{8,64}$/);
    });

    it("reuses a supplied client_message_id when re-sending", async () => {
      fetchMock.mockResolvedValue(
        jsonResponse(202, { turn_id: "t", message_id: "m", replayed: true }),
      );

      await sendMessage(TOKEN, "s1", message, "fixed-id-1234");

      expect(JSON.parse(String(lastCall().init.body))).toEqual({
        ...message,
        client_message_id: "fixed-id-1234",
      });
    });
  });

  describe("errors", () => {
    it("throws ApiError carrying status and detail", async () => {
      fetchMock.mockResolvedValue(
        jsonResponse(409, { detail: { code: "turn_running", error: "busy" } }),
      );

      const err = await getSession(TOKEN, "s1").catch((e: unknown) => e);

      expect(err).toBeInstanceOf(ApiError);
      expect((err as ApiError).status).toBe(409);
      expect((err as ApiError).detail).toEqual({ code: "turn_running", error: "busy" });
    });

    it("falls back to the status text when the error body is not JSON", async () => {
      fetchMock.mockResolvedValue(new Response("<html>", { status: 502, statusText: "Bad Gateway" }));

      const err = await getSession(TOKEN, "s1").catch((e: unknown) => e);

      expect(err).toBeInstanceOf(ApiError);
      expect((err as ApiError).status).toBe(502);
      expect((err as ApiError).detail).toBe("Bad Gateway");
    });

    it("turns a 30 s timeout into ApiError(0)", async () => {
      vi.useFakeTimers();
      try {
        fetchMock.mockImplementation(
          (_url, options) =>
            new Promise<Response>((_resolve, reject) => {
              options?.signal?.addEventListener("abort", () =>
                reject(new DOMException("aborted", "AbortError")),
              );
            }),
        );

        const pending = getSession(TOKEN, "s1").catch((e: unknown) => e);
        await vi.advanceTimersByTimeAsync(30_000);
        const err = await pending;

        expect(err).toBeInstanceOf(ApiError);
        expect((err as ApiError).status).toBe(0);
      } finally {
        vi.useRealTimers();
      }
    });

    it("notifies capacity listeners on a 503 host_capacity_exhausted", async () => {
      const detail = {
        error: "busy",
        code: "host_capacity_exhausted",
        recoverable: true,
        retry_after_seconds: 5,
        signals: [],
      };
      fetchMock.mockResolvedValue(jsonResponse(503, { detail }));
      const listener = vi.fn();
      const off = onCapacityRejected(listener);

      await expect(sendMessage(TOKEN, "s1", {
        content: "hi",
        model_id: "m",
        effort: null,
        canvas_state: { steps: [] },
      })).rejects.toBeInstanceOf(ApiError);

      off();
      expect(listener).toHaveBeenCalledWith(detail);
    });

    it("signals session expiry on a 401", async () => {
      fetchMock.mockResolvedValue(jsonResponse(401, { detail: "Not authenticated" }));
      const listener = vi.fn();
      const off = onSessionExpired(listener);

      const err = await getBuilderModels(TOKEN).catch((e: unknown) => e);

      off();
      expect(err).toBeInstanceOf(ApiError);
      expect((err as ApiError).status).toBe(401);
      expect(listener).toHaveBeenCalled();
    });
  });
});
