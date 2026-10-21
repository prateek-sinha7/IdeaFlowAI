import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import {
  adminGetCapacityHistory,
  adminListCapacity,
  getRunEvents,
  onCapacityRejected,
  type CapacityRejectionDetail,
} from "@/lib/api";

// ─────────────────────────────────────────────────────────────────
// BUG-018 Part A — getRunEvents must merge the durable row's authoritative
// `event_id` + `seq` COLUMNS into the mapped frame's `data`. The durable
// Concierge `chat_reply` row carries a DISTINCT event_id COLUMN
// ("chat-reply:{message_id}") but its payload_json has NO event_id — only a
// message_id IDENTICAL to the paired user turn's. If getRunEvents drops the
// column, the reply keys on message_id downstream and OVERWRITES the user's
// question bubble (BUG-018). Driven through the global fetch that api.ts's
// request() calls (clones the api.getRunArtifacts.test.ts fetch-mock idiom).
// ─────────────────────────────────────────────────────────────────

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function okJson(body: unknown) {
  return { ok: true, json: async () => body };
}

describe("getRunEvents — durable row mapping (BUG-018 Part A)", () => {
  it("merges the row's event_id + seq COLUMNS into data (column wins over payload)", async () => {
    // A durable Concierge reply row: the event_id lives in the COLUMN, NOT in
    // payload_json (which only has message_id === the user turn's id).
    const wire = {
      workflow_id: "run-1",
      after: 0,
      events: [
        {
          seq: 7,
          event_id: "chat-reply:X",
          type: "chat_reply",
          payload_json: { message_id: "X", text: "A" },
        },
      ],
    };
    fetchMock.mockResolvedValue(okJson(wire));

    const frames = await getRunEvents("t.t.t", "run-1", 0);

    expect(frames).toHaveLength(1);
    const frame = frames[0];
    expect(frame.type).toBe("chat_reply");
    // The authoritative COLUMN values reach the consumer.
    expect(frame.data.event_id).toBe("chat-reply:X");
    expect(frame.data.seq).toBe(7);
    // The payload is preserved.
    expect(frame.data.message_id).toBe("X");
    expect(frame.data.text).toBe("A");
  });

  it("the column value wins when payload_json carries a same-named key", async () => {
    const wire = {
      workflow_id: "run-1",
      after: 0,
      events: [
        {
          seq: 9,
          event_id: "col-authoritative",
          type: "chat_message",
          payload_json: { event_id: "payload-stale", seq: 1, message_id: "m" },
        },
      ],
    };
    fetchMock.mockResolvedValue(okJson(wire));

    const [frame] = await getRunEvents("t.t.t", "run-1", 0);

    expect(frame.data.event_id).toBe("col-authoritative");
    expect(frame.data.seq).toBe(9);
  });
});

// ─────────────────────────────────────────────────────────────────
// ISS-1155 (QA-KB-119) — GET /api/runs/{id}/events returns one bounded page
// plus `has_more` / `next_after`. getRunEvents must still hand every caller
// the WHOLE log, by following the cursor, and must stop on an envelope with
// no `has_more` (an old backend, the mock catch-all `{}`).
// ─────────────────────────────────────────────────────────────────

