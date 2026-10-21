/**
 * ADR-0056 — formatters for the Machines-tab history charts.
 */
import { describe, expect, it } from "vitest";
import {
  formatBytesPerSecond,
  formatCount,
  formatMaybe,
  formatPercent,
  formatPeriod,
  formatTimeTick,
  formatTimestamp,
  formatterForUnit,
} from "./capacityHistoryFormat";

const MS = Date.UTC(2026, 9, 21, 14, 5);

describe("value formatters", () => {
  it("prints whole percents bare and fractional ones to one place", () => {
    expect(formatPercent(25)).toBe("25%");
    expect(formatPercent(12.345)).toBe("12.3%");
  });

  it("scales byte rates through SI units", () => {
    expect(formatBytesPerSecond(0)).toBe("0 B/s");
    expect(formatBytesPerSecond(512.4)).toBe("512 B/s");
    expect(formatBytesPerSecond(2_500)).toBe("2.5 kB/s");
    expect(formatBytesPerSecond(1_000_000)).toBe("1 MB/s");
    expect(formatBytesPerSecond(3.21e9)).toBe("3.2 GB/s");
    expect(formatBytesPerSecond(-2_000)).toBe("-2 kB/s");
  });

  it("prints counts whole, or to two places when averaged", () => {
    expect(formatCount(1)).toBe("1");
    expect(formatCount(0.5)).toBe("0.50");
  });

  it("picks the formatter for each unit and dashes missing values", () => {
    expect(formatterForUnit("percent")(50)).toBe("50%");
    expect(formatterForUnit("bytes_per_second")(2_000)).toBe("2 kB/s");
    expect(formatterForUnit("count")(1)).toBe("1");
    expect(formatMaybe(null, "percent")).toBe("—");
    expect(formatMaybe(7.25, "percent")).toBe("7.3%");
  });
});

describe("time formatters", () => {
  it("shows clock time for ranges up to a day", () => {
    expect(formatTimeTick(MS, "utc", 3 * 3600)).toMatch(/14:05/);
  });

  it("adds the date for ranges up to three days", () => {
    const text = formatTimeTick(MS, "utc", 3 * 86_400);
    expect(text).toMatch(/21/);
    expect(text).toMatch(/14:05/);
  });

  it("shows the date only for longer ranges", () => {
    const text = formatTimeTick(MS, "utc", 7 * 86_400);
    expect(text).toMatch(/21/);
    expect(text).not.toMatch(/14:05/);
  });

  it("suffixes UTC timestamps and leaves local ones bare", () => {
    expect(formatTimestamp(MS, "utc")).toMatch(/14:05 UTC$/);
    expect(formatTimestamp(MS, "local")).not.toMatch(/UTC$/);
  });

  it("names periods in minutes or hours", () => {
    expect(formatPeriod(60)).toBe("1 min");
    expect(formatPeriod(900)).toBe("15 min");
    expect(formatPeriod(3600)).toBe("1 hour");
    expect(formatPeriod(7200)).toBe("2 hours");
    expect(formatPeriod(45)).toBe("45 s");
  });
});
