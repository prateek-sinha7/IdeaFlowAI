"use client";

/**
 * TimeSeriesChart — token-styled SVG line chart for evenly spaced buckets
 * (ADR-0056), the time-series sibling of `BarChart` / `DonutChart`.
 *
 * In-house rather than a chart library: two small primitives already cover the
 * analytics page, and one more keeps the bundle free of a charting dependency.
 *
 * - Values are one per bucket from `startMs`, `periodMs` apart; `null` = no data.
 *   Gaps wider than `MAX_BRIDGED_GAP` buckets break the line.
 * - Long series are min/max-decimated before drawing so a 15-day / 1-minute
 *   series (21,600 points) stays light while keeping its spikes.
 * - Lines use `var(--...)` tokens only; no raw hex.
 * - Accessibility: the SVG is a single `role="img"` with a caller-written
 *   `ariaLabel` summary (same contract as the other chart primitives). The hover
 *   crosshair/tooltip is a decorative supplement; the legend is real text.
 */

import { useMemo, useState } from "react";
import type { PointerEvent } from "react";
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

/** Decimation target: ~2 drawn points per bucket keeps lines crisp up to ~1,000px. */
const MAX_RENDER_BUCKETS = 500;
const X_TICK_FRACTIONS = [0, 0.25, 0.5, 0.75, 1] as const;

export interface TimeSeriesLine {
  key: string;
  label: string;
  /** CSS colour, normally a design token such as `var(--brand)`. */
  color: string;
  values: readonly (number | null)[];
  /** Optional legend suffix, e.g. the latest value. */
  detail?: string;
}

export interface TimeSeriesThreshold {
  value: number;
  label: string;
}

export interface TimeSeriesChartProps {
  lines: TimeSeriesLine[];
  /** Epoch ms of bucket 0. */
  startMs: number;
  /** Bucket width in ms. */
  periodMs: number;
  /** Screen-reader text alternative summarising the chart. */
  ariaLabel: string;
  /** Formats y values for axis ticks, tooltip and threshold label. */
  formatValue: (value: number) => string;
  /** Formats a bucket time for the tooltip. */
  formatTime: (ms: number) => string;
  /** Formats a bucket time for the x-axis. */
  formatTick: (ms: number) => string;
  /** Fixed axis maximum (e.g. 100 for percent); otherwise scaled to the data. */
  yMax?: number;
  /** Number of y-axis intervals. */
  tickCount?: number;
  threshold?: TimeSeriesThreshold;
  /** Step-after lines, for state series such as a status check. */
  step?: boolean;
  /** Plot height in px (axes included). */
  height?: number;
}

function seriesMax(lines: readonly TimeSeriesLine[]): number {
  let max = 0;
  for (const line of lines) {
    for (const v of line.values) if (v != null && v > max) max = v;
  }
  return max;
}

