import { describe, it, expect } from "vitest";
import { formatDuration, formatTokenCount } from "./runStats";

describe("formatDuration", () => {
  it("should return empty string for null or undefined", () => {
    expect(formatDuration(null)).toBe("");
    expect(formatDuration(undefined)).toBe("");
  });

  it("should return empty string for zero", () => {
    expect(formatDuration(0)).toBe("");
  });

  it("should format seconds less than 60", () => {
    expect(formatDuration(30)).toBe("30s");
    expect(formatDuration(45)).toBe("45s");
    expect(formatDuration(1)).toBe("1s");
  });

  it("should format seconds with rounding below 60", () => {
    expect(formatDuration(59.4)).toBe("59s");
    expect(formatDuration(59.6)).toBe("60s");
  });

  it("should format minutes and seconds", () => {
    expect(formatDuration(65)).toBe("1m 5s");
    expect(formatDuration(125)).toBe("2m 5s");
    expect(formatDuration(300)).toBe("5m 0s");
  });

  it("should round seconds in minutes format", () => {
    expect(formatDuration(65.4)).toBe("1m 5s");
    expect(formatDuration(65.6)).toBe("1m 6s");
  });

  it("should handle large durations", () => {
    expect(formatDuration(3661)).toBe("61m 1s");
    expect(formatDuration(7384)).toBe("123m 4s");
  });

  it("should handle exactly 60 seconds", () => {
    expect(formatDuration(60)).toBe("1m 0s");
  });

  it("should handle exactly 120 seconds", () => {
    expect(formatDuration(120)).toBe("2m 0s");
  });

  it("should handle fractional seconds", () => {
    expect(formatDuration(45.5)).toBe("46s");
    expect(formatDuration(45.4)).toBe("45s");
  });
});

describe("formatTokenCount", () => {
  it("should format numbers less than 1000 as-is", () => {
    expect(formatTokenCount(0)).toBe("0");
    expect(formatTokenCount(1)).toBe("1");
    expect(formatTokenCount(500)).toBe("500");
    expect(formatTokenCount(999)).toBe("999");
  });

  it("should format thousands with K suffix", () => {
    expect(formatTokenCount(1000)).toBe("1.0K");
    expect(formatTokenCount(1200)).toBe("1.2K");
    expect(formatTokenCount(5000)).toBe("5.0K");
    expect(formatTokenCount(9999)).toBe("10.0K");
  });

  it("should format millions with M suffix", () => {
    expect(formatTokenCount(1000000)).toBe("1.0M");
    expect(formatTokenCount(2000000)).toBe("2.0M");
    expect(formatTokenCount(1500000)).toBe("1.5M");
    expect(formatTokenCount(999999)).toBe("1000.0K");
  });

  it("should use one decimal place", () => {
    expect(formatTokenCount(1500)).toBe("1.5K");
    expect(formatTokenCount(1550)).toBe("1.6K");
    expect(formatTokenCount(1540)).toBe("1.5K");
  });

  it("should handle boundary values", () => {
    expect(formatTokenCount(999)).toBe("999");
    expect(formatTokenCount(1000)).toBe("1.0K");
    expect(formatTokenCount(999999)).toBe("1000.0K");
    expect(formatTokenCount(1000000)).toBe("1.0M");
  });

  it("should round correctly for thousands", () => {
    expect(formatTokenCount(1050)).toBe("1.1K");
    expect(formatTokenCount(1049)).toBe("1.0K");
  });

  it("should round correctly for millions", () => {
    expect(formatTokenCount(1500000)).toBe("1.5M");
    expect(formatTokenCount(1550000)).toBe("1.6M");
  });

  it("should handle large numbers", () => {
    expect(formatTokenCount(10000000)).toBe("10.0M");
    expect(formatTokenCount(99999999)).toBe("100.0M");
  });
});
