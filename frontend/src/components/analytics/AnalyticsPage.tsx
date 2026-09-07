"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { motion } from "motion/react";
import {
  ChevronLeft, ChevronDown, Activity,
  RefreshCw, CheckCircle2, XCircle, Clock3, Cpu,
} from "lucide-react";
import { getToken, getAnalyticsSummary, getPreferences, getCapabilities } from "@/lib/api";
import type { AnalyticsSummary, CapabilityModelEntry } from "@/lib/api";
import { routes } from "@/lib/routes";
import { BarChart } from "./charts/BarChart";
import { DonutChart } from "./charts/DonutChart";

interface AnalyticsPageProps {
  onBack: () => void;
}

// Range enum — sent verbatim to the server (38-01 allow-list). Changing it
// re-queries the endpoint (SC-1 server recompute), never re-filters in memory.
type DateFilter = "today" | "3d" | "7d" | "30d" | "90d" | "all";
type PipelineFilter = "all" | "user_stories" | "ppt" | "prototype" | "app_builder" | "custom";

// ─── Model metadata helpers (RFN-002b — dynamic, sourced from /api/capabilities) ─
// The static MODEL_META map is replaced by a live fetch on mount so new models
// added to the catalog appear automatically (SC-001 / INV-12 — no hardcoded
// model-id list on the frontend). Rate formatters scale per-1M values from the
// catalog's Pricing dataclass.

function formatRate(ratePerMillion: number): string {
  if (ratePerMillion === 0) return "—";
  return `$${ratePerMillion.toFixed(2)} / 1M`;
}

function formatContextWindow(tokens: number): string {
  if (tokens >= 1_000_000) return `${(tokens / 1_000_000).toFixed(0)}M`;
  if (tokens >= 1_000) return `${Math.round(tokens / 1_000)}K`;
  return String(tokens);
}

/** Derive the short display label from a full catalog label.
 *  E.g. "Claude Haiku 4.5" → "Haiku 4.5"
 *       "Claude Sonnet 5 (EU)" → "Sonnet 5"
 *       "Claude Sonnet 5 (US)" → "Sonnet 5"
 *  Region/geo suffixes are stripped — the analytics page shows model families,
 *  not deployment regions (the geo prefix on the raw id is an infra detail). */
function shortLabel(label: string): string {
  return label
    .replace(/^Claude\s+/i, "")
    .replace(/\s*\((EU|US|APAC|Global)\)\s*$/i, "")
    .trim();
}

// DISPLAY-ONLY pipeline label map (SC-001/INV-1): the server rolls up on the
// generic `type` column; this maps a type string → a friendly label, and normalises
// the od_/revision variants onto their base label. No workflow-name control flow.
const PIPELINE_LABELS: Record<string, string> = {
  user_stories: "User Stories", user_stories_revision: "User Stories",
  ppt: "Presentation", ppt_revision: "Presentation",
  prototype: "Prototype", prototype_revision: "Prototype",
  app_builder: "App Builder", app_builder_revision: "App Builder",
  custom: "Custom", mulesoft_to_springboot: "Mulesoft Migration",
  dotnet_to_azure: ".NET Migration",
};

/** Normalise revision type variants onto their base type (display grouping). */
function normalizeType(type: string): string {
  return type.replace("_revision", "");
}

// ─── Formatters (aligned to the mock's number format: compact 1-dp tokens,
//     2-dp currency, tabular figures — 40-04 parity pass) ─────────────────────────
function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}
function formatCost(usd: number): string {
  if (usd === 0) return "$0.00";
  if (usd < 0.01) return "<$0.01";
  return `$${usd.toFixed(2)}`;
}
function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

