"use client";

// ─── WorkflowDialog (SHELL-04 / SURF-03) ─────────────────────────────────────
//
// Surfaces a COMPILED workflow's DECLARED data — capabilities (the per-step
// gates + validators), context_providers, and compaction — read from
// `getWorkflowDetail` (`GET /api/workflows/{id}`), enriched with capability
// metadata from the `/api/capabilities` registry.
//
// Load-bearing invariant (SC-001 / INV-5): the "Engineer-only" lock is a pure
// REFLECTION of the declared `user_allowed` flag from the registry — it is NEVER
// a workflow-name / pipelineType code branch, and there is NO hardcoded
// agent-count / shot-count fiction. Every value shown is declared, compiled data.

import { useEffect, useState } from "react";
import { X, Lock, Sliders, Layers, Minimize2, AlertCircle } from "lucide-react";
import {
  getToken,
  getCapabilities as fetchCapabilities,
  getWorkflowDetail,
  type CapabilityEntry,
  type WorkflowDetail,
} from "@/lib/api";
import { Card } from "@/components/ui/Card";
import { Pill } from "@/components/ui/Pill";

// One declared capability reference resolved against the registry. `entry` is
// the registry metadata when the declared name is a registered capability;
// absent when it is not (still shown, just without a lock/description).
interface DeclaredCap {
  kind: string;
  name: string;
  entry?: CapabilityEntry;
}

function titleCase(kind: string): string {
  return kind.charAt(0).toUpperCase() + kind.slice(1);
}

export interface WorkflowDialogProps {
  /** The compiled workflow id fetched via `GET /api/workflows/{id}`. */
  workflowId: string;
  onClose: () => void;
  /** Optional JWT override (defaults to the stored token). */
  token?: string | null;
  /** Controlled visibility (defaults to open). */
  open?: boolean;
}

