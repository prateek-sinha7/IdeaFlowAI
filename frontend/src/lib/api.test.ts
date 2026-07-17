import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { getRunEvents } from "@/lib/api";

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
