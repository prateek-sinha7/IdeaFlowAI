"use client";

/**
 * CapabilityPalette — the live capability-registry palette panel (API-02 / D-11).
 *
 * Fetches `GET /api/capabilities` on mount and renders every registered
 * capability grouped by kind, showing name + the CAP-03 `user_allowed` trust
 * flag. Mirrors the `AgentLibrary.tsx` grouped-list pattern; it is an ADDITIVE
 * sibling panel wired into `WorkflowComposer` (it does not change the existing
 * composer behavior).
 *
 * Data is LIVE — the registry palette, never a hardcoded list — so a newly
 * `@register`'d backend capability appears here with no frontend edit.
 *
 * Subagent/wave-tree and repo-diff viewers are explicitly DEFERRED (no backing
 * data) and are NOT built here.
 */

import { useEffect, useMemo, useState } from "react";
import { Layers, Lock, Check, AlertCircle } from "lucide-react";
import { getCapabilities, getToken, type CapabilityEntry } from "@/lib/api";

interface CapabilityPaletteProps {
  /** Optional token override (defaults to the stored JWT). */
  token?: string | null;
}

export function CapabilityPalette({ token }: CapabilityPaletteProps) {
  const [entries, setEntries] = useState<CapabilityEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const jwt = token ?? getToken();
    if (!jwt) {
      setError("Not authenticated.");
      setLoading(false);
      return;
    }
    setLoading(true);
    getCapabilities(jwt)
      .then((palette) => {
        if (cancelled) return;
        setEntries(palette.capabilities);
        setError(null);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e?.message ?? "Failed to load capabilities.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  // Group the flat palette by kind, preserving a stable kind order.
  const grouped = useMemo(() => {
    const byKind = new Map<string, CapabilityEntry[]>();
    for (const e of entries) {
      const list = byKind.get(e.kind) ?? [];
      list.push(e);
      byKind.set(e.kind, list);
    }
    return Array.from(byKind.entries()).sort(([a], [b]) => a.localeCompare(b));
  }, [entries]);

  return (
    <div className="flex flex-col">
      <div className="flex items-center gap-1.5 mb-2">
        <Layers className="h-3.5 w-3.5 text-[#1B2A4A]" />
        <p className="text-[10px] font-semibold text-gray-500 uppercase tracking-widest">
          Capability Palette
        </p>
      </div>

      {loading && (
        <p className="text-[11px] text-gray-400 py-2">Loading capabilities…</p>
      )}

      {error && (
        <div className="flex items-center gap-1.5 text-[11px] text-red-600 bg-red-50 rounded-lg px-2.5 py-1.5">
          <AlertCircle className="h-3 w-3 flex-shrink-0" />
          {error}
        </div>
      )}

      {!loading && !error && grouped.length === 0 && (
        <p className="text-[11px] text-gray-400 py-2">No capabilities registered.</p>
      )}

      {!loading && !error && (
        <div className="space-y-3 max-h-[260px] overflow-y-auto pr-1">
          {grouped.map(([kind, caps]) => (
            <div key={kind}>
              <p className="text-[9px] font-semibold text-gray-400 uppercase tracking-widest mb-1">
                {kind} ({caps.length})
              </p>
              <div className="space-y-1">
                {caps.map((cap) => (
                  <div
                    key={`${cap.kind}:${cap.name}`}
                    className="flex items-center gap-2 bg-gray-50 border border-gray-100 rounded-lg px-2.5 py-1.5"
                  >
                    <div className="flex-1 min-w-0">
                      <p className="text-[11px] font-semibold text-gray-800 truncate">
                        {cap.name}
                      </p>
                    </div>
                    {cap.user_allowed ? (
                      <span
                        className="flex items-center gap-0.5 text-[8px] text-emerald-600 bg-emerald-50 px-1.5 py-0.5 rounded flex-shrink-0"
                        title="User-grantable capability"
                      >
                        <Check className="h-2.5 w-2.5" /> allowed
                      </span>
                    ) : (
                      <span
                        className="flex items-center gap-0.5 text-[8px] text-gray-400 bg-gray-100 px-1.5 py-0.5 rounded flex-shrink-0"
                        title="Privileged — not user-grantable"
                      >
                        <Lock className="h-2.5 w-2.5" /> privileged
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
