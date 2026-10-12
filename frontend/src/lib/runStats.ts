/**
 * Shared run-stat formatters — the SINGLE source for the duration + token
 * formatters the run-detail surfaces render (D-15 / no dual implementation).
 *
 * Extracted so `RunDetailPage` imports them rather than re-implementing the
 * `fmt`/`formatDuration` closures inline. The in-panel `WorkflowHistory` detail
 * still carries its own local copies today; those are retired together with the
 * whole in-panel duplicate in 36-05 (which then repoints onto this module).
 */

import type { WaveWorkerEntry } from "@/types/index";

/** Human-readable duration: "45s" / "2m 5s". Falsy/zero → "" (no chip). */
export function formatDuration(seconds?: number | null): string {
  if (!seconds) return "";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
}

/** Compact token count: 2_000_000 → "2.0M", 1_200 → "1.2K", 800 → "800". */
export function formatTokenCount(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

type UsageField = "inputTokens" | "outputTokens" | "totalTokens" | "cacheReadTokens" | "cacheWriteTokens" | "estimatedCostUsd";
type WithUsage = { waveWorkers?: WaveWorkerEntry[] } & Partial<Record<UsageField, number>>;

/** Sum one usage field across a wave step's members (0 for a plain step). */
export function sumWorkers(agent: { waveWorkers?: WaveWorkerEntry[] }, field: UsageField): number {
  return (agent.waveWorkers ?? []).reduce((n, w) => n + (w[field] ?? 0), 0);
}

/** One step's usage: its own figure once it finished, else — a wave still running —
 *  what its finished members have spent so far. */
export function stepUsage(agent: WithUsage, field: UsageField): number {
  return agent[field] || sumWorkers(agent, field);
}

/** A run's usage so far, every field from the same steps — so a live split never
 *  compares a running wave's cache against input that leaves the wave out. */
export function runUsage(agents: WithUsage[] | undefined, field: UsageField): number {
  return (agents ?? []).reduce((n, a) => n + stepUsage(a, field), 0);
}
