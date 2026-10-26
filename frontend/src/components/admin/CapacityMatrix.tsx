"use client";

/**
 * CapacityMatrix — the admin "Machines" tab body (specs/014 §3.6).
 *
 * A read-only presentation over `useCapacityMatrix`'s discriminated-union
 * state. Mirrors the users table's structure in `admin/page.tsx` (Card shell,
 * loading/empty/data triad, `<table>` with a `bg-surface-warm` header row) so
 * the two tabs feel like one console rather than two different UIs bolted
 * together.
 *
 * Severity colour (CPU %/Memory % cells) routes through the four
 * `--severity-low|medium|high|critical` vars in `globals.css`'s `:root` —
 * those are deliberately NOT registered in the `@theme inline` block, so
 * `text-severity-high` is not a real Tailwind utility. Consumed as arbitrary
 * `var()` text-color utilities instead (the same pattern `Badge.tsx` already
 * uses for its status-ramp fill/border classes). No raw hex anywhere.
 */

import { RefreshCw, Server } from "lucide-react";
import type { CapacityMatrixState } from "@/hooks/useCapacityMatrix";
import type { AdminCapacityGate, AdminCapacityInstance } from "@/lib/api";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import type { BadgeStatus } from "@/components/ui/Badge";
import { Pill } from "@/components/ui/Pill";

const GATE_STATE_BADGE: Record<AdminCapacityGate["state"], BadgeStatus> = {
  allowing: "done",
  blocking: "failed",
  blind: "gate",
};

const GATE_STATE_LABEL: Record<AdminCapacityGate["state"], string> = {
  allowing: "Allowing",
  blocking: "Blocking",
  blind: "Blind",
};

type Severity = "low" | "medium" | "high" | "critical";

const SEVERITY_TEXT_CLASS: Record<Severity, string> = {
  low: "text-[var(--severity-low)]",
  medium: "text-[var(--severity-medium)]",
  high: "text-[var(--severity-high)]",
  critical: "text-[var(--severity-critical)]",
};

/**
 * Buckets a metric reading against its gate threshold into a 4-step severity
 * ladder for at-a-glance colour. There is no backend-provided severity ramp
 * (the gate itself is a binary threshold + hysteresis decision, not a
 * ladder) — this is purely presentational bucketing relative to the
 * threshold: at/above threshold = critical, >=90% of it = high, >=75% =
 * medium, else low. `null` (no reading yet) renders neutral, not a colour.
 */
function severityFor(value: number | null, threshold: number): Severity | null {
  if (value == null || threshold <= 0) return null;
  const ratio = value / threshold;
  if (ratio >= 1) return "critical";
  if (ratio >= 0.9) return "high";
  if (ratio >= 0.75) return "medium";
  return "low";
}

function formatPercent(value: number | null): string {
  return value == null ? "—" : `${value.toFixed(1)}%`;
}

/** "3s ago" / "2m 5s ago" / "—" for an instance that has never had a reading. */
function formatAge(seconds: number | null): string {
  if (seconds == null) return "—";
  const rounded = Math.max(0, Math.round(seconds));
  if (rounded < 60) return `${rounded}s ago`;
  return `${Math.floor(rounded / 60)}m ${rounded % 60}s ago`;
}

/**
 * OK / Stale / Unknown — a display-only bucket over the two flags the API
 * already gives us. "Unknown" (never had a datapoint for either series) is
 * distinct from "Stale" (had one once, but it aged out past
 * `HOST_CAPACITY_MAX_STALENESS_SECONDS`) — both fail open on the gate (D-04),
 * but they read differently to an operator diagnosing why.
 */
function instanceState(inst: AdminCapacityInstance): { label: string; status: BadgeStatus } {
  if (inst.cpu_used_percent == null && inst.mem_used_percent == null) {
    return { label: "Unknown", status: "queued" };
  }
  if (inst.stale) {
    return { label: "Stale", status: "cancelled" };
  }
  return { label: "OK", status: "done" };
}

function MetricCell({ value, threshold }: { value: number | null; threshold: number }) {
  const severity = severityFor(value, threshold);
  return (
    <span className={severity ? `font-semibold ${SEVERITY_TEXT_CLASS[severity]}` : "text-ink-400"}>
      {formatPercent(value)}
    </span>
  );
}

export interface CapacityMatrixProps {
  state: CapacityMatrixState;
  /** Row whose history is shown below the table (ADR-0056). */
  selectedInstanceId?: string | null;
  /** When given, each instance id becomes a button that selects its row. */
  onSelectInstance?: (instanceId: string) => void;
}

