"use client";

/**
 * CapacityHistoryCharts — summary tiles + chart grid for one instance's history
 * (ADR-0056). Presentational: renders whatever `useCapacityHistory` state it is
 * given. Each chart card owns its loading / error / "No data available" state,
 * so a failed disk-I/O lookup never blanks the CPU chart.
 *
 * Charts are driven by the series' `group`, not by series names; only the group
 * titles, the summary-tile picks and the two threshold lines are fixed here.
 */

import { AlertTriangle, RefreshCw } from "lucide-react";
import type { ReactNode } from "react";
import type {
  AdminCapacityHistory,
  CapacityHistoryGroup,
  CapacityHistorySeries,
  CapacityHistoryUnit,
} from "@/lib/api";
import type { CapacityHistoryState } from "@/hooks/useCapacityHistory";
import { Card } from "@/components/ui/Card";
import { TimeSeriesChart } from "@/components/analytics/charts/TimeSeriesChart";
import type { TimeSeriesLine } from "@/components/analytics/charts/TimeSeriesChart";
import {
  formatMaybe,
  formatPeriod,
  formatTimeTick,
  formatTimestamp,
  formatterForUnit,
} from "./capacityHistoryFormat";
import type { TimeZoneMode } from "./capacityHistoryFormat";

interface ChartSpec {
  group: CapacityHistoryGroup;
  title: string;
  unit: CapacityHistoryUnit;
  /** Which gate threshold to draw, if any. */
  threshold?: "cpu" | "memory";
  yMax?: number;
  tickCount?: number;
  step?: boolean;
}

const CHARTS: readonly ChartSpec[] = [
  { group: "cpu", title: "CPU utilization", unit: "percent", threshold: "cpu", yMax: 100 },
  { group: "memory", title: "Memory used", unit: "percent", threshold: "memory", yMax: 100 },
  { group: "disk_used", title: "Disk used", unit: "percent", yMax: 100 },
  { group: "disk_io", title: "Disk I/O (EBS)", unit: "bytes_per_second" },
  { group: "network", title: "Network", unit: "bytes_per_second" },
  { group: "swap", title: "Swap used", unit: "percent", yMax: 100 },
  { group: "status", title: "Status check failed", unit: "count", yMax: 1, tickCount: 1, step: true },
];

/** Line colours by position within a chart — status/brand tokens only. */
const LINE_COLORS = [
  "var(--brand)",
  "var(--status-done)",
  "var(--status-amber)",
  "var(--severity-high)",
] as const;

const SUMMARY_TILES: readonly { key: string; title: string }[] = [
  { key: "cpu_used", title: "CPU" },
  { key: "mem_used", title: "Memory" },
  { key: "disk_root_used", title: "Disk /" },
  { key: "disk_data_used", title: "Disk /var/lib/postgresql" },
];

type CardStatus =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "empty" }
  | { kind: "ready"; series: CapacityHistorySeries[]; partialError: string | null };

function hasData(series: CapacityHistorySeries): boolean {
  return series.values.some((v) => v != null);
}

function cardStatus(state: CapacityHistoryState, group: CapacityHistoryGroup): CardStatus {
  if (state.status === "error") return { kind: "error", message: state.message };
  if (state.status !== "ready") return { kind: "loading" };
  const inGroup = state.history.series.filter((s) => s.group === group);
  const loaded = inGroup.filter((s) => s.error == null);
  const firstError = inGroup.find((s) => s.error != null)?.error ?? null;
  if (loaded.length === 0 && firstError) return { kind: "error", message: firstError };
  if (!loaded.some(hasData)) return { kind: "empty" };
  return { kind: "ready", series: loaded, partialError: firstError };
}

function rangeSeconds(history: AdminCapacityHistory): number {
  return (Date.parse(history.end) - Date.parse(history.start)) / 1000;
}

function chartAriaLabel(
  spec: ChartSpec,
  history: AdminCapacityHistory,
  series: CapacityHistorySeries[],
  thresholdValue: number | null,
): string {
  const parts = series.map(
    (s) =>
      `${s.label}: current ${formatMaybe(s.summary.latest, s.unit)}, average ${formatMaybe(s.summary.avg, s.unit)}, maximum ${formatMaybe(s.summary.max, s.unit)}`,
  );
  const threshold = thresholdValue != null ? ` Gate threshold ${formatMaybe(thresholdValue, spec.unit)}.` : "";
  return `${spec.title} over the last ${history.range} at ${formatPeriod(history.period_seconds)} resolution. ${parts.join("; ")}.${threshold}`;
}

