import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  CHAT_EVENT_TYPES,
  STREAM_DELTA_EVENT_TYPES,
  getRunEvents,
  type DurableFrame,
} from "./api";

// ─────────────────────────────────────────────────────────────────
// Finished-run perf — getRunEvents forwards the server-side `/events` type
// filter (`types` allow-list / `exclude_types` deny-list) on EVERY page URL,
// so the filtered cursor walk stays filtered past page 1. With no filter the
// URL is byte-identical to the unfiltered call. Driven through the global
// fetch that api.ts's request() calls (the api.test.ts fetch-mock idiom).
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

const row = (seq: number, type = "agent_start") => ({
  seq,
  event_id: `e${seq}`,
  type,
  payload_json: {},
});

function twoPages() {
  fetchMock
    .mockResolvedValueOnce(
      okJson({ workflow_id: "run-1", after: 0, events: [row(1), row(2)], has_more: true, next_after: 2 }),
    )
    .mockResolvedValueOnce(
      okJson({ workflow_id: "run-1", after: 2, events: [row(3)], has_more: false, next_after: 3 }),
    );
}

const calledUrl = (index: number) => String(fetchMock.mock.calls[index][0]);

describe("getRunEvents — event type filter", () => {
  it("sends the types allow-list on page 1 and page 2 when types is given", async () => {
    twoPages();

    const frames = await getRunEvents("t.t.t", "run-1", 0, undefined, { types: CHAT_EVENT_TYPES });

    expect(frames.map((f) => f.data.seq)).toEqual([1, 2, 3]);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(calledUrl(0)).toContain("/api/runs/run-1/events?after=0&limit=5000&types=chat_message,chat_reply");
    expect(calledUrl(1)).toContain("/api/runs/run-1/events?after=2&limit=5000&types=chat_message,chat_reply");
    expect(calledUrl(0)).not.toContain("exclude_types");
  });

  it("sends the exclude_types deny-list on every page when excludeTypes is given", async () => {
    twoPages();

    await getRunEvents("t.t.t", "run-1", 0, undefined, { excludeTypes: STREAM_DELTA_EVENT_TYPES });

    expect(calledUrl(0)).toContain("after=0&limit=5000&exclude_types=agent_chunk,agent_thinking");
    expect(calledUrl(1)).toContain("after=2&limit=5000&exclude_types=agent_chunk,agent_thinking");
    expect(calledUrl(0)).not.toContain("&types=");
  });

  it("encodes each token when a token carries reserved characters", async () => {
    fetchMock.mockResolvedValueOnce(okJson({ workflow_id: "run-1", after: 0, events: [] }));

    await getRunEvents("t.t.t", "run-1", 0, undefined, { types: ["a&b", "c"] });

    expect(calledUrl(0)).toMatch(/&types=a%26b,c$/);
  });

  it("sends no filter param when the filter is omitted", async () => {
    twoPages();

    await getRunEvents("t.t.t", "run-1", 0);

    expect(calledUrl(0)).toMatch(/\/api\/runs\/run-1\/events\?after=0&limit=5000$/);
    expect(calledUrl(1)).toMatch(/\/api\/runs\/run-1\/events\?after=2&limit=5000$/);
  });

  it("sends no filter param when both lists are empty", async () => {
    fetchMock.mockResolvedValueOnce(okJson({ workflow_id: "run-1", after: 0, events: [] }));

    await getRunEvents("t.t.t", "run-1", 0, undefined, { types: [], excludeTypes: [] });

    expect(calledUrl(0)).toMatch(/\/events\?after=0&limit=5000$/);
  });

  it("calls onPage once per page when a filter is given", async () => {
    twoPages();
    const pages: DurableFrame[][] = [];

    await getRunEvents("t.t.t", "run-1", 0, (frames) => pages.push(frames), {
      excludeTypes: STREAM_DELTA_EVENT_TYPES,
    });

    expect(pages.map((page) => page.map((f) => f.data.seq))).toEqual([[1, 2], [3]]);
  });
});