describe("getRunEvents — follows the events cursor (ISS-1155)", () => {
  const row = (seq: number) => ({
    seq,
    event_id: `e${seq}`,
    type: "agent_chunk",
    payload_json: {},
  });

  it("concatenates every page in order until has_more is false", async () => {
    fetchMock
      .mockResolvedValueOnce(
        okJson({ workflow_id: "run-1", after: 0, events: [row(1), row(2)], has_more: true, next_after: 2 }),
      )
      .mockResolvedValueOnce(
        okJson({ workflow_id: "run-1", after: 2, events: [row(3)], has_more: false, next_after: 3 }),
      );

    const frames = await getRunEvents("t.t.t", "run-1", 0);

    expect(frames.map((f) => f.data.seq)).toEqual([1, 2, 3]);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(String(fetchMock.mock.calls[1][0])).toContain("after=2");
  });

  it("stops after one request when the envelope carries no has_more", async () => {
    fetchMock.mockResolvedValue(okJson({ workflow_id: "run-1", after: 0, events: [row(1)] }));

    const frames = await getRunEvents("t.t.t", "run-1", 0);

    expect(frames).toHaveLength(1);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("returns [] for the mock catch-all {}", async () => {
    fetchMock.mockResolvedValue(okJson({}));

    expect(await getRunEvents("t.t.t", "run-1", 0)).toEqual([]);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

// ─────────────────────────────────────────────────────────────────
// specs/014 — the ApiError-constructor notification seam. Every 503
// host_capacity_exhausted rejection, from ANY call site that throws an
// ApiError (request()'s own throw, or a bespoke fetch+throw site like
// postResume/adminDeleteUser), must reach every onCapacityRejected
// subscriber exactly once, synchronously, with the typed detail.
// ─────────────────────────────────────────────────────────────────

function capacityRejectionBody(overrides: Partial<CapacityRejectionDetail> = {}) {
  return {
    detail: {
      error: "The service is busy right now. Please try again in a few minutes.",
      code: "host_capacity_exhausted",
      recoverable: true,
      retry_after_seconds: 120,
      signals: [{ name: "cpu", value: 91.0, threshold: 75.0 }],
      ...overrides,
    },
  };
}

function serviceUnavailable(body: unknown) {
  return { ok: false, status: 503, json: async () => body };
}

describe("onCapacityRejected — the ApiError-constructor notification seam", () => {
  it("fires when a request() call throws a 503 host_capacity_exhausted ApiError", async () => {
    fetchMock.mockResolvedValue(serviceUnavailable(capacityRejectionBody()));

    const received: CapacityRejectionDetail[] = [];
    const unsubscribe = onCapacityRejected((detail) => received.push(detail));

    await expect(adminListCapacity("tok")).rejects.toThrow();

    expect(received).toHaveLength(1);
    expect(received[0].code).toBe("host_capacity_exhausted");
    expect(received[0].retry_after_seconds).toBe(120);
    expect(received[0].signals).toEqual([
      { name: "cpu", value: 91.0, threshold: 75.0 },
    ]);

    unsubscribe();
  });

  it("does NOT fire for a non-503 ApiError (e.g. a 403 admin-guard rejection)", async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 403,
      json: async () => ({ detail: "Admin access required." }),
    });

    const received: CapacityRejectionDetail[] = [];
    const unsubscribe = onCapacityRejected((detail) => received.push(detail));

    await expect(adminListCapacity("tok")).rejects.toThrow();

    expect(received).toHaveLength(0);
    unsubscribe();
  });

  it("does NOT fire for a 503 whose detail lacks the host_capacity_exhausted code", async () => {
    fetchMock.mockResolvedValue(
      serviceUnavailable({ detail: { error: "some other 503" } }),
    );

    const received: CapacityRejectionDetail[] = [];
    const unsubscribe = onCapacityRejected((detail) => received.push(detail));

    await expect(adminListCapacity("tok")).rejects.toThrow();

    expect(received).toHaveLength(0);
    unsubscribe();
  });

  it("unsubscribe stops further notifications", async () => {
    fetchMock.mockResolvedValue(serviceUnavailable(capacityRejectionBody()));

    const received: CapacityRejectionDetail[] = [];
    const unsubscribe = onCapacityRejected((detail) => received.push(detail));
    unsubscribe();

    await expect(adminListCapacity("tok")).rejects.toThrow();

    expect(received).toHaveLength(0);
  });

  it("multiple subscribers each receive the rejection independently", async () => {
    fetchMock.mockResolvedValue(serviceUnavailable(capacityRejectionBody()));

    const a: CapacityRejectionDetail[] = [];
    const b: CapacityRejectionDetail[] = [];
    const unsubA = onCapacityRejected((detail) => a.push(detail));
    const unsubB = onCapacityRejected((detail) => b.push(detail));

    await expect(adminListCapacity("tok")).rejects.toThrow();

    expect(a).toHaveLength(1);
    expect(b).toHaveLength(1);

    unsubA();
    unsubB();
  });

  it("a throwing subscriber does not prevent the ApiError from propagating, nor break other subscribers", async () => {
    fetchMock.mockResolvedValue(serviceUnavailable(capacityRejectionBody()));

    const received: CapacityRejectionDetail[] = [];
    const unsubBad = onCapacityRejected(() => {
      throw new Error("a buggy subscriber");
    });
    const unsubGood = onCapacityRejected((detail) => received.push(detail));

    await expect(adminListCapacity("tok")).rejects.toThrow();

    expect(received).toHaveLength(1);
    unsubBad();
    unsubGood();
  });
});

describe("adminListCapacity", () => {
  it("GETs /api/admin/capacity with the bearer token and returns the parsed matrix", async () => {
    const matrix = {
      collected_at: "2026-09-08T00:00:00Z",
      self_instance_id: "i-abc",
      instance_source: "discovery",
      instances: [],
      gate: {
        enabled: false,
        state: "blind",
        blind_reason: "no capacity data collected yet",
        cpu_threshold_percent: 75,
        mem_threshold_percent: 75,
        signals: [],
        engaged_at: null,
        evaluated_at: "2026-09-08T00:00:00Z",
      },
    };
    fetchMock.mockResolvedValue({ ok: true, json: async () => matrix });

    const result = await adminListCapacity("tok");

    expect(result).toEqual(matrix);
    const [url, options] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/api/admin/capacity");
    expect(options.method).toBe("GET");
    expect((options.headers as Record<string, string>).Authorization).toBe(
      "Bearer tok",
    );
  });

  it("propagates a 403 as an ApiError when the caller is not an admin", async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 403,
      json: async () => ({ detail: "Admin access required." }),
    });

    await expect(adminListCapacity("tok")).rejects.toMatchObject({
      status: 403,
    });
  });
});