function CardBody({ status, children }: { status: CardStatus; children?: ReactNode }) {
  if (status.kind === "loading") {
    return (
      <div className="flex h-[150px] items-center justify-center gap-2 text-[11px] text-ink-400">
        <RefreshCw aria-hidden="true" className="h-3.5 w-3.5 animate-spin motion-reduce:animate-none" />
        Loading…
      </div>
    );
  }
  if (status.kind === "error") {
    return (
      <div role="alert" className="flex h-[150px] flex-col items-center justify-center gap-1.5 text-[11px] text-status-failed">
        <AlertTriangle aria-hidden="true" className="h-4 w-4" />
        {status.message}
      </div>
    );
  }
  if (status.kind === "empty") {
    return (
      <div className="flex h-[150px] items-center justify-center text-[11px] text-ink-400">
        No data available
      </div>
    );
  }
  return <>{children}</>;
}

function HistoryChartCard({
  spec,
  state,
  timeZone,
}: {
  spec: ChartSpec;
  state: CapacityHistoryState;
  timeZone: TimeZoneMode;
}) {
  const status = cardStatus(state, spec.group);
  const history = state.status === "ready" ? state.history : null;
  const thresholdValue =
    history && spec.threshold === "cpu"
      ? history.cpu_threshold_percent
      : history && spec.threshold === "memory"
        ? history.mem_threshold_percent
        : null;

  let chart: ReactNode = null;
  if (status.kind === "ready" && history) {
    const format = formatterForUnit(spec.unit);
    const span = rangeSeconds(history);
    const lines: TimeSeriesLine[] = status.series.map((s, i) => ({
      key: s.key,
      label: s.label,
      color: LINE_COLORS[i % LINE_COLORS.length],
      values: s.values,
      detail: formatMaybe(s.summary.latest, s.unit),
    }));
    chart = (
      <>
        <TimeSeriesChart
          lines={lines}
          startMs={Date.parse(history.start)}
          periodMs={history.period_seconds * 1000}
          ariaLabel={chartAriaLabel(spec, history, status.series, thresholdValue)}
          formatValue={format}
          formatTime={(ms) => formatTimestamp(ms, timeZone)}
          formatTick={(ms) => formatTimeTick(ms, timeZone, span)}
          yMax={spec.yMax}
          tickCount={spec.tickCount}
          threshold={
            thresholdValue != null
              ? { value: thresholdValue, label: `Gate ${format(thresholdValue)}` }
              : undefined
          }
          step={spec.step}
        />
        {status.partialError && (
          <p className="mt-1.5 text-[10px] text-status-failed">
            Some series failed to load: {status.partialError}
          </p>
        )}
      </>
    );
  }

  return (
    <Card className="px-4 py-3.5 shadow-sm">
      <h4 className="mb-2.5 text-[12px] font-semibold text-ink-900">{spec.title}</h4>
      <CardBody status={status}>{chart}</CardBody>
    </Card>
  );
}

function SummaryTile({
  title,
  series,
  state,
}: {
  title: string;
  series: CapacityHistorySeries | undefined;
  state: CapacityHistoryState;
}) {
  const ready = state.status === "ready" && series != null && series.error == null;
  const unit = series?.unit ?? "percent";
  const summary = ready ? series.summary : null;
  return (
    <Card className="px-4 py-3 shadow-sm">
      <p className="truncate text-[10px] font-semibold uppercase tracking-wide text-ink-400" title={title}>
        {title}
      </p>
      <p className="mt-1 text-[18px] font-semibold tabular-nums text-ink-900">
        {state.status === "loading" ? "…" : formatMaybe(summary?.latest ?? null, unit)}
      </p>
      <p className="text-[10px] tabular-nums text-ink-500">
        avg {formatMaybe(summary?.avg ?? null, unit)} · max {formatMaybe(summary?.max ?? null, unit)}
      </p>
    </Card>
  );
}

export interface CapacityHistoryChartsProps {
  state: CapacityHistoryState;
  timeZone: TimeZoneMode;
}

export function CapacityHistoryCharts({ state, timeZone }: CapacityHistoryChartsProps) {
  const seriesByKey = new Map(
    state.status === "ready" ? state.history.series.map((s) => [s.key, s] as const) : [],
  );
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {SUMMARY_TILES.map((tile) => (
          <SummaryTile key={tile.key} title={tile.title} series={seriesByKey.get(tile.key)} state={state} />
        ))}
      </div>
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        {CHARTS.map((spec) => (
          <HistoryChartCard key={spec.group} spec={spec} state={state} timeZone={timeZone} />
        ))}
      </div>
    </div>
  );
}

export default CapacityHistoryCharts;