export function CapacityMatrix({ state, selectedInstanceId = null, onSelectInstance }: CapacityMatrixProps) {
  if (state.status === "loading") {
    return (
      <Card className="shadow-sm">
        <div className="flex items-center justify-center py-16 gap-2">
          <RefreshCw className="h-4 w-4 animate-spin text-ink-400" />
          <span className="text-[12px] text-ink-400">Loading capacity matrix...</span>
        </div>
      </Card>
    );
  }

  if (state.status === "error") {
    return (
      <Card className="shadow-sm">
        <div className="flex flex-col items-center justify-center py-16 gap-2">
          <Server className="h-8 w-8 text-ink-400/50" />
          <p className="text-[12px] text-status-failed">{state.message}</p>
        </div>
      </Card>
    );
  }

  const { matrix } = state;
  const { gate } = matrix;

  return (
    <div className="space-y-4">
      {/* Gate summary strip — the admission decision every launch/resume/
          revision/concierge-turn is currently subject to (specs/014 §D-01). */}
      <Card className="px-5 py-4 shadow-sm">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-2.5">
            <span className="text-[13px] font-semibold text-ink-900">Admission gate</span>
            <Badge status={GATE_STATE_BADGE[gate.state]} label={GATE_STATE_LABEL[gate.state]} />
            {!gate.enabled && (
              <Pill className="text-[10px] px-1.5 py-0.5">Disabled</Pill>
            )}
          </div>
          <span className="text-[11px] text-ink-400">
            Thresholds: CPU {gate.cpu_threshold_percent.toFixed(0)}% · Memory{" "}
            {gate.mem_threshold_percent.toFixed(0)}%
          </span>
        </div>
        {gate.blind_reason && (
          <p className="mt-2 text-[11px] text-ink-500">Blind: {gate.blind_reason}</p>
        )}
        {gate.signals.length > 0 && (
          <p className="mt-2 text-[11px] text-status-failed">
            {gate.signals
              .map((s) => `${s.name} ${s.value.toFixed(1)}% (>= ${s.threshold.toFixed(0)}%)`)
              .join(" · ")}
          </p>
        )}
        {/* "as of" is shown unconditionally (specs/014 §3.6) — an admin must
            always be able to tell how fresh this whole snapshot is, not just
            each row's own reading age. */}
        <p className="mt-2 text-[10px] text-ink-400">
          As of {new Date(matrix.collected_at).toLocaleTimeString()}
        </p>
      </Card>

      {/* Instances table */}
      <Card className="shadow-sm">
        <div className="flex items-center justify-between px-5 py-4 border-b border-line-divider">
          <div className="flex items-center gap-2">
            <Server className="h-4 w-4 text-ink-400" />
            <span className="text-[13px] font-semibold text-ink-900">Instances</span>
            <Pill className="text-[10px] px-1.5 py-0.5">{matrix.instances.length}</Pill>
          </div>
          <span className="text-[10px] text-ink-400 uppercase tracking-wide">
            Source: {matrix.instance_source}
          </span>
        </div>

        {state.status === "empty" ? (
          <div className="flex flex-col items-center justify-center py-16 gap-2">
            <Server className="h-8 w-8 text-ink-400/50" />
            <p className="text-[12px] text-ink-400">No instances collected yet</p>
          </div>
        ) : (
          <table className="w-full">
            <thead className="bg-surface-warm">
              <tr>
                <th className="text-left text-[10px] font-semibold text-ink-400 uppercase tracking-wider px-5 py-2.5">
                  Instance
                </th>
                <th className="text-left text-[10px] font-semibold text-ink-400 uppercase tracking-wider px-4 py-2.5">
                  Type
                </th>
                <th className="text-center text-[10px] font-semibold text-ink-400 uppercase tracking-wider px-4 py-2.5">
                  State
                </th>
                <th className="text-right text-[10px] font-semibold text-ink-400 uppercase tracking-wider px-4 py-2.5">
                  CPU %
                </th>
                <th className="text-right text-[10px] font-semibold text-ink-400 uppercase tracking-wider px-4 py-2.5">
                  Memory %
                </th>
                <th className="text-left text-[10px] font-semibold text-ink-400 uppercase tracking-wider px-4 py-2.5">
                  Reading age
                </th>
                <th className="text-center text-[10px] font-semibold text-ink-400 uppercase tracking-wider px-5 py-2.5">
                  Gate
                </th>
              </tr>
            </thead>
            <tbody>
              {matrix.instances.map((inst) => {
                const st = instanceState(inst);
                const isSelected = onSelectInstance != null && inst.instance_id === selectedInstanceId;
                return (
                  <tr
                    key={inst.instance_id}
                    // Row click is a mouse convenience; the id button below is
                    // the keyboard/assistive-tech path to the same selection.
                    onClick={onSelectInstance ? () => onSelectInstance(inst.instance_id) : undefined}
                    className={[
                      "border-t border-line-divider transition-colors",
                      onSelectInstance ? "cursor-pointer" : "",
                      isSelected ? "bg-brand-fill" : "hover:bg-surface-warm",
                    ].join(" ")}
                  >
                    <td className="px-5 py-3.5">
                      <div className="flex items-center gap-2">
                        {onSelectInstance ? (
                          <button
                            type="button"
                            aria-pressed={isSelected}
                            aria-label={`Show metrics history for ${inst.instance_id}`}
                            onClick={(event) => {
                              event.stopPropagation();
                              onSelectInstance(inst.instance_id);
                            }}
                            className="rounded-[4px] text-[12px] font-mono text-ink-900 underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
                          >
                            {inst.instance_id}
                          </button>
                        ) : (
                          <span className="text-[12px] font-mono text-ink-900">
                            {inst.instance_id}
                          </span>
                        )}
                        {inst.is_self && (
                          <Pill className="text-[9px] px-1.5 py-0.5 uppercase tracking-wide">
                            This instance
                          </Pill>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3.5 text-[11px] text-ink-500">
                      {inst.instance_type ?? "—"}
                    </td>
                    <td className="px-4 py-3.5 text-center">
                      <Badge status={st.status} label={st.label} />
                    </td>
                    <td className="px-4 py-3.5 text-right">
                      <MetricCell value={inst.cpu_used_percent} threshold={gate.cpu_threshold_percent} />
                    </td>
                    <td className="px-4 py-3.5 text-right">
                      <MetricCell value={inst.mem_used_percent} threshold={gate.mem_threshold_percent} />
                    </td>
                    <td className="px-4 py-3.5 text-[11px] text-ink-400">
                      {formatAge(inst.reading_age_seconds)}
                    </td>
                    <td className="px-5 py-3.5 text-center">
                      <Badge status={GATE_STATE_BADGE[gate.state]} label={GATE_STATE_LABEL[gate.state]} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}

export default CapacityMatrix;