export function WorkflowDialog({
  workflowId,
  onClose,
  token,
  open = true,
}: WorkflowDialogProps) {
  const [detail, setDetail] = useState<WorkflowDetail | null>(null);
  const [registry, setRegistry] = useState<Map<string, CapabilityEntry>>(
    new Map(),
  );
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    const jwt = token ?? getToken();
    if (!jwt) {
      setError("Not authenticated.");
      setLoading(false);
      return;
    }
    setLoading(true);
    Promise.all([getWorkflowDetail(jwt, workflowId), fetchCapabilities(jwt)])
      .then(([wf, palette]) => {
        if (cancelled) return;
        setDetail(wf);
        // Registry keyed by capability name — the declared per-step gate/
        // validator names resolve their trust flag (`user_allowed`) here. NO
        // hardcoded capability list (SC-001).
        const map = new Map<string, CapabilityEntry>();
        for (const cap of palette.capabilities) map.set(cap.name, cap);
        setRegistry(map);
        setError(null);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e?.message ?? "Failed to load workflow.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, workflowId, token]);

  if (!open) return null;

  // Aggregate the DECLARED capabilities across the compiled steps — the
  // per-step gates (kind "gate") + validators (kind "validator"). Deduped by
  // kind:name, order-preserving. This is the compiled projection, never a
  // hardcoded per-workflow list.
  const declaredCaps: DeclaredCap[] = [];
  const seen = new Set<string>();
  for (const step of detail?.steps ?? []) {
    const refs: { kind: string; name: string }[] = [
      ...step.gates.map((name) => ({ kind: "gate", name })),
      ...step.validators.map((name) => ({ kind: "validator", name })),
    ];
    for (const ref of refs) {
      const key = `${ref.kind}:${ref.name}`;
      if (seen.has(key)) continue;
      seen.add(key);
      declaredCaps.push({ ...ref, entry: registry.get(ref.name) });
    }
  }

  // Distinct declared compaction strategies across steps (order-preserving).
  const compactions: string[] = [];
  for (const step of detail?.steps ?? []) {
    if (step.compaction && !compactions.includes(step.compaction)) {
      compactions.push(step.compaction);
    }
  }

  const contextProviders = detail?.context_providers ?? [];

  return (
    <div
      className="fixed inset-0 z-[80] flex items-center justify-center p-6 bg-ink-900/30 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={detail ? `${detail.name} workflow` : "Workflow"}
        onClick={(e) => e.stopPropagation()}
        className="bg-surface-card border border-line-border rounded-[var(--radius-card)] shadow-2xl w-full max-w-md max-h-[90vh] flex flex-col overflow-hidden"
      >
        {/* Header */}
        <div className="px-6 pt-6 pb-4 border-b border-line-border flex-shrink-0">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <h2 className="text-[15px] font-bold text-ink-900 leading-tight truncate">
                {detail?.name ?? "Workflow"}
              </h2>
              {detail?.description && (
                <p className="text-[11px] text-ink-500 mt-0.5">
                  {detail.description}
                </p>
              )}
            </div>
            <button
              onClick={onClose}
              aria-label="Close"
              className="h-7 w-7 flex items-center justify-center rounded-lg text-ink-400 hover:text-ink-700 hover:bg-surface-warm transition-all flex-shrink-0"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="overflow-y-auto flex-1 px-6 py-4 space-y-5">
          {loading && (
            <p className="text-[11px] text-ink-400 py-2">Loading workflow…</p>
          )}

          {error && (
            <div className="flex items-center gap-1.5 text-[11px] text-status-failed bg-[var(--status-failed-fill)] rounded-lg px-2.5 py-1.5">
              <AlertCircle className="h-3 w-3 flex-shrink-0" />
              {error}
            </div>
          )}

          {!loading && !error && detail && (
            <>
              {/* Context providers */}
              <section>
                <div className="flex items-center gap-1.5 mb-2">
                  <Layers className="h-3.5 w-3.5 text-brand" />
                  <p className="text-[10px] font-semibold text-ink-500 uppercase tracking-widest">
                    Context providers
                  </p>
                </div>
                {contextProviders.length > 0 ? (
                  <div className="flex flex-wrap gap-1.5">
                    {contextProviders.map((cp) => (
                      <Pill key={cp} data-context-provider>
                        {cp}
                      </Pill>
                    ))}
                  </div>
                ) : (
                  <p className="text-[11px] text-ink-400">
                    No context providers declared.
                  </p>
                )}
              </section>

              {/* Declared capabilities */}
              <section>
                <div className="flex items-center gap-1.5 mb-2">
                  <Sliders className="h-3.5 w-3.5 text-brand" />
                  <p className="text-[10px] font-semibold text-ink-500 uppercase tracking-widest">
                    Capabilities
                  </p>
                </div>
                {declaredCaps.length > 0 ? (
                  <div className="space-y-1.5">
                    {declaredCaps.map((cap) => {
                      // Engineer-only lock = declared-data reflection of the
                      // registry `user_allowed` flag (INV-5) — never a name
                      // branch. Unregistered declared names show unlocked.
                      const locked = cap.entry
                        ? !cap.entry.user_allowed
                        : false;
                      return (
                        <Card
                          key={`${cap.kind}:${cap.name}`}
                          data-cap-row
                          aria-disabled={locked ? "true" : undefined}
                          aria-label={
                            locked
                              ? `${cap.name} — Engineer-only, not available`
                              : undefined
                          }
                          className={`px-2.5 py-1.5 ${
                            locked ? "opacity-80" : ""
                          }`}
                        >
                          <div className="flex items-center gap-2">
                            {locked && (
                              <Lock className="h-3 w-3 text-ink-400 flex-shrink-0" />
                            )}
                            <p
                              className={`text-[11px] font-semibold truncate flex-1 min-w-0 ${
                                locked ? "text-ink-400" : "text-ink-800"
                              }`}
                            >
                              {cap.name}
                            </p>
                            <span className="text-[9px] font-semibold text-ink-400 uppercase tracking-wide flex-shrink-0">
                              {titleCase(cap.kind)}
                            </span>
                            {locked && (
                              <span className="text-[10px] text-ink-400 flex-shrink-0">
                                Engineer-only
                              </span>
                            )}
                          </div>
                          {cap.entry?.description && (
                            <p
                              className={`text-[11px] ${
                                locked ? "text-ink-400" : "text-ink-500"
                              }`}
                            >
                              {cap.entry.description}
                            </p>
                          )}
                        </Card>
                      );
                    })}
                  </div>
                ) : (
                  <p className="text-[11px] text-ink-400">
                    No capabilities declared.
                  </p>
                )}
              </section>

              {/* Compaction */}
              <section>
                <div className="flex items-center gap-1.5 mb-2">
                  <Minimize2 className="h-3.5 w-3.5 text-brand" />
                  <p className="text-[10px] font-semibold text-ink-500 uppercase tracking-widest">
                    Compaction
                  </p>
                </div>
                {compactions.length > 0 ? (
                  <div className="flex flex-wrap gap-1.5">
                    {compactions.map((c) => (
                      <Pill key={c}>{c}</Pill>
                    ))}
                  </div>
                ) : (
                  <p className="text-[11px] text-ink-400">
                    No compaction declared.
                  </p>
                )}
              </section>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export default WorkflowDialog;
