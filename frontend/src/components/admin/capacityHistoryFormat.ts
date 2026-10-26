/**
 * Pure formatters for the Machines-tab history charts (ADR-0056). React-free so
 * each rule is unit-testable; the components only pick which one to apply.
 */

import type { CapacityHistoryUnit } from "@/lib/api";

export type TimeZoneMode = "local" | "utc";

const DAY_SECONDS = 86_400;

/** "25%" for whole numbers (axis ticks), "12.3%" otherwise. */
export function formatPercent(value: number): string {
  return Number.isInteger(value) ? `${value}%` : `${value.toFixed(1)}%`;
}

const RATE_UNITS = ["B/s", "kB/s", "MB/s", "GB/s", "TB/s"] as const;

/** Decimal (SI) byte rate: "512 B/s", "2.5 kB/s", "1.2 MB/s". */
export function formatBytesPerSecond(value: number): string {
  let scaled = Math.abs(value);
  let unit = 0;
  while (scaled >= 1000 && unit < RATE_UNITS.length - 1) {
    scaled /= 1000;
    unit += 1;
  }
  const sign = value < 0 ? "-" : "";
  const digits = unit === 0 || Number.isInteger(scaled) ? 0 : 1;
  return `${sign}${scaled.toFixed(digits)} ${RATE_UNITS[unit]}`;
}

/** Whole counts as-is, fractional ones (averaged buckets) to two places. */
export function formatCount(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(2);
}

export function formatterForUnit(unit: CapacityHistoryUnit): (value: number) => string {
  if (unit === "percent") return formatPercent;
  if (unit === "bytes_per_second") return formatBytesPerSecond;
  return formatCount;
}

/** "—" for a missing value, otherwise the unit's formatter. */
export function formatMaybe(value: number | null, unit: CapacityHistoryUnit): string {
  return value == null ? "—" : formatterForUnit(unit)(value);
}

function timeZoneOption(mode: TimeZoneMode): string | undefined {
  return mode === "utc" ? "UTC" : undefined;
}

/**
 * X-axis label sized to the range: clock time up to a day, date + time up to
 * three days, date only beyond.
 */
export function formatTimeTick(ms: number, mode: TimeZoneMode, rangeSeconds: number): string {
  const timeZone = timeZoneOption(mode);
  const options: Intl.DateTimeFormatOptions =
    rangeSeconds <= DAY_SECONDS
      ? { hour: "2-digit", minute: "2-digit", hourCycle: "h23", timeZone }
      : rangeSeconds <= 3 * DAY_SECONDS
        ? { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hourCycle: "h23", timeZone }
        : { month: "short", day: "numeric", timeZone };
  return new Intl.DateTimeFormat(undefined, options).format(ms);
}

/** Tooltip / "updated" timestamp, suffixed " UTC" in UTC mode. */
export function formatTimestamp(ms: number, mode: TimeZoneMode): string {
  const text = new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
    timeZone: timeZoneOption(mode),
  }).format(ms);
  return mode === "utc" ? `${text} UTC` : text;
}

/** "1 min", "5 min", "1 hour", "6 hours". */
export function formatPeriod(seconds: number): string {
  if (seconds % 3600 === 0) {
    const hours = seconds / 3600;
    return hours === 1 ? "1 hour" : `${hours} hours`;
  }
  if (seconds % 60 === 0) return `${seconds / 60} min`;
  return `${seconds} s`;
}