export function TimeSeriesChart({
  lines,
  startMs,
  periodMs,
  ariaLabel,
  formatValue,
  formatTime,
  formatTick,
  yMax,
  tickCount = 4,
  threshold,
  step = false,
  height = 150,
}: TimeSeriesChartProps) {
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);
  const count = lines.reduce((n, line) => Math.max(n, line.values.length), 0);

  // Decimation + path building walk every value of every line; memoized so a
  // pointer move (which re-renders for the crosshair) does not redo it.
  const geometry = useMemo(() => {
    const scale = niceScale(
      yMax ?? Math.max(seriesMax(lines), threshold?.value ?? 0),
      tickCount,
    );
    const decimated = count > MAX_RENDER_BUCKETS * 2;
    const bridgeDistance = decimated
      ? Math.max(MAX_BRIDGED_GAP + 1, Math.ceil((2 * count) / MAX_RENDER_BUCKETS))
      : MAX_BRIDGED_GAP + 1;
    const paths = lines.map((line) => ({
      key: line.key,
      color: line.color,
      d: buildLinePath(line.values, pickRenderIndices(line.values, MAX_RENDER_BUCKETS), {
        count,
        max: scale.max,
        bridgeDistance,
        step,
      }),
    }));
    return { scale, paths };
  }, [lines, count, yMax, tickCount, threshold?.value, step]);

  if (count === 0) return null;

  const { scale, paths } = geometry;
  const timeAt = (index: number) => startMs + index * periodMs;
  const xPercent = (index: number) => (xForIndex(index, count) / VIEW_WIDTH) * 100;
  const yPercent = (value: number) => (yForValue(value, scale.max) / VIEW_HEIGHT) * 100;

  const handlePointerMove = (event: PointerEvent<HTMLDivElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    if (rect.width <= 0) return;
    const fraction = Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width));
    setHoverIndex(count <= 1 ? 0 : Math.round(fraction * (count - 1)));
  };

  const hover = hoverIndex != null && hoverIndex < count ? hoverIndex : null;
  const thresholdY =
    threshold && threshold.value <= scale.max ? yForValue(threshold.value, scale.max) : null;

  return (
    <figure className="w-full">
      <div className="relative" style={{ height }}>
        {/* y-axis labels */}
        <div aria-hidden="true" className="absolute left-0 top-0 bottom-5 w-12 text-[9px] text-ink-400 tabular-nums">
          {scale.ticks.map((tick) => (
            <span
              key={tick}
              className="absolute right-2 -translate-y-1/2 whitespace-nowrap"
              style={{ top: `${yPercent(tick)}%` }}
            >
              {formatValue(tick)}
            </span>
          ))}
        </div>

        {/* plot area */}
        <div
          data-testid="time-series-plot"
          className="absolute left-12 right-1 top-0 bottom-5"
          onPointerMove={handlePointerMove}
          onPointerLeave={() => setHoverIndex(null)}
        >
          <svg
            role="img"
            aria-label={ariaLabel}
            viewBox={`0 0 ${VIEW_WIDTH} ${VIEW_HEIGHT}`}
            preserveAspectRatio="none"
            className="block h-full w-full overflow-visible"
          >
            {scale.ticks.map((tick) => {
              const y = yForValue(tick, scale.max);
              return (
                <line
                  key={tick}
                  x1={0}
                  x2={VIEW_WIDTH}
                  y1={y}
                  y2={y}
                  stroke="var(--line-faint-row)"
                  strokeWidth={1}
                  vectorEffect="non-scaling-stroke"
                />
              );
            })}
            {thresholdY != null && (
              <line
                data-testid="time-series-threshold"
                x1={0}
                x2={VIEW_WIDTH}
                y1={thresholdY}
                y2={thresholdY}
                stroke="var(--status-failed)"
                strokeWidth={1}
                strokeDasharray="4 3"
                vectorEffect="non-scaling-stroke"
              />
            )}
            {paths.map((path) => (
              <path
                key={path.key}
                data-testid="time-series-line"
                d={path.d}
                fill="none"
                stroke={path.color}
                strokeWidth={1.5}
                strokeLinejoin="round"
                strokeLinecap="round"
                vectorEffect="non-scaling-stroke"
              />
            ))}
            {hover != null && (
              <line
                x1={xForIndex(hover, count)}
                x2={xForIndex(hover, count)}
                y1={0}
                y2={VIEW_HEIGHT}
                stroke="var(--ink-300)"
                strokeWidth={1}
                vectorEffect="non-scaling-stroke"
              />
            )}
          </svg>

          {thresholdY != null && threshold && (
            <span
              aria-hidden="true"
              className="pointer-events-none absolute right-0 -translate-y-full pb-0.5 text-[9px] text-status-failed"
              style={{ top: `${(thresholdY / VIEW_HEIGHT) * 100}%` }}
            >
              {threshold.label}
            </span>
          )}

          {hover != null && (
            <>
              {lines.map((line) => {
                const value = line.values[hover];
                if (value == null) return null;
                return (
                  <span
                    key={line.key}
                    aria-hidden="true"
                    className="pointer-events-none absolute h-2 w-2 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-[var(--surface-card)]"
                    style={{ left: `${xPercent(hover)}%`, top: `${yPercent(value)}%`, background: line.color }}
                  />
                );
              })}
              <div
                data-testid="time-series-tooltip"
                aria-hidden="true"
                className={[
                  "pointer-events-none absolute top-1 z-20 rounded-md bg-surface-near-black px-2 py-1.5 text-[10px] text-white shadow-lg whitespace-nowrap",
                  xPercent(hover) > 60 ? "-translate-x-[calc(100%+8px)]" : "translate-x-2",
                ].join(" ")}
                style={{ left: `${xPercent(hover)}%` }}
              >
                <div className="mb-0.5 font-semibold">{formatTime(timeAt(hover))}</div>
                {lines.map((line) => {
                  const value = line.values[hover];
                  return (
                    <div key={line.key} className="flex items-center gap-1.5">
                      <span className="h-1.5 w-1.5 rounded-full" style={{ background: line.color }} />
                      <span>{line.label}</span>
                      <span className="ml-auto pl-3 tabular-nums">
                        {value == null ? "—" : formatValue(value)}
                      </span>
                    </div>
                  );
                })}
              </div>
            </>
          )}
        </div>

        {/* x-axis labels */}
        <div aria-hidden="true" className="absolute left-12 right-1 bottom-0 h-4 text-[9px] text-ink-400 tabular-nums">
          {X_TICK_FRACTIONS.map((fraction) => {
            const index = Math.round(fraction * (count - 1));
            const align =
              fraction === 0 ? "translate-x-0" : fraction === 1 ? "-translate-x-full" : "-translate-x-1/2";
            return (
              <span
                key={fraction}
                className={`absolute whitespace-nowrap ${align}`}
                style={{ left: `${fraction * 100}%` }}
              >
                {formatTick(timeAt(index))}
              </span>
            );
          })}
        </div>
      </div>

      <figcaption>
        <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[10px] text-ink-500">
          {lines.map((line) => (
            <li key={line.key} className="flex items-center gap-1.5">
              <span aria-hidden="true" className="h-0.5 w-3 rounded-full" style={{ background: line.color }} />
              <span>{line.label}</span>
              {line.detail && <span className="tabular-nums text-ink-400">{line.detail}</span>}
            </li>
          ))}
        </ul>
      </figcaption>
    </figure>
  );
}

export default TimeSeriesChart;
