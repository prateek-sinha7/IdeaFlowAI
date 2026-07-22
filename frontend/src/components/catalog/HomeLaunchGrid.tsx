"use client";

/**
 * HomeLaunchGrid — the data-driven Home landing (Plan 20-02 / WF-DB-01, restyled
 * to the shell mock in Phase 40-02). It renders, top→bottom, the mock's Home
 * composition:
 *
 *   eyebrow (ND-A "VelocityAI") → h1 → the PROMPT under the h1 (an Attach
 *   affordance + a primary Build submit — NO Voice, ND-X) → the "Or start from a
 *   deliverable" 3-column CARD GRID (from the live GET /api/workflows list,
 *   ND-D) → the "Jump back in" recents strip (from live GET /api/runs, ND-D).
 *
 * SC-001 / ND-D: EVERY row + recent comes from live endpoints (never the mock's
 * fixed 6 card labels / hardcoded recents). A brand-new manifest setting
 * `user_launchable: true` appears in this catalog with zero FE edit.
 *
 * TWO-GATE filter (preserved from 20-02): GATE 1 = `user_launchable` (the
 * declared product-visibility flag); GATE 2 = `canRunPipeline` (tier). The raw
 * API `name` is NEVER rendered (UI-SPEC §4) — only `display_name ??
 * getWorkflowLabel(id)`. The per-card real estimate (Phase 38, SC-2) is kept.
 *
 * The prompt state is CONTROLLED-OPTIONAL: DashboardLayout owns `homeBrief` and
 * passes `brief`/`onBriefChange`/`onBuild`/`onOpenRun`; when they are absent the
 * component falls back to internal state so it still renders standalone (vitest).
 */

import { useEffect, useRef, useState } from "react";
import { motion } from "motion/react";
import { useRouter } from "next/navigation";
import { ArrowRight, Lock, AlertCircle, Plus, Info, Paperclip, Sparkles, X } from "lucide-react";
import type { WorkflowType } from "@/types/index";
import type { WorkflowRun } from "@/types/index";
import { WorkflowDialog } from "@/components/workflow/WorkflowDialog";
import type { Tier } from "@/lib/entitlements";
import { canRunPipeline, TIER_LABELS, getUpgradeTier } from "@/lib/entitlements";
import { CHAIN_OPTIONS } from "@/lib/workflowChaining";
import { getWorkflowLabel } from "@/hooks/useNotifications";
import {
  getWorkflowDefinitions,
  getAnalyticsSummary,
  getWorkflows,
  getToken,
  type WorkflowSummary,
  type UserWorkflowSummary,
} from "@/lib/api";

interface HomeLaunchGridProps {
  onSelectFeature: (type: WorkflowType) => void;
  // Optional — kept for API compatibility; launch wiring lives in
  // SavedWorkflowsPage (profile dropdown) now.
  onLaunchSaved?: (saved: UserWorkflowSummary) => void;
  userTier?: Tier;
  // Prompt (mock: UNDER the h1) — CONTROLLED-OPTIONAL. DashboardLayout owns the
  // `homeBrief` so it can carry it into the launch (pendingHomeBrief); when these
  // are omitted the component uses internal state and renders standalone.
  brief?: string;
  onBriefChange?: (value: string) => void;
  // Build submit — carries the typed brief down the existing launch fork. When
  // omitted, falls back to the custom-compose entry.
  onBuild?: () => void;
  // "Jump back in" recents deep-link opener (reuses the existing run-open path).
  onOpenRun?: (run: WorkflowRun) => void;
}

// How many recent runs the "Jump back in" strip surfaces (mock: a 3-col grid).
const RECENTS_LIMIT = 6;

// Live status → the recents chip tone. Maps the WorkflowStatus enum onto the
// shared status tokens (no raw hex; UI-SPEC §0). Generic — never a workflow-name
// branch (SC-001/INV-1).
const STATUS_TONE: Record<
  string,
  { label: string; dot: string; text: string }