describe("adminGetCapacityHistory", () => {
  it("GETs /api/admin/capacity/history with instance_id and range, omitting period when null", async () => {
    const history = { instance_id: "i-abc", range: "3h", series: [] };
    fetchMock.mockResolvedValue(okJson(history));

    const result = await adminGetCapacityHistory("tok", "i-abc", "3h", null);

    expect(result).toEqual(history);
    const [url, options] = fetchMock.mock.calls[0];
    const parsed = new URL(String(url), "http://localhost");
    expect(parsed.pathname).toBe("/api/admin/capacity/history");
    expect(parsed.searchParams.get("instance_id")).toBe("i-abc");
    expect(parsed.searchParams.get("range")).toBe("3h");
    expect(parsed.searchParams.has("period")).toBe(false);
    expect(options.method).toBe("GET");
    expect((options.headers as Record<string, string>).Authorization).toBe("Bearer tok");
  });

  it("sends the period and URL-encodes the instance id when given", async () => {
    fetchMock.mockResolvedValue(okJson({}));

    await adminGetCapacityHistory("tok", "i-a&b=c", "15d", 60);

    const parsed = new URL(String(fetchMock.mock.calls[0][0]), "http://localhost");
    expect(parsed.searchParams.get("instance_id")).toBe("i-a&b=c");
    expect(parsed.searchParams.get("period")).toBe("60");
  });

  it("propagates a 422 as an ApiError when the backend rejects the period", async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 422,
      json: async () => ({ detail: "Period 60s is not available for range 30d" }),
    });

    await expect(adminGetCapacityHistory("tok", "i-abc", "30d", 60)).rejects.toMatchObject({
      status: 422,
    });
  });
});
