import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import {
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