> = {
  completed: { label: "Done", dot: "bg-status-done", text: "text-status-done" },
  running: { label: "Running", dot: "bg-status-running", text: "text-status-running" },
  revising: { label: "Revising", dot: "bg-status-running", text: "text-status-running" },
  failed: { label: "Failed", dot: "bg-status-failed", text: "text-status-failed" },
  degraded: { label: "Degraded", dot: "bg-status-failed", text: "text-status-failed" },
  cancelled: { label: "Cancelled", dot: "bg-ink-300", text: "text-ink-400" },
};

// Compact, self-contained relative-time formatter for the recents chip (avoids a
// cross-surface import; the exact wording is not asserted — ND-D live data).
function relativeTime(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const secs = Math.max(0, Math.round((Date.now() - then) / 1000));
  if (secs < 60) return "just now";
  const mins = Math.round(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days < 7) return `${days}d ago`;
  const weeks = Math.round(days / 7);
  return `${weeks}w ago`;
}

export function HomeLaunchGrid({
  onSelectFeature,
  userTier = "basic",
  brief,
  onBriefChange,
  onBuild,
  onOpenRun,
}: HomeLaunchGridProps) {
  const router = useRouter();
  const [workflows, setWorkflows] = useState<WorkflowSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // SC-2 (38-01): owner-scoped per-type history-average duration (seconds), keyed
  // by the generic workflow id, from GET /api/analytics/summary. Feeds the "~Xm"
  // half of each card's real estimate. Empty until fetched / on failure.
  const [avgDurationSec, setAvgDurationSec] = useState<Record<string, number>>({});
  // ND-D: the "Jump back in" recents come from the LIVE GET /api/runs list (the
  // same endpoint + WorkflowRun shape WorkflowHistory uses) — never fabricated.
  const [recents, setRecents] = useState<WorkflowRun[]>([]);
  // SURF-03: the compiled workflow the read-only WorkflowDialog is inspecting.
  const [inspectId, setInspectId] = useState<string | null>(null);

  // Prompt (controlled-optional). `brief`/`onBriefChange` win when supplied;
  // otherwise the component owns the value so it renders + tests standalone.
  const [internalBrief, setInternalBrief] = useState("");
  const briefValue = brief ?? internalBrief;
  const setBrief = (value: string) => {
    if (onBriefChange) onBriefChange(value);
    else setInternalBrief(value);
  };

  // ND-X: Attach IS a real image-input affordance (unlike Voice, which has no
  // product capability). The Home picker captures images + previews them as
  // chips; the full downstream out-of-band threading lives in the deliverable
  // input view (IdeaInputPage) reached on launch.
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [attachedImages, setAttachedImages] = useState<{ name: string }[]>([]);

  const handleAttachClick = () => fileInputRef.current?.click();
  const handleFilesPicked = (files: FileList | null) => {
    if (!files || files.length === 0) return;
    setAttachedImages((prev) => [
      ...prev,
      ...Array.from(files).map((f) => ({ name: f.name })),
    ]);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };
  const removeAttachment = (idx: number) =>
    setAttachedImages((prev) => prev.filter((_, i) => i !== idx));

  // Fetch shell ⟵ AgentModelPicker (cancelled guard, getToken fallback,
  // loading/error/finally). `.filter(w => w.user_launchable)` is GATE 1.
  useEffect(() => {
    let cancelled = false;
    const jwt = getToken();
    if (!jwt) {
      setError("Not authenticated.");
      setLoading(false);
      return;
    }
    setLoading(true);
    getWorkflowDefinitions(jwt)
      .then((rows) => {
        if (cancelled) return;
        setWorkflows(rows.filter((w) => w.user_launchable)); // gate 1
        setError(null);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e?.message ?? "Failed to load workflows.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    // SC-2: owner-scoped per-type history average for the "~Xm" estimate half.
    getAnalyticsSummary(jwt, "all")
      .then((summary) => {
        if (cancelled) return;
        setAvgDurationSec(summary.type_avg_duration_sec ?? {});
      })
      .catch(() => {
        if (!cancelled) setAvgDurationSec({});
      });

    // ND-D: the live recent runs for the "Jump back in" strip. Tolerant .catch →
    // empty (the strip then renders NOTHING; never a fabricated placeholder).
    getWorkflows(jwt, { limit: RECENTS_LIMIT })
      .then((runs) => {
        if (!cancelled) setRecents(runs.slice(0, RECENTS_LIMIT));
      })
      .catch(() => {
        if (!cancelled) setRecents([]);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  // Launch fork ⟵ CreationHub, but wizard routing reads from CHAIN_OPTIONS.
  const handleClick = (type: WorkflowType) => {
    if (!canRunPipeline(userTier, type)) return; // gate 2: tier-blocked → no-op
    const opt = CHAIN_OPTIONS.find((o) => o.type === type);
    if (opt?.requiresWizard && opt.wizardPath) {
      router.push(opt.wizardPath);
      return;
    }
    if (type === "prototype") {
      router.push("/workflow/create?mode=prototype");
      return;
    }
    if (type === "ppt") {
      router.push("/workflow/create?mode=ppt");
      return;
    }
    onSelectFeature(type);
  };

  // Build submit — carry the typed brief down the launch fork (custom-compose
  // when the parent gives no explicit handler). Disabled while the brief is empty.
  const buildDisabled = briefValue.trim().length === 0;
  const handleBuild = () => {
    if (buildDisabled) return;
    if (onBuild) onBuild();
    else onSelectFeature("custom" as WorkflowType);
  };

  return (
    <div
      className="flex h-full flex-col overflow-y-auto bg-surface-paper"
      style={{ scrollbarGutter: "stable" }}
    >
      <div className="mx-auto w-full max-w-[1000px] px-6 pt-12 pb-16 sm:px-10">

        {/* Header — eyebrow (ND-A) + h1. The subtitle folds away so the prompt
            sits directly under the h1 (mock composition). */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          className="text-center"
        >
          <p className="mb-4 text-[11px] font-semibold uppercase tracking-[0.22em] text-ink-400">
            VelocityAI
          </p>
          <h1 className="mb-7 font-serif text-[38px] font-normal italic leading-tight tracking-tight text-ink-900 sm:text-[44px]">
            What would you like to build today?
          </h1>
        </motion.div>

        {/* PROMPT under the h1 — the mock's input shell with an Attach affordance
            + a primary Build submit. NO Voice button (ND-X). */}
        <div className="overflow-hidden rounded-[18px] border border-line-border bg-surface-white shadow-[0_8px_30px_rgba(17,17,20,0.05)]">
          <textarea
            id="home-launch-prompt"
            value={briefValue}
            onChange={(e) => setBrief(e.target.value)}
            rows={3}
            placeholder="Describe what you want to build — a prototype, a backlog, an app, a deck…"
            className="block w-full resize-none border-0 bg-transparent px-5 pt-5 pb-2 text-[15px] leading-relaxed text-ink-900 placeholder:text-ink-400 focus:outline-none focus:ring-0"
          />
          <div className="flex items-center gap-4 border-t border-line-divider px-4 py-3">
            <button
              type="button"
              onClick={handleAttachClick}
              className="inline-flex items-center gap-1.5 text-[12.5px] font-medium text-ink-500 transition-colors hover:text-brand"
            >
              <Paperclip className="h-[15px] w-[15px]" /> Attach
            </button>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              multiple
              className="hidden"
              onChange={(e) => handleFilesPicked(e.target.files)}
            />
            {/* NO Voice affordance — ND-X (no product voice-input capability). */}
            <span className="flex-1" />
            <button
              type="button"
              onClick={handleBuild}
              disabled={buildDisabled}
              className={`inline-flex items-center gap-2 rounded-[11px] px-5 py-2.5 text-[13.5px] font-semibold text-white transition-colors ${
                buildDisabled
                  ? "cursor-not-allowed bg-brand opacity-50"
                  : "cursor-pointer bg-brand hover:bg-brand-pressed"
              }`}
            >
              Build
              <ArrowRight className="h-[15px] w-[15px]" />
            </button>
          </div>
        </div>

        {/* Attached-image chips (ND-X — Attach is a real image affordance). */}
        {attachedImages.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
            {attachedImages.map((img, i) => (
              <span
                key={`${img.name}-${i}`}
                className="inline-flex items-center gap-1.5 rounded-lg border border-line-border bg-surface-card px-2.5 py-1 text-[11px] text-ink-600"
              >
                <Paperclip className="h-3 w-3" />
                <span className="max-w-[160px] truncate">{img.name}</span>
                <button
                  type="button"
                  onClick={() => removeAttachment(i)}
                  aria-label={`Remove ${img.name}`}
                  className="text-ink-400 transition-colors hover:text-ink-700"
                >
                  <X className="h-3 w-3" />
                </button>
              </span>
            ))}
          </div>
        )}

        {error && (
          <div className="mt-6 flex items-center gap-1.5 rounded-lg bg-[var(--status-failed-fill)] px-2.5 py-1.5 text-[11px] text-status-failed">
            <AlertCircle className="h-3 w-3 flex-shrink-0" />
            {error}
          </div>
        )}

        {/* "Or start from a deliverable" — the section label + the Create-workflow
            affordance (SAVE-FROM-BOTH catalog entry). */}
        <div className="mt-10 mb-3.5 flex items-center justify-between">
          <p className="text-[10.5px] font-semibold uppercase tracking-[0.14em] text-ink-400">
            Or start from a deliverable
          </p>
          <button
            onClick={() => onSelectFeature("custom" as WorkflowType)}
            className="inline-flex items-center gap-1.5 text-[11px] font-semibold text-ink-500 transition-colors hover:text-brand"
          >
            <Plus className="h-3.5 w-3.5" /> Create workflow
          </button>
        </div>

        {!loading && !error && workflows.length === 0 && (
          <p className="py-2 text-[11px] text-ink-400">
            No workflows available for your plan yet.
          </p>
        )}

        {/* Deliverable CARD GRID (ND-D — live rows). 3 columns on wide viewports,
            mirroring the SavedWorkflowsPage grid idiom for token consistency. */}
        {!loading && !error && workflows.length > 0 && (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {workflows.map((row, idx) => {
              const type = row.id as WorkflowType;
              const label = row.display_name ?? getWorkflowLabel(row.id);
              const subtitle = row.description;
              const agents =
                row.step_count ??
                (row as WorkflowSummary & { agent_count?: number }).agent_count;
              const avgSec = avgDurationSec[row.id];
              void avgSec; // FIX-097: time estimate removed from card display
              const estimate = `~${agents} agents`;
              const allowed = canRunPipeline(userTier, type); // gate 2
              const upgradeTo = getUpgradeTier(userTier, type);
              return (
                <motion.div
                  key={row.id}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.3, delay: 0.06 + idx * 0.05 }}
                  className="relative"
                >
                  {/* The whole card is the launch target → onSelectFeature. Kept
                      as a <button> holding an <h2> so the selection e2e resolves
                      (TS-B). */}
                  <button
                    onClick={() => handleClick(type)}
                    disabled={!allowed}
                    className={`group flex h-full w-full flex-col rounded-[14px] border p-[18px] text-left transition-colors ${
                      allowed
                        ? "cursor-pointer border-line-border bg-surface-card hover:border-line-faint"
                        : "cursor-not-allowed border-line-border bg-surface-card opacity-60"
                    }`}
                  >
                    <div className="mb-3.5 flex items-center justify-between">
                      <span className="grid h-[38px] w-[38px] place-items-center rounded-[10px] bg-surface-warm text-ink-900">
                        {allowed ? (
                          <Sparkles className="h-[19px] w-[19px]" />
                        ) : (
                          <Lock className="h-[18px] w-[18px] text-ink-400" />
                        )}
                      </span>
                      <ArrowRight className="h-[17px] w-[17px] text-ink-300 transition-colors group-hover:text-ink-600" />
                    </div>
                    <h2
                      className={`mb-1.5 text-[14.5px] font-semibold leading-snug ${
                        allowed ? "text-ink-900 group-hover:text-brand" : "text-ink-400"
                      }`}
                    >
                      {label}
                    </h2>
                    <p
                      className={`mb-3 text-[12.5px] leading-relaxed ${
                        allowed ? "text-ink-500" : "text-ink-400"
                      }`}
                    >
                      {subtitle}
                    </p>
                    {/* SC-2 real estimate — agents always; time only when the
                        owner-scoped history has an entry. */}
                    <span className="mt-auto text-[11px] font-medium text-ink-400">
                      {estimate}
                    </span>
                    {!allowed && upgradeTo && (
                      <span className="mt-1.5 text-[10px] font-semibold text-brand">
                        Requires {TIER_LABELS[upgradeTo]} plan
                      </span>
                    )}
                  </button>

                  {/* SURF-03 — inspect this compiled workflow's declared
                      capabilities. A SIBLING of the launch button (never nested),
                      positioned in the card corner; stays enabled even when the
                      row is tier-locked (looking ≠ launching). */}
                  <button
                    type="button"
                    onClick={() => setInspectId(row.id)}
                    aria-label={`Inspect ${label} details`}
                    className="absolute right-2.5 top-2.5 flex h-7 w-7 items-center justify-center rounded-lg text-ink-300 transition-colors hover:bg-surface-warm hover:text-ink-700"
                  >
                    <Info className="h-3.5 w-3.5" />
                  </button>
                </motion.div>
              );
            })}
          </div>
        )}

        {/* "Jump back in" — live recent runs (ND-D). Absent when there are none. */}
        {recents.length > 0 && (
          <>
            <div className="mt-10 mb-3.5 flex items-center justify-between">
              <span className="text-[10.5px] font-semibold uppercase tracking-[0.14em] text-ink-400">
                Jump back in
              </span>
            </div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {recents.map((run) => {
                const tone = STATUS_TONE[run.status] ?? {
                  label: run.status,
                  dot: "bg-ink-300",
                  text: "text-ink-400",
                };
                return (
                  <button
                    key={run.id}
                    type="button"
                    onClick={() => onOpenRun?.(run)}
                    className="group flex flex-col rounded-[13px] border border-line-border bg-surface-card p-[15px] text-left transition-colors hover:border-line-faint"
                  >
                    <div className="mb-2.5 flex items-center gap-2">
                      <span className={`h-1.5 w-1.5 flex-shrink-0 rounded-full ${tone.dot}`} />
                      <span className={`text-[10.5px] font-semibold uppercase tracking-[0.08em] ${tone.text}`}>
                        {tone.label}
                      </span>
                      <span className="flex-1" />
                      <span className="text-[11px] text-ink-400">
                        {relativeTime(run.createdAt)}
                      </span>
                    </div>
                    <p className="mb-1 truncate text-[13.5px] font-semibold text-ink-900 group-hover:text-brand">
                      {run.title}
                    </p>
                    <p className="truncate text-[11.5px] text-ink-400">
                      {getWorkflowLabel(run.type)}
                    </p>
                  </button>
                );
              })}
            </div>
          </>
        )}
      </div>

      {/* SURF-03 detail viewer — read-only; declared data only (INV-5). */}
      {inspectId && (
        <WorkflowDialog workflowId={inspectId} onClose={() => setInspectId(null)} />
      )}
    </div>
  );
}
