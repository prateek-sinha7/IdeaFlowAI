/**
 * Pure geometry for `TimeSeriesChart` — scale, decimation and SVG path building.
 *
 * Kept free of React so every rule is unit-testable on its own. The chart draws
 * in a fixed `VIEW_WIDTH x VIEW_HEIGHT` user space stretched to the container
 * (`preserveAspectRatio="none"` + `vector-effect: non-scaling-stroke`), so no DOM
 * measurement is needed at any width.
 */

export const VIEW_WIDTH = 1000;
export const VIEW_HEIGHT = 100;

/** Missing buckets bridged by a line before it breaks into a visible gap. A
 *  single dropped agent datapoint should not cut the line; an outage should. */
export const MAX_BRIDGED_GAP = 2;

export interface Scale {
  max: number;
  ticks: number[];
}

/**
 * A "nice" 0-based axis covering `maxValue`: steps of 1, 2, 2.5 or 5 x 10^k, so
 * tick labels read as round numbers. Non-positive or non-finite input yields a
 * unit axis rather than a zero-height one.
 */
export function niceScale(maxValue: number, tickCount = 4): Scale {
  const target = Number.isFinite(maxValue) && maxValue > 0 ? maxValue : 1;
  const count = Math.max(1, Math.round(tickCount));
  const rawStep = target / count;
  const magnitude = 10 ** Math.floor(Math.log10(rawStep));
  const residual = rawStep / magnitude;
  const niceResidual =
    residual <= 1 ? 1 : residual <= 2 ? 2 : residual <= 2.5 ? 2.5 : residual <= 5 ? 5 : 10;
  const step = niceResidual * magnitude;
  const steps = Math.ceil(target / step - 1e-9);
  const ticks = Array.from({ length: steps + 1 }, (_, i) => Number((i * step).toPrecision(12)));
  return { max: ticks[ticks.length - 1], ticks };
}

/**
 * Indices worth drawing. Short series keep every present point. Long ones are
 * min/max-decimated into `maxBuckets` buckets: each bucket keeps its lowest and
 * highest point (in time order), so a one-minute spike in a 15-day view still
 * shows instead of being averaged away.
 */
export function pickRenderIndices(
  values: readonly (number | null)[],
  maxBuckets: number,
): number[] {
  const count = values.length;
  const picked: number[] = [];
  if (count <= maxBuckets * 2) {
    for (let i = 0; i < count; i++) if (values[i] != null) picked.push(i);
    return picked;
  }
  const size = count / maxBuckets;
  for (let b = 0; b < maxBuckets; b++) {
    const lo = Math.floor(b * size);
    const hi = Math.min(count, Math.floor((b + 1) * size));
    let minIdx = -1;
    let maxIdx = -1;
    for (let i = lo; i < hi; i++) {
      const v = values[i];
      if (v == null) continue;
      if (minIdx < 0 || v < (values[minIdx] as number)) minIdx = i;
      if (maxIdx < 0 || v > (values[maxIdx] as number)) maxIdx = i;
    }
    if (minIdx < 0) continue;
    if (minIdx === maxIdx) picked.push(minIdx);
    else picked.push(Math.min(minIdx, maxIdx), Math.max(minIdx, maxIdx));
  }
  return picked;
}

/** x (user units) of bucket `index` in a series of `count` buckets. */
export function xForIndex(index: number, count: number): number {
  return count <= 1 ? VIEW_WIDTH / 2 : (index / (count - 1)) * VIEW_WIDTH;
}

/** y (user units, 0 = top) of `value` on a `[0, max]` axis, clamped to the plot. */
export function yForValue(value: number, max: number): number {
  const ratio = max > 0 ? value / max : 0;
  return Math.min(VIEW_HEIGHT, Math.max(0, VIEW_HEIGHT * (1 - ratio)));
}

export interface PathOptions {
  count: number;
  max: number;
  /** Largest index distance still joined by a line (see MAX_BRIDGED_GAP). */
  bridgeDistance: number;
  /** Step-after rendering (state series such as a status check). */
  step?: boolean;
}

/**
 * SVG path over the picked indices. A new sub-path starts after a gap wider than
 * `bridgeDistance`, and every sub-path opens with a zero-length segment so an
 * isolated datapoint still renders as a dot (round line caps).
 */
export function buildLinePath(
  values: readonly (number | null)[],
  indices: readonly number[],
  { count, max, bridgeDistance, step = false }: PathOptions,
): string {
  const parts: string[] = [];
  let previous = Number.NEGATIVE_INFINITY;
  for (const index of indices) {
    const value = values[index];
    if (value == null) continue;
    const x = xForIndex(index, count).toFixed(2);
    const y = yForValue(value, max).toFixed(2);
    if (index - previous > bridgeDistance) {
      parts.push(`M${x} ${y}l0 0`);
    } else if (step) {
      parts.push(`H${x}V${y}`);
    } else {
      parts.push(`L${x} ${y}`);
    }
    previous = index;
  }
  return parts.join("");
}
