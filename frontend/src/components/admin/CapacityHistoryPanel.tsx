"use client";

/**
 * CapacityHistoryPanel — the Machines tab's history section (ADR-0056): range,
 * resolution and time-zone controls over `CapacityHistoryCharts`.
 *
 * Container: owns the `useCapacityHistory` fetch. The view options themselves
 * are controlled by the parent (`MachinesPanel`) so they survive this panel
 * unmounting while the capacity table is between polls.
 */

import { RefreshCw } from "lucide-react";
import type { CapacityHistoryRange } from "@/lib/api";
import { useCapacityHistory } from "@/hooks/useCapacityHistory";
import { Card } from "@/components/ui/Card";
import { CapacityHistoryCharts } from "./CapacityHistoryCharts";
import { formatPeriod, formatTimestamp } from "./capacityHistoryFormat";
import type { TimeZoneMode } from "./capacityHistoryFormat";

export const HISTORY_RANGES: readonly CapacityHistoryRange[] = [
  "1h",
  "3h",
  "12h",
  "1d",
  "3d",
  "1w",
  "15d",
  "30d",
  "90d",
];

export interface HistoryViewOptions {
  range: CapacityHistoryRange;
  /** `null` = let the backend pick the range's default resolution. */
  periodSeconds: number | null;
  timeZone: TimeZoneMode;
}

export const DEFAULT_HISTORY_VIEW: HistoryViewOptions = {
  range: "3h",
  periodSeconds: null,
  timeZone: "local",
};

export interface CapacityHistoryPanelProps {
  token: string | null;
  instanceId: string;
  options: HistoryViewOptions;
  onOptionsChange: (next: HistoryViewOptions) => void;
}

function segmentClass(active: boolean): string {
  return [
    "px-2 py-1 text-[11px] font-medium rounded-[6px] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
    active ? "bg-brand-fill text-brand" : "text-ink-500 hover:text-ink-900 hover:bg-surface-warm",
  ].join(" ");
}

export function CapacityHistoryPanel({
  token,
  instanceId,
  options,
  onOptionsChange,
}: CapacityHistoryPanelProps) {
  const { state, refresh } = useCapacityHistory(
    token,
    instanceId,
    options.range,
    options.periodSeconds,
  );

  // Resolution choices come from the backend's answer for THIS range; until it
  // arrives only "Auto" is offered (a range change always resets to Auto).
  const allowedPeriods =
    state.status === "ready" && state.history.range === options.range
      ? state.history.allowed_periods
      : [];
  const activePeriod = state.status === "ready" ? state.history.period_seconds : null;
  const refreshing = state.status === "loading" || (state.status === "ready" && state.refreshing);

  return (
    <section aria-labelledby="capacity-history-heading" className="space-y-4">
      <Card className="px-5 py-4 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <h3 id="capacity-history-heading" className="text-[13px] font-semibold text-ink-900">
              Metrics history
            </h3>
            <p className="mt-0.5 text-[11px] text-ink-400">
              <span className="font-mono text-ink-700">{instanceId}</span>
              {state.status === "ready" && (
                <>
                  {" · "}
                  {formatPeriod(state.history.period_seconds)} resolution · updated{" "}
                  {formatTimestamp(Date.parse(state.history.fetched_at), options.timeZone)}
                </>
              )}
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <div role="group" aria-label="Time range" className="flex flex-wrap items-center gap-0.5 rounded-[8px] border border-line-control p-0.5">
              {HISTORY_RANGES.map((range) => (
                <button
                  key={range}
                  type="button"
                  aria-pressed={options.range === range}
                  className={segmentClass(options.range === range)}
                  onClick={() => onOptionsChange({ ...options, range, periodSeconds: null })}
                >
                  {range}
                </button>
              ))}
            </div>

            <label className="flex items-center gap-1.5 text-[11px] text-ink-500">
              Resolution
              <select
                className="rounded-[6px] border border-line-control bg-surface-card px-1.5 py-1 text-[11px] text-ink-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
                value={options.periodSeconds == null ? "auto" : String(options.periodSeconds)}
                onChange={(event) =>
                  onOptionsChange({
                    ...options,
                    periodSeconds: event.target.value === "auto" ? null : Number(event.target.value),
                  })
                }
              >
                <option value="auto">
                  Auto{options.periodSeconds == null && activePeriod != null ? ` (${formatPeriod(activePeriod)})` : ""}
                </option>
                {allowedPeriods.map((period) => (
                  <option key={period} value={String(period)}>
                    {formatPeriod(period)}
                  </option>
                ))}
              </select>
            </label>

            <div role="group" aria-label="Time zone" className="flex items-center gap-0.5 rounded-[8px] border border-line-control p-0.5">
              {(["local", "utc"] as const).map((zone) => (
                <button
                  key={zone}
                  type="button"
                  aria-pressed={options.timeZone === zone}
                  className={segmentClass(options.timeZone === zone)}
                  onClick={() => onOptionsChange({ ...options, timeZone: zone })}
                >
                  {zone === "local" ? "Local" : "UTC"}
                </button>
              ))}
            </div>

            <button
              type="button"
              aria-label="Refresh charts"
              title="Refresh charts"
              disabled={refreshing}
              onClick={refresh}
              className="inline-flex h-7 w-7 items-center justify-center rounded-[6px] border border-line-control text-ink-500 transition-colors hover:text-ink-900 disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
            >
              <RefreshCw
                aria-hidden="true"
                className={`h-3.5 w-3.5 ${refreshing ? "animate-spin motion-reduce:animate-none" : ""}`}
              />
            </button>
          </div>
        </div>

        {state.status === "ready" && state.refreshError && (
          <p role="status" className="mt-2 text-[11px] text-status-failed">
            Refresh failed ({state.refreshError}); showing the last loaded data.
          </p>
        )}
      </Card>

      <CapacityHistoryCharts state={state} timeZone={options.timeZone} />
    </section>
  );
}

export default CapacityHistoryPanel;
