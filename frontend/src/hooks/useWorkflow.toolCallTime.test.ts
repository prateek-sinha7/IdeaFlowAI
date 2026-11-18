import { describe, expect, it } from "vitest";
import { learnServerClockSkew, toolCallTime } from "./useWorkflow";

describe("toolCallTime", () => {
  it("takes the server's clock offset off created_at", () => {
    // created_at written in local time (UTC+1) but labelled UTC; timestamp is true UTC
    learnServerClockSkew({ pipeline_run_id: "run-a", created_at: "2026-11-11T22:55:38.598+00:00", timestamp: "2026-11-11T21:55:38.597+00:00" });
    expect(toolCallTime({ pipeline_run_id: "run-a", created_at: "2026-11-11T23:01:07.839+00:00" })).toBe("2026-11-11T22:01:07.839Z");
  });

  it("leaves created_at unchanged when the server is on UTC", () => {
    learnServerClockSkew({ pipeline_run_id: "run-b", created_at: "2026-11-11T21:55:38.598+00:00", timestamp: "2026-11-11T21:55:38.590+00:00" });
    expect(toolCallTime({ pipeline_run_id: "run-b", created_at: "2026-11-11T22:01:07.000+00:00" })).toBe("2026-11-11T22:01:07.000Z");
  });

  it("uses the browser clock for a live call with no created_at", () => {
    const before = Date.now();
    const t = Date.parse(toolCallTime({ pipeline_run_id: "run-a" }));
    expect(t).toBeGreaterThanOrEqual(before);
    expect(t).toBeLessThanOrEqual(Date.now());
  });
});