// ─── Animated counter ─────────────────────────────────────────────────────────
function AnimatedNumber({ value, format }: { value: number; format: (n: number) => string }) {
  const [display, setDisplay] = useState(0);
  const [mounted, setMounted] = useState(false);

  useEffect(() => { setMounted(true); }, []);

  useEffect(() => {
    if (!mounted) return;
    if (value === 0) { setDisplay(0); return; }
    const duration = 700;
    const startTs = performance.now();
    let raf = 0;
    const tick = (now: number) => {
      const t = Math.min((now - startTs) / duration, 1);
      setDisplay(t >= 1 ? value : Math.floor(value * t));
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value, mounted]);

  return <>{format(mounted ? display : value)}</>;
}

// ─── Stat card (mock parity: no icon — label / figure / sub) ────────────────────
function StatCard({ label, value, rawValue, sub, format }: {
  label: string; value: string; rawValue?: number;
  sub?: string; format?: (n: number) => string;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="bg-surface-card rounded-[14px] border border-line-border px-[17px] py-4 hover:shadow-md transition-shadow"
    >
      <p className="text-[9.5px] font-semibold text-ink-300 uppercase tracking-[0.11em] mb-3">{label}</p>
      <p className="text-[24px] font-bold text-ink-900 leading-none tabular-nums">
        {rawValue !== undefined && format
          ? <AnimatedNumber value={rawValue} format={format} />
          : value}
      </p>
      {sub && <p className="text-[11px] text-ink-400 mt-2 tabular-nums">{sub}</p>}
    </motion.div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────
export function AnalyticsPage({ onBack }: AnalyticsPageProps) {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [dateFilter, setDateFilter] = useState<DateFilter>(() => {
    const param = searchParams.get("range");
    if (param === "today" || param === "3d" || param === "7d" || param === "30d" || param === "90d" || param === "all") {
      return param;
    }
    return "30d";
  });
  const [pipelineFilter, setPipelineFilter] = useState<PipelineFilter>(() => {
    const param = searchParams.get("pipeline");
    if (param === "all" || param === "user_stories" || param === "ppt" || param === "prototype" || param === "app_builder" || param === "custom") {
      return param;
    }
    return "all";
  });
  const [modelFilter, setModelFilter] = useState<string>("all");
  const [preferredModelId, setPreferredModelId] = useState<string | null>(null);
  // RFN-002b — live catalog keyed by model id; built from /api/capabilities once
  // on mount.  Replaces the deleted static MODEL_META.  A null value means the
  // fetch has not yet completed; we degrade gracefully (raw id shown as label).
  const [catalogMap, setCatalogMap] = useState<Record<string, CapabilityModelEntry>>({});
  // Model Details collapse state — tracks which model cards are expanded.
  // Seeded with the first model's id once the summary loads so it opens by default.
  const [expandedModels, setExpandedModels] = useState<Set<string>>(new Set());

  // SC-1 server recompute: the summary is re-queried whenever ANY filter
  // changes — the server re-aggregates the owner's rows for the new
  // range/pipeline/model (HomeLaunchGrid fetch-shell idiom: cancelled guard +
  // getToken + loading/error/finally). No in-memory reduce of raw runs.
  // ISS-229/288/289 — the pipeline and model filters have to come back through
  // here too: the KPI tiles, the Daily Activity chart and the Success Rate donut
  // read the payload's window-wide `kpis`/`daily`/`token_totals`, which no
  // client-side narrowing of the two rollup arrays can reach.
  useEffect(() => {
    let cancelled = false;
    const token = getToken();
    if (!token) {
      setError("Not authenticated.");
      setLoading(false);
      return;
    }
    setLoading(true);
    getAnalyticsSummary(
      token,
      dateFilter,
      pipelineFilter === "all" ? undefined : pipelineFilter,
      modelFilter === "all" ? undefined : modelFilter,
    )
      .then((data) => {
        if (cancelled) return;
        setSummary(data);
        setError(null);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e?.message ?? "Failed to load analytics.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [dateFilter, pipelineFilter, modelFilter]);

  // Preferred model (for the "new runs will use…" note) — fetched once.
  useEffect(() => {
    const token = getToken();
    if (!token) return;
    let cancelled = false;
    getPreferences(token)
      .then((p) => { if (!cancelled) setPreferredModelId(p.preferred_model); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  // Seed the first catalog-matched model as expanded when the summary (re)loads,
  // so the top model card opens by default without requiring a click.
  // We reset expandedModels here rather than using an implicit idx===0 fallback,
  // so that clicking to collapse actually works on the first item.
  useEffect(() => {
    if (!summary) return;
    const firstId = (summary.models ?? [])
      .filter(m => m.model_id !== "unknown")
      .sort((a, b) => b.total_tokens - a.total_tokens)[0]?.model_id;
    if (firstId) setExpandedModels(new Set([firstId]));
    else setExpandedModels(new Set());
  }, [summary]);

  // RFN-002b — fetch the live capability catalog once on mount to build catalogMap.
  // The map covers every model in model_catalog.py (all geo-prefix variants) so the
  // Model Details panel and model-dropdown short labels are always correct for new
  // models added to the catalog without any frontend-only change.
  useEffect(() => {
    const token = getToken();
    if (!token) return;
    let cancelled = false;
    getCapabilities(token)
      .then((palette) => {
        if (cancelled) return;
        const map: Record<string, CapabilityModelEntry> = {};
        for (const entry of palette.model_catalog) {
          map[entry.id] = entry;
        }
        setCatalogMap(map);
      })
      .catch(() => {
        // Non-fatal: model labels fall back to raw ids, rates show "—".
      });
    return () => { cancelled = true; };
  }, []);

  // ── Derived display data — bound to the endpoint payload (KPI math ported,
  //    not re-derived). EVERY figure below describes the same population: the
  //    payload is already scoped to the active date/pipeline/model filters
  //    server-side (ISS-229/288/289), so nothing here re-filters in memory.
  const kpis = summary?.kpis;
  const tokenTotals = summary?.token_totals;
  const spend = summary?.spend ?? 0;

  // ── ISS-034: the SIGNED effect of Bedrock prompt caching on this window ──────
  // Both figures come from the backend (INV-12 — no FE rate table, no per-model
  // math); this is a subtraction of two backend dollars, which FIX-037 permits.
  // The sign is the product of the DATA, never baked into the copy: a run that
  // writes cache entries it never re-reads pays the 1.25x cache_write premium for
  // nothing, and 6 of the 11 runs measured when this shipped were net-negative.
  // Zero (including a window of only pre-ISS-034 rows, which fold to a zero delta
  // server-side) renders NOTHING — a "0%" would imply caching ran and broke even.
  const spendFull = summary?.spend_full ?? 0;
  const meteredRuns = summary?.metered_runs ?? 0;
  const cacheDelta = spendFull - spend;
  const cacheDeltaPct = spendFull > 0 ? Math.abs(cacheDelta / spendFull) * 100 : 0;
  const cacheSaved = cacheDelta > 0;
  // Gate on the PERCENTAGE, not the dollar: a short run's delta can be a fraction
  // of a cent and still be a real -8.9% regression worth seeing.
  const showCacheDelta = spendFull > 0 && cacheDeltaPct >= 0.5;

  const totalTokens = tokenTotals?.total ?? 0;
  const inputTokens = tokenTotals?.input ?? 0;
  const outputTokens = tokenTotals?.output ?? 0;
  const cacheReadTokens = tokenTotals?.cache_read ?? 0;
  const cacheWriteTokens = tokenTotals?.cache_write ?? 0;
  // Uncached input = gross input − cache_read − cache_write (Bedrock convention:
  // input_tokens in usage_metadata is the gross total including all cache tiers).
  const uncachedInputTokens = Math.max(0, inputTokens - cacheReadTokens - cacheWriteTokens);
  const hasCacheData = cacheReadTokens > 0 || cacheWriteTokens > 0;
  const completedCount = kpis?.completed ?? 0;
  const failedCount = kpis?.failed ?? 0;
  const totalCount = kpis?.total ?? 0;
  const successRate = kpis ? Math.round(kpis.success_rate * 100) : 0;
  // Avg tokens PER RUN: token_totals.total is summed over ALL runs (backend
  // _aggregate), so the denominator must be all runs (totalCount) too — not
  // completedCount — for a consistent population that matches the label (MD-2).
  const avgTokens = totalCount > 0 ? Math.round(totalTokens / totalCount) : 0;

  const availableModelIds = (summary?.models ?? [])
    .map((m) => m.model_id)
    .sort();

  const dailyData = (summary?.daily ?? []).map((d) => {
    const label = formatDate(d.date);
    return {
      label,
      value: d.total_tokens,
      runs: d.total,
      // ISS-369: tokens in the per-bar tooltip get the same K/M treatment as
      // every other number on this page. Zero-token days keep BarChart's own
      // default so the runs-only fallback tooltip ("Aug 24: 3 runs") survives.
      tip: d.total_tokens > 0 ? `${label}: ${formatTokens(d.total_tokens)}` : undefined,
    };
  });
  const dailyHasTokens = dailyData.some((d) => d.value > 0);
  const dailyEmpty = dailyData.every((d) => d.value === 0 && d.runs === 0);

  const pipelineRows = (summary?.pipelines ?? [])
    .map((p) => ({
      label: PIPELINE_LABELS[normalizeType(p.type)] ?? normalizeType(p.type),
      runs: p.count,
      tokens: p.total_tokens,
      cost: p.cost,
    }))
    .sort((a, b) => (b.tokens !== a.tokens ? b.tokens - a.tokens : b.runs - a.runs));
  const pipelineHasTokens = pipelineRows.some((p) => p.tokens > 0);
  const pipelineMax = pipelineHasTokens
    ? Math.max(...pipelineRows.map((p) => p.tokens), 1)
    : Math.max(...pipelineRows.map((p) => p.runs), 1);

  const modelRows = (summary?.models ?? [])
    .filter((m) => m.model_id !== "unknown")
    .map((m) => ({
      id: m.model_id,
      // RFN-002b: use live catalog label; fall back to cleaned raw id for unrecognised entries.
      name: catalogMap[m.model_id]?.label
        ? shortLabel(catalogMap[m.model_id].label)
        : m.model_id,
      runs: m.count,
      tokens: m.total_tokens,
      cost: m.cost,
    }))
    .sort((a, b) => b.tokens - a.tokens);
  const modelMax = Math.max(...modelRows.map((m) => m.tokens), 1);

  // RFN-002 — per-agent breakdown derived from summary.agents (sorted desc by backend).
  const agentRows = (summary?.agents ?? []).map((a) => ({
    id: a.agent_id,
    name: a.agent_name,
    runs: a.count,
    tokens: a.total_tokens,
    cost: a.cost,
  }));
  const agentMax = Math.max(...agentRows.map((a) => a.tokens), 1);
  const agentHasTokens = agentRows.some((a) => a.tokens > 0);

  const activeModelId = modelFilter !== "all"
    ? modelFilter
    : (modelRows[0]?.id ?? "");
  // RFN-002b — active catalog entry (null when catalog not yet loaded or model unknown).
  const activeCatalogEntry = activeModelId ? (catalogMap[activeModelId] ?? null) : null;
  const preferenceLabel = preferredModelId
    ? (catalogMap[preferredModelId]?.label ?? null)
    : null;
  const showPreferenceNote = preferenceLabel && activeCatalogEntry &&
    preferenceLabel !== activeCatalogEntry.label && modelFilter === "all";

  const DATE_LABELS: Record<DateFilter, string> = {
    today: "Today", "3d": "Last 3 days", "7d": "Last 7 days",
    "30d": "Last 30 days", "90d": "Last 90 days", all: "All time",
  };

  return (
    <div className="h-full flex flex-col overflow-y-auto bg-surface-paper">
      <div className="max-w-[1040px] mx-auto w-full px-10 pt-6 pb-16">

        {/* ── Header (inline over paper — mock parity) ── */}
        <div className="flex items-center gap-3.5 mb-[22px] flex-wrap">
          <button onClick={onBack}
            className="h-9 w-9 flex-none rounded-[9px] border border-line-control bg-surface-card grid place-items-center text-ink-700 hover:border-line-faint transition-colors">
            <ChevronLeft className="h-[17px] w-[17px]" />
          </button>
          <div className="flex-1 min-w-0">
            <h1 className="text-[26px] font-normal italic font-serif text-ink-900 leading-none tracking-tight">Analytics</h1>
            <p className="text-[12.5px] text-ink-400 mt-1.5">Token usage · Cost · Pipeline performance</p>
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            {/* Date pills — each selection re-queries the server (SC-1). */}
            <div className="flex items-center gap-0.5 bg-surface-warm rounded-[9px] p-[3px]">
              {(["today", "3d", "7d", "30d", "90d", "all"] as DateFilter[]).map(f => (
                <button key={f} onClick={() => {
                  setDateFilter(f);
                  router.replace(routes.analytics({ range: f === "30d" ? undefined : f, pipeline: pipelineFilter === "all" ? undefined : pipelineFilter }));
                }}
                  className={`px-3 py-1.5 rounded-[7px] text-[11px] font-semibold transition-all ${
                    dateFilter === f ? "bg-surface-white text-ink-900 shadow-sm" : "text-ink-500 hover:text-ink-700"
                  }`}>
                  {f === "all" ? "All" : f === "today" ? "Today" : f}
                </button>
              ))}
            </div>
            {/* Pipeline select — each selection re-queries the server (SC-1). */}
            <select value={pipelineFilter} onChange={e => {
              const newPipeline = e.target.value as PipelineFilter;
              setPipelineFilter(newPipeline);
              router.replace(routes.analytics({ range: dateFilter === "30d" ? undefined : dateFilter, pipeline: newPipeline === "all" ? undefined : newPipeline }));
            }}
              aria-label="Filter by pipeline"
              name="pipeline-filter"
              className="text-[12.5px] font-medium border border-line-control rounded-[9px] px-3 py-2 bg-surface-card text-ink-700 focus:outline-none focus:border-brand transition-colors">
              <option value="all">All pipelines</option>
              <option value="user_stories">User Stories</option>
              <option value="ppt">Presentation</option>
              <option value="prototype">Prototype</option>
              <option value="app_builder">App Builder</option>
              <option value="custom">Custom</option>
            </select>
            {/* Model select — each selection re-queries the server (SC-1). Shown
                when the window holds more than one model, and kept on screen once
                a model is picked: the filtered payload reports only that one model,
                which would otherwise hide the control still applying the filter. */}
            {(availableModelIds.length > 1 || modelFilter !== "all") && (
              <select value={modelFilter} onChange={e => setModelFilter(e.target.value)}
                aria-label="Filter by model"
                name="model-filter"
                className="text-[12.5px] font-medium border border-line-control rounded-[9px] px-3 py-2 bg-surface-card text-ink-700 focus:outline-none focus:border-brand transition-colors">
                <option value="all">All models</option>
                {availableModelIds.map(id => (
                  <option key={id} value={id}>
                    {catalogMap[id] ? shortLabel(catalogMap[id].label) : id}
                  </option>
                ))}
              </select>
            )}
          </div>
        </div>

        {loading ? (
          <div className="py-24 flex items-center justify-center">
            <div className="flex flex-col items-center gap-3">
              <RefreshCw className="h-5 w-5 animate-spin text-ink-300" />
              <p className="text-[11px] text-ink-400">Loading analytics…</p>
            </div>
          </div>
        ) : error ? (
          <div className="py-24 flex items-center justify-center">
            <div className="flex flex-col items-center gap-2">
              <XCircle className="h-5 w-5 text-status-failed" />
              <p className="text-[11px] text-ink-500">{error}</p>
            </div>
          </div>
        ) : (
          <div className="space-y-3.5">

            {/* ── KPI row ── */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
              <StatCard label="Total Tokens"  value={formatTokens(totalTokens)}
                rawValue={totalTokens} format={formatTokens}
                sub={`${formatTokens(inputTokens)} in · ${formatTokens(outputTokens)} out`} />
              <StatCard label="Est. Cost"     value={formatCost(spend)}
                sub={`across ${completedCount} completed runs`} />
              <StatCard label="Avg / Run"     value={formatTokens(avgTokens)}
                rawValue={avgTokens} format={formatTokens}
                sub="tokens per run" />
              <StatCard label="Total Runs"    value={String(totalCount)}
                rawValue={totalCount} format={n => String(n)}
                sub={`${completedCount} completed · ${failedCount} failed`} />
            </div>

            {/* ── Activity chart + Success rate ── */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">

              {/* Daily activity — extracted BarChart (INV-3), 2/3 width */}
              <div className="lg:col-span-2 bg-surface-card rounded-[14px] border border-line-border px-[18px] py-4 hover:shadow-md transition-shadow">
                <div className="flex items-center justify-between mb-4">
                  <div>
                    <p className="text-[12px] font-semibold text-ink-800">Daily Activity</p>
                    <p className="text-[11px] text-ink-300 mt-1">{DATE_LABELS[dateFilter]}</p>
                  </div>
                  <div className="flex items-center gap-1.5 text-[11px] text-ink-400">
                    <span className="h-2 w-2 rounded-[2px] inline-block" style={{ background: "var(--brand)" }} />
                    {dailyHasTokens ? "Tokens" : "Runs"}
                  </div>
                </div>

                {dailyEmpty ? (
                  <div className="h-32 flex flex-col items-center justify-center gap-1">
                    <Activity className="h-5 w-5 text-ink-300" />
                    <p className="text-[11px] text-ink-400">No activity in this period</p>
                  </div>
                ) : (
                  <>
                    <BarChart
                      data={dailyData}
                      ariaLabel={`Daily ${dailyHasTokens ? "token usage" : "run counts"} for ${DATE_LABELS[dateFilter]}`}
                    />
                    {!dailyHasTokens && (
                      <p className="text-[9px] text-ink-400 mt-2 text-center italic">
                        Showing run counts — token data available for new runs
                      </p>
                    )}
                  </>
                )}
              </div>

              {/* Success rate — extracted DonutChart (INV-3, brand sweep per mock), 1/3 width */}
              <div className="bg-surface-card rounded-[14px] border border-line-border px-[18px] py-4 flex flex-col hover:shadow-md transition-shadow">
                <p className="text-[9.5px] font-semibold text-ink-300 uppercase tracking-[0.11em] mb-2">Success Rate</p>
                <div className="flex justify-center my-3">
                  <DonutChart
                    percent={successRate}
                    ariaLabel={`Success rate ${successRate} percent — ${completedCount} completed of ${totalCount}`}
                  >
                    <span className="text-[22px] font-bold text-ink-900 tabular-nums">{successRate}%</span>
                  </DonutChart>
                </div>
                <div className="space-y-2 w-full mt-auto">
                  <div className="flex items-center justify-between text-[12px] text-ink-700">
                    <span className="flex items-center gap-2">
                      <CheckCircle2 className="h-3.5 w-3.5 text-status-done" /> Completed
                    </span>
                    <span className="tabular-nums">{completedCount}</span>
                  </div>
                  <div className="flex items-center justify-between text-[12px] text-ink-700">
                    <span className="flex items-center gap-2">
                      <XCircle className="h-3.5 w-3.5 text-status-failed" /> Failed
                    </span>
                    <span className="tabular-nums">{failedCount}</span>
                  </div>
                  <div className="flex items-center justify-between text-[12px] text-ink-700">
                    <span className="flex items-center gap-2">
                      <Clock3 className="h-3.5 w-3.5 text-ink-300" /> Total
                    </span>
                    <span className="tabular-nums">{totalCount}</span>
                  </div>
                </div>
              </div>
            </div>

            {/* ── Pipeline breakdown + Model breakdown ── */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">

              {/* By Pipeline Type — bound to pipelines[] rollup */}
              <div className="bg-surface-card rounded-[14px] border border-line-border px-[18px] py-4 hover:shadow-md transition-shadow">
                <p className="text-[12px] font-semibold text-ink-800 mb-3.5">By Pipeline Type</p>
                {pipelineRows.length === 0 ? (
                  <p className="text-[11px] text-ink-400 py-6 text-center">No data for this period</p>
                ) : (
                  <div className="space-y-2.5">
                    {pipelineRows.map((p, i) => {
                      const barVal = pipelineHasTokens ? p.tokens : p.runs;
                      const pct = Math.max(Math.round((barVal / pipelineMax) * 100), barVal > 0 ? 3 : 0);
                      return (
                        <motion.div key={i} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.05 }}>
                          <div className="flex items-center justify-between mb-1.5">
                            <span className="text-[9px] font-bold px-2 py-0.5 rounded-md bg-surface-warm text-ink-500 uppercase tracking-wide">{p.label}</span>
                            <div className="flex items-center gap-2 text-[10.5px] text-ink-300 tabular-nums">
                              <span>{p.runs} run{p.runs !== 1 ? "s" : ""}</span>
                              {p.tokens > 0 && <><span>·</span><span className="font-semibold text-ink-700">{formatTokens(p.tokens)}</span><span>{formatCost(p.cost)}</span></>}
                            </div>
                          </div>
                          <div className="h-1.5 bg-[var(--status-queued-fill)] rounded-full overflow-hidden">
                            <motion.div className="h-full rounded-full"
                              initial={{ width: 0 }}
                              animate={{ width: `${pct}%` }}
                              transition={{ duration: 0.6, delay: i * 0.05, ease: "easeOut" }}
                              style={{ background: "var(--brand)" }}
                            />
                          </div>
                        </motion.div>
                      );
                    })}
                  </div>
                )}
              </div>

              {/* By Model — bound to models[] rollup (ND-40-04-AA: the /api/analytics/summary
                  payload carries no recent-runs list and this plan forbids a new fetch, so this
                  slot renders the live model rollup where the mock shows Recent Runs). */}
              <div className="bg-surface-card rounded-[14px] border border-line-border px-[18px] py-4 hover:shadow-md transition-shadow">
                <p className="text-[12px] font-semibold text-ink-800 mb-3.5">By Model</p>
                {modelRows.length === 0 ? (
                  <p className="text-[11px] text-ink-400 py-6 text-center">No model usage yet</p>
                ) : (
                  <div className="space-y-2.5">
                    {modelRows.map((m, i) => {
                      const pct = Math.max(Math.round((m.tokens / modelMax) * 100), m.tokens > 0 ? 3 : 0);
                      return (
                        <motion.div key={m.id} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.05 }}>
                          <div className="flex items-center justify-between mb-1.5">
                            <div className="flex items-center gap-2">
                              <Cpu className="h-3 w-3 text-brand" />
                              <span className="text-[10.5px] font-semibold text-ink-800">{m.name}</span>
                            </div>
                            <div className="flex items-center gap-2 text-[10.5px] text-ink-300 tabular-nums">
                              <span>{m.runs} run{m.runs !== 1 ? "s" : ""}</span>
                              {m.tokens > 0 && <><span>·</span><span className="font-semibold text-ink-700">{formatTokens(m.tokens)}</span><span>{formatCost(m.cost)}</span></>}
                            </div>
                          </div>
                          <div className="h-1.5 bg-[var(--status-queued-fill)] rounded-full overflow-hidden">
                            <motion.div className="h-full rounded-full"
                              initial={{ width: 0 }}
                              animate={{ width: `${pct}%` }}
                              transition={{ duration: 0.6, delay: i * 0.05, ease: "easeOut" }}
                              style={{ background: "var(--brand-on-dark)" }}
                            />
                          </div>
                        </motion.div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>

            {/* ── By Agent — RFN-002 ── */}
            <div className="bg-surface-card rounded-[14px] border border-line-border px-[18px] py-4 hover:shadow-md transition-shadow">
              <p className="text-[12px] font-semibold text-ink-800 mb-3.5">By Agent</p>
              {agentRows.length === 0 ? (
                <p className="text-[11px] text-ink-400 py-6 text-center">No agent data for this period</p>
              ) : (
                <div className="space-y-2.5">
                  {agentRows.map((a, i) => {
                    const barVal = agentHasTokens ? a.tokens : a.runs;
                    const pct = Math.max(Math.round((barVal / agentMax) * 100), barVal > 0 ? 3 : 0);
                    return (
                      <motion.div key={a.id} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.04 }}>
                        <div className="flex items-center justify-between mb-1.5">
                          <span className="text-[9px] font-bold px-2 py-0.5 rounded-md bg-surface-warm text-ink-500 uppercase tracking-wide">{a.name}</span>
                          <div className="flex items-center gap-2 text-[10.5px] text-ink-300 tabular-nums">
                            <span>{a.runs} run{a.runs !== 1 ? "s" : ""}</span>
                            {a.tokens > 0 && <><span>·</span><span className="font-semibold text-ink-700">{formatTokens(a.tokens)}</span><span>{formatCost(a.cost)}</span></>}
                          </div>
                        </div>
                        <div className="h-1.5 bg-[var(--status-queued-fill)] rounded-full overflow-hidden">
                          <motion.div className="h-full rounded-full"
                            initial={{ width: 0 }}
                            animate={{ width: `${pct}%` }}
                            transition={{ duration: 0.6, delay: i * 0.04, ease: "easeOut" }}
                            style={{ background: "var(--brand)" }}
                          />
                        </div>
                      </motion.div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* ── Token ratio + Model info ── */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">

              {/* Input vs Output ratio — bound to token_totals */}
              <div className="bg-surface-card rounded-[14px] border border-line-border px-[18px] py-4 hover:shadow-md transition-shadow">
                <div className="flex items-center justify-between mb-3">
                  <p className="text-[12px] font-semibold text-ink-800">Token Breakdown</p>
                  {totalTokens > 0 && (
                    <span className="text-[11px] text-ink-300 tabular-nums">
                      {Math.round((inputTokens / totalTokens) * 100)}% in ·{" "}
                      {Math.round((outputTokens / totalTokens) * 100)}% out
                    </span>
                  )}
                </div>

                {totalTokens === 0 ? (
                  <p className="text-[11px] text-ink-400 py-3 text-center">No token data yet</p>
                ) : (
                  <>
                    {/* Segmented bar: uncached input / cache_read / cache_write / output */}
                    <div className="h-2.5 bg-[var(--status-queued-fill)] rounded-full overflow-hidden flex mb-3.5">
                      {hasCacheData ? (
                        <>
                          <motion.div className="h-full bg-brand"
                            style={{ borderRadius: "9999px 0 0 9999px" }}
                            initial={{ width: 0 }}
                            animate={{ width: `${(uncachedInputTokens / totalTokens) * 100}%` }}
                            transition={{ duration: 0.8, ease: "easeOut" }}
                            title={`New input: ${formatTokens(uncachedInputTokens)}`}
                          />
                          <motion.div className="h-full"
                            style={{ background: "var(--status-amber)" }}
                            initial={{ width: 0 }}
                            animate={{ width: `${(cacheReadTokens / totalTokens) * 100}%` }}
                            transition={{ duration: 0.8, ease: "easeOut", delay: 0.05 }}
                            title={`Cache read: ${formatTokens(cacheReadTokens)}`}
                          />
                          <motion.div className="h-full"
                            style={{ background: "var(--status-amber-border)" }}
                            initial={{ width: 0 }}
                            animate={{ width: `${(cacheWriteTokens / totalTokens) * 100}%` }}
                            transition={{ duration: 0.8, ease: "easeOut", delay: 0.1 }}
                            title={`Cache write: ${formatTokens(cacheWriteTokens)}`}
                          />
                          <motion.div className="h-full rounded-r-full"
                            style={{ background: "var(--brand-on-dark)" }}
                            initial={{ width: 0 }}
                            animate={{ width: `${(outputTokens / totalTokens) * 100}%` }}
                            transition={{ duration: 0.8, ease: "easeOut", delay: 0.15 }}
                            title={`Output: ${formatTokens(outputTokens)}`}
                          />
                        </>
                      ) : (
                        <>
                          <motion.div className="h-full bg-brand rounded-l-full"
                            initial={{ width: 0 }}
                            animate={{ width: `${(inputTokens / totalTokens) * 100}%` }}
                            transition={{ duration: 0.8, ease: "easeOut" }}
                          />
                          <motion.div className="h-full rounded-r-full"
                            style={{ background: "var(--brand-on-dark)" }}
                            initial={{ width: 0 }}
                            animate={{ width: `${(outputTokens / totalTokens) * 100}%` }}
                            transition={{ duration: 0.8, ease: "easeOut", delay: 0.1 }}
                          />
                        </>
                      )}
                    </div>
                    {/* Token stat grid — shows cache columns when data is available */}
                    {hasCacheData ? (
                      <div className="grid grid-cols-2 gap-2 mb-2">
                        {[
                          { label: "New Input",    value: uncachedInputTokens, color: "var(--brand)",             accent: "text-ink-900", tip: "Uncached — billed at full input rate" },
                          { label: "Output",       value: outputTokens,        color: "var(--brand-on-dark)",     accent: "text-ink-900", tip: "Model-generated tokens" },
                          { label: "Cache Read",   value: cacheReadTokens,     color: "var(--status-amber)",      accent: "text-ink-900", tip: "Served from cache — ~10% of input rate" },
                          { label: "Cache Write",  value: cacheWriteTokens,    color: "var(--status-amber-border)", accent: "text-ink-900", tip: "Written to cache — ~125% of input rate (5 min TTL)" },
                        ].map(item => (
                          <div key={item.label} className="bg-surface-white border border-line-faint-row rounded-[10px] px-3 py-[11px]" title={item.tip}>
                            <p className={`text-[16px] font-bold tabular-nums ${item.accent}`}>{formatTokens(item.value)}</p>
                            <div className="flex items-center gap-1.5 mt-1.5">
                              <span className="h-1.5 w-1.5 rounded-full" style={{ background: item.color }} />
                              <span className="text-[10.5px] text-ink-300 font-medium">{item.label}</span>
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="grid grid-cols-3 gap-2.5">
                        {[
                          { label: "Input", value: inputTokens, color: "var(--brand)", accent: "text-ink-900" },
                          { label: "Output", value: outputTokens, color: "var(--brand-on-dark)", accent: "text-ink-900" },
                          { label: "Total", value: totalTokens, color: "var(--brand)", accent: "text-brand" },
                        ].map(item => (
                          <div key={item.label} className="bg-surface-white border border-line-faint-row rounded-[10px] px-3 py-[11px]">
                            <p className={`text-[16px] font-bold tabular-nums ${item.accent}`}>{formatTokens(item.value)}</p>
                            <div className="flex items-center gap-1.5 mt-1.5">
                              <span className="h-1.5 w-1.5 rounded-full" style={{ background: item.color }} />
                              <span className="text-[10.5px] text-ink-300 font-medium">{item.label}</span>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                    {/* Total row always shown at bottom when cache data is present */}
                    {hasCacheData && (
                      <div className="bg-surface-white border border-line-faint-row rounded-[10px] px-3 py-[11px] flex items-center justify-between">
                        <div className="flex items-center gap-1.5">
                          <span className="h-1.5 w-1.5 rounded-full bg-brand" />
                          <span className="text-[10.5px] text-ink-300 font-medium">Total</span>
                        </div>
                        <p className="text-[16px] font-bold tabular-nums text-brand">{formatTokens(totalTokens)}</p>
                      </div>
                    )}
                  </>
                )}
              </div>
              {/* Model info — display-only meta for all models in use (RFN-002b: fully dynamic) */}
              <div className="bg-surface-card rounded-[14px] border border-line-border px-[18px] py-4 hover:shadow-md transition-shadow">
                <p className="text-[12px] font-semibold text-ink-800 mb-3">Model Details</p>
                {modelRows.filter(m => catalogMap[m.id]).length === 0 ? (
                  <p className="text-[11px] text-ink-400 py-4 text-center">No model data for this period</p>
                ) : (
                  <div className="divide-y divide-line-faint-row">
                    {modelRows
                      .filter(m => catalogMap[m.id])
                      .filter(m => modelFilter === "all" || modelFilter === m.id)
                      .map((m) => {
                        const entry = catalogMap[m.id]!;
                        // isExpanded is now driven purely by the set — seeded by the useEffect above.
                        const isExpanded = expandedModels.has(m.id);
                        const toggle = () => setExpandedModels(prev => {
                          const next = new Set(prev);
                          if (next.has(m.id)) next.delete(m.id);
                          else next.add(m.id);
                          return next;
                        });
                        return (
                          <div key={m.id} className="border-t border-line-faint-row first:border-t-0">
                            {/* Clickable header row */}
                            <button
                              onClick={toggle}
                              className="w-full flex items-center gap-2 py-1.5 group focus:outline-none"
                              aria-expanded={isExpanded}
                              aria-controls={`model-detail-${m.id}`}
                            >
                              <Cpu className="h-3 w-3 text-brand flex-none" />
                              <span className="text-[11px] font-semibold text-ink-800 group-hover:text-brand transition-colors">{shortLabel(entry.label)}</span>
                              <span className="text-[10px] text-ink-400 tabular-nums">{formatTokens(m.tokens)} · {formatCost(m.cost)}</span>
                              <ChevronDown
                                className={`h-3 w-3 text-ink-300 ml-auto flex-none transition-transform duration-200 ${isExpanded ? "rotate-180" : ""}`}
                              />
                            </button>
                            {/* Collapsible detail rows */}
                            {isExpanded && (
                              <div id={`model-detail-${m.id}`} className="pb-2">
                                {[
                                  { label: "Tier",             value: entry.tier.charAt(0).toUpperCase() + entry.tier.slice(1) },
                                  { label: "Input rate",       value: `${formatRate(entry.input_rate_per_1m ?? 0)} tokens` },
                                  { label: "Output rate",      value: `${formatRate(entry.output_rate_per_1m ?? 0)} tokens` },
                                  { label: "Cache read rate",  value: `${formatRate(entry.cache_read_rate_per_1m ?? 0)} tokens` },
                                  { label: "Cache write rate", value: `${formatRate(entry.cache_write_5m_rate_per_1m ?? 0)} tokens (5m)` },
                                  { label: "Context window",   value: `${formatContextWindow(entry.context_window)} tokens` },
                                ].map(item => (
                                  <div key={item.label} className="flex items-center gap-3 py-1.5 border-t border-line-faint-row">
                                    <span className="w-[120px] flex-none text-[11px] font-medium text-ink-300">{item.label}</span>
                                    <span className="flex-1 text-[11.5px] text-ink-700 tabular-nums">{item.value}</span>
                                  </div>
                                ))}
                                {entry.thinking_supported && (
                                  <div className="flex items-center gap-3 py-1.5 border-t border-line-faint-row">
                                    <span className="w-[120px] flex-none text-[11px] font-medium text-ink-300">Thinking</span>
                                    <span className="text-[11.5px] text-brand font-medium">Adaptive (effort: max)</span>
                                  </div>
                                )}
                              </div>
                            )}
                          </div>
                        );
                      })}
                  </div>
                )}
                {showPreferenceNote && (
                  <div className="mt-3 rounded-lg bg-[var(--status-amber-fill)] border border-[var(--status-amber-border)] px-3 py-2">
                    <p className="text-[10px] text-[var(--status-amber)]">
                      New runs will use <span className="font-semibold">{preferenceLabel}</span>
                    </p>
                  </div>
                )}
                {spend > 0 && (
                  <div className="mt-3 bg-brand-violet-tint border border-brand-border rounded-[9px] px-3 py-2.5 flex items-center justify-between">
                    <span className="text-[11.5px] text-ink-600 font-medium">Total spend ({DATE_LABELS[dateFilter]})</span>
                    <span className="text-[14px] font-bold text-brand tabular-nums">{formatCost(spend)}</span>
                  </div>
                )}
                {/* ISS-034 — signed prompt-cache delta. Percentage is the primary
                    figure (stable under scaling of an incomplete token base); the
                    dollar is secondary. A net LOSS is amber, not red: it is a
                    configuration finding, not an error. */}
                {showCacheDelta && (
                  <div
                    data-testid="cache-delta"
                    className={`mt-2 rounded-[9px] px-3 py-2.5 flex items-center justify-between border ${
                      cacheSaved
                        ? "bg-surface-white border-line-faint-row"
                        : "bg-[var(--status-amber-fill)] border-[var(--status-amber-border)]"
                    }`}
                  >
                    <span className="text-[11.5px] text-ink-600 font-medium">
                      {cacheSaved ? "Prompt caching saved" : "Prompt caching cost more"}
                    </span>
                    <span className="flex items-baseline gap-1.5">
                      <span className={`text-[14px] font-bold tabular-nums ${cacheSaved ? "text-ink-900" : "text-[var(--status-amber)]"}`}>
                        {Math.round(cacheDeltaPct)}%
                      </span>
                      <span className="text-[11px] text-ink-400 tabular-nums">
                        {formatCost(Math.abs(cacheDelta))}
                      </span>
                    </span>
                  </div>
                )}
                {showCacheDelta && (
                  <p className="mt-1.5 text-[10px] leading-[1.45] text-ink-300">
                    {meteredRuns < totalCount
                      ? `Measured on ${meteredRuns} of ${totalCount} runs. `
                      : ""}
                    Engine agent tokens only — Concierge chat is recorded per message
                    but not included here; handoff runs are not metered.
                  </p>
                )}
              </div>
            </div>

          </div>
        )}
      </div>
    </div>
  );
}
