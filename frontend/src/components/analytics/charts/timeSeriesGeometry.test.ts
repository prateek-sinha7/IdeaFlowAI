/**
 * ADR-0056 — pure geometry behind TimeSeriesChart: axis scaling, min/max
 * decimation and SVG path building (gaps, isolated points, step lines).
 */
import { describe, expect, it } from "vitest";
import fc from "fast-check";
import {
  MAX_BRIDGED_GAP,
  VIEW_HEIGHT,
  VIEW_WIDTH,
  buildLinePath,
  niceScale,
  pickRenderIndices,
  xForIndex,
  yForValue,
} from "./timeSeriesGeometry";

describe("niceScale", () => {
  it("splits a percent axis into quarters", () => {
    expect(niceScale(100, 4)).toEqual({ max: 100, ticks: [0, 25, 50, 75, 100] });
  });

  it("rounds an arbitrary maximum up to a nice step", () => {
    expect(niceScale(37, 4)).toEqual({ max: 40, ticks: [0, 10, 20, 30, 40] });
  });

  it("handles fractional maxima without float noise", () => {
    expect(niceScale(0.3, 4).ticks).toEqual([0, 0.1, 0.2, 0.3]);
  });

  it("returns a unit axis when the data is all zero or not finite", () => {
    expect(niceScale(0).max).toBe(1);
    expect(niceScale(Number.NaN).max).toBe(1);
  });

  it("gives a two-tick 0/1 axis for a status series", () => {
    expect(niceScale(1, 1)).toEqual({ max: 1, ticks: [0, 1] });
  });

  it("always covers the input maximum with ascending ticks from zero", () => {
    fc.assert(
      fc.property(fc.double({ min: 1e-3, max: 1e12, noNaN: true }), fc.integer({ min: 1, max: 8 }), (value, ticks) => {
        const scale = niceScale(value, ticks);
        expect(scale.ticks[0]).toBe(0);
        expect(scale.max).toBeGreaterThanOrEqual(value * (1 - 1e-9));
        for (let i = 1; i < scale.ticks.length; i++) {
          expect(scale.ticks[i]).toBeGreaterThan(scale.ticks[i - 1]);
        }
      }),
    );
  });
});

describe("pickRenderIndices", () => {
  it("keeps every present point when the series is short", () => {
    expect(pickRenderIndices([1, null, 3, 4], 10)).toEqual([0, 2, 3]);
  });

  it("keeps a single spike when decimating a long series", () => {
    const values: (number | null)[] = Array.from({ length: 10_000 }, () => 1);
    values[4321] = 99;
    const picked = pickRenderIndices(values, 100);
    expect(picked.length).toBeLessThanOrEqual(200);
    expect(picked).toContain(4321);
  });

  it("skips buckets that hold no data", () => {
    const values: (number | null)[] = Array.from({ length: 1_000 }, (_, i) => (i < 500 ? null : i));
    const picked = pickRenderIndices(values, 10);
    expect(picked.every((i) => i >= 500)).toBe(true);
  });

  it("returns sorted, unique, present indices that include the global min and max", () => {
    fc.assert(
      fc.property(
        fc.array(fc.option(fc.integer({ min: -1_000, max: 1_000 }), { nil: null }), { minLength: 1, maxLength: 3_000 }),
        fc.integer({ min: 1, max: 200 }),
        (values, buckets) => {
          const picked = pickRenderIndices(values, buckets);
          for (let i = 1; i < picked.length; i++) expect(picked[i]).toBeGreaterThan(picked[i - 1]);
          expect(picked.every((i) => values[i] != null)).toBe(true);
          const present = values.filter((v): v is number => v != null);
          if (present.length > 0) {
            const pickedValues = picked.map((i) => values[i] as number);
            expect(pickedValues).toContain(Math.max(...present));
            expect(pickedValues).toContain(Math.min(...present));
          }
        },
      ),
    );
  });
});

describe("xForIndex / yForValue", () => {
  it("maps the first and last bucket to the plot edges", () => {
    expect(xForIndex(0, 5)).toBe(0);
    expect(xForIndex(4, 5)).toBe(VIEW_WIDTH);
    expect(xForIndex(0, 1)).toBe(VIEW_WIDTH / 2);
  });

  it("maps zero to the bottom, max to the top, and clamps out-of-range values", () => {
    expect(yForValue(0, 100)).toBe(VIEW_HEIGHT);
    expect(yForValue(100, 100)).toBe(0);
    expect(yForValue(150, 100)).toBe(0);
    expect(yForValue(-5, 100)).toBe(VIEW_HEIGHT);
  });
});

describe("buildLinePath", () => {
  const options = { count: 5, max: 100, bridgeDistance: MAX_BRIDGED_GAP + 1 };

  it("draws one continuous sub-path through consecutive points", () => {
    const values = [0, 50, 100, null, null];
    const d = buildLinePath(values, [0, 1, 2], options);
    expect(d).toBe("M0.00 100.00l0 0L250.00 50.00L500.00 0.00");
  });

  it("bridges a short gap but breaks the line after a long one", () => {
    const values = Array.from({ length: 10 }, (_, i) => (i === 0 || i === 3 || i === 9 ? 10 : null));
    const d = buildLinePath(values, [0, 3, 9], { ...options, count: 10 });
    // 0 → 3 is within the bridge distance; 3 → 9 starts a new sub-path.
    expect(d.match(/M/g)).toHaveLength(2);
    expect(d).toContain("L");
  });

  it("renders an isolated point as a zero-length dot segment", () => {
    expect(buildLinePath([null, 40, null], [1], { ...options, count: 3 })).toBe("M500.00 60.00l0 0");
  });

  it("uses horizontal-then-vertical segments for step lines", () => {
    const d = buildLinePath([0, 1], [0, 1], { count: 2, max: 1, bridgeDistance: 3, step: true });
    expect(d).toBe("M0.00 100.00l0 0H1000.00V0.00");
  });

  it("returns an empty path when nothing is picked", () => {
    expect(buildLinePath([null, null], [], options)).toBe("");
  });
});
