"use client";

import { useEffect, useState } from "react";
import { motion } from "motion/react";
import {
  ChevronLeft, Activity,
  RefreshCw, CheckCircle2, XCircle, Clock3, Cpu,
} from "lucide-react";
import { getToken, getAnalyticsSummary, getPreferences } from "@/lib/api";
import type { AnalyticsSummary } from "@/lib/api";
import { BarChart } from "./charts/BarChart";
import { DonutChart } from "./charts/DonutChart";

interface AnalyticsPageProps {
  onBack: () => void;
}

// Range enum — sent verbatim to the server (38-01 allow-list). Changing it
// re-queries the endpoint (SC-1 server recompute), never re-filters in memory.
type DateFilter = "today" | "3d" | "7d" | "30d" | "90d" | "all";
type PipelineFilter = "all" | "user_stories" | "ppt" | "prototype" | "app_builder" | "custom";

// ─── Model metadata (DISPLAY-ONLY lookup — SC-001, no control flow) ───────────
const MODEL_META: Record<string, { name: string; short: string; inputRate: string; outputRate: string; context: string }> = {
  "eu.anthropic.claude-haiku-4-5-20251001-v1:0":  { name: "Claude Haiku 4.5",  short: "Haiku 4.5",   inputRate: "$0.25 / 1M",  outputRate: "$1.25 / 1M",  context: "200K" },
  "eu.anthropic.claude-sonnet-4-5-20250929-v1:0": { name: "Claude Sonnet 4.5", short: "Sonnet 4.5",  inputRate: "$3.00 / 1M",  outputRate: "$15.00 / 1M", context: "200K" },
  "eu.anthropic.claude-sonnet-4-6":               { name: "Claude Sonnet 4.6", short: "Sonnet 4.6",  inputRate: "$3.00 / 1M",  outputRate: "$15.00 / 1M", context: "1M"   },
  "eu.anthropic.claude-opus-4-5-20251101-v1:0":   { name: "Claude Opus 4.5",   short: "Opus 4.5",    inputRate: "$15.00 / 1M", outputRate: "$75.00 / 1M", context: "200K" },
  "eu.anthropic.claude-opus-4-6-v1":              { name: "Claude Opus 4.6",   short: "Opus 4.6",    inputRate: "$15.00 / 1M", outputRate: "$75.00 / 1M", context: "200K" },
};
const DEFAULT_MODEL_ID = "eu.anthropic.claude-haiku-4-5-20251001-v1:0";

// DISPLAY-ONLY pipeline label map (SC-001/INV-1): the server rolls up on the
// generic `type` column; this maps a type string → a friendly label, and normalises
// the od_/revision variants onto their base label. No workflow-name control flow.
const PIPELINE_LABELS: Record<string, string> = {
  user_stories: "User Stories", user_stories_revision: "User Stories",
  ppt: "Presentation", ppt_revision: "Presentation",
  od_ppt: "Presentation", od_ppt_revision: "Presentation",
  prototype: "Prototype", prototype_revision: "Prototype",
  od_prototype: "Prototype", od_prototype_revision: "Prototype",
  app_builder: "App Builder", app_builder_revision: "App Builder",
  custom: "Custom", mulesoft_to_springboot: "Mulesoft Migration",
  dotnet_to_azure: ".NET Migration",
};

/** Normalise od_/revision type variants onto their base type (display grouping). */
function normalizeType(type: string): string {
  return type.replace("od_ppt", "ppt").replace("od_prototype", "prototype").replace("_revision", "");
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
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [dateFilter, setDateFilter] = useState<DateFilter>("30d");
  const [pipelineFilter, setPipelineFilter] = useState<PipelineFilter>("all");
  const [modelFilter, setModelFilter] = useState<string>("all");
  const [preferredModelId, setPreferredModelId] = useState<string | null>(null);

  // SC-1 server recompute: the summary is re-queried whenever `dateFilter`
  // changes — the server re-aggregates the owner's rows for the new range
  // (HomeLaunchGrid fetch-shell idiom: cancelled guard + getToken + loading/
  // error/finally). No in-memory reduce of raw runs.
  useEffect(() => {
    let cancelled = false;
    const token = getToken();
    if (!token) {
      setError("Not authenticated.");
      setLoading(false);
      return;
    }
    setLoading(true);
    getAnalyticsSummary(token, dateFilter)
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
  }, [dateFilter]);

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

  // ── Derived display data — bound to the endpoint payload (KPI math ported,
  //    not re-derived). pipeline/model filters narrow the already-fetched
  //    rollup arrays client-side (sanctioned — only the DATE filter refetches).
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

  const dailyData = (summary?.daily ?? []).map((d) => ({
    label: formatDate(d.date),
    value: d.total_tokens,
    runs: d.total,
  }));
  const dailyHasTokens = dailyData.some((d) => d.value > 0);
  const dailyEmpty = dailyData.every((d) => d.value === 0 && d.runs === 0);

  const pipelineRows = (summary?.pipelines ?? [])
    .filter((p) => pipelineFilter === "all" || normalizeType(p.type) === pipelineFilter)
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
    .filter((m) => modelFilter === "all" || m.model_id === modelFilter)
    .map((m) => ({
      id: m.model_id,
      name: MODEL_META[m.model_id]?.short ?? m.model_id,
      runs: m.count,
      tokens: m.total_tokens,
      cost: m.cost,
    }))
    .sort((a, b) => b.tokens - a.tokens);
  const modelMax = Math.max(...modelRows.map((m) => m.tokens), 1);

  const activeModelId = modelFilter !== "all"
    ? modelFilter
    : (modelRows[0]?.id ?? DEFAULT_MODEL_ID);
  const meta = MODEL_META[activeModelId] ?? MODEL_META[DEFAULT_MODEL_ID];
  const preferenceLabel = preferredModelId ? (MODEL_META[preferredModelId]?.name ?? null) : null;
  const showPreferenceNote = preferenceLabel && preferenceLabel !== meta.name && modelFilter === "all";

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
                <button key={f} onClick={() => setDateFilter(f)}
                  className={`px-3 py-1.5 rounded-[7px] text-[11px] font-semibold transition-all ${
                    dateFilter === f ? "bg-surface-white text-ink-900 shadow-sm" : "text-ink-500 hover:text-ink-700"
                  }`}>
                  {f === "all" ? "All" : f === "today" ? "Today" : f}
                </button>
              ))}
            </div>
            {/* Pipeline select — narrows the fetched rollup arrays client-side. */}
            <select value={pipelineFilter} onChange={e => setPipelineFilter(e.target.value as PipelineFilter)}
              className="text-[12.5px] font-medium border border-line-control rounded-[9px] px-3 py-2 bg-surface-card text-ink-700 focus:outline-none focus:border-brand transition-colors">
              <option value="all">All pipelines</option>
              <option value="user_stories">User Stories</option>
              <option value="ppt">Presentation</option>
              <option value="prototype">Prototype</option>
              <option value="app_builder">App Builder</option>
              <option value="custom">Custom</option>
            </select>
            {/* Model select — only shown when multiple models appear in the range. */}
            {availableModelIds.length > 1 && (
              <select value={modelFilter} onChange={e => setModelFilter(e.target.value)}
                className="text-[12.5px] font-medium border border-line-control rounded-[9px] px-3 py-2 bg-surface-card text-ink-700 focus:outline-none focus:border-brand transition-colors">
                <option value="all">All models</option>
                {availableModelIds.map(id => (
                  <option key={id} value={id}>
                    {MODEL_META[id]?.short ?? id}
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
                    <div className="h-2.5 bg-[var(--status-queued-fill)] rounded-full overflow-hidden flex mb-3.5">
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
                    </div>
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
                  </>
                )}
              </div>

              {/* Model info — display-only meta for the active model */}
              <div className="bg-surface-card rounded-[14px] border border-line-border px-[18px] py-4 hover:shadow-md transition-shadow">
                <p className="text-[12px] font-semibold text-ink-800 mb-2">Model Details</p>
                <div>
                  {[
                    { label: "Model",          value: meta.name },
                    { label: "Input rate",     value: `${meta.inputRate} tokens` },
                    { label: "Output rate",    value: `${meta.outputRate} tokens` },
                    { label: "Context window", value: `${meta.context} tokens` },
                  ].map(item => (
                    <div key={item.label} className="flex items-center gap-3 py-2 border-t border-line-faint-row">
                      <span className="w-[130px] flex-none text-[11.5px] font-medium text-ink-300">{item.label}</span>
                      <span className="flex-1 text-[12px] text-ink-700 tabular-nums">{item.value}</span>
                    </div>
                  ))}
                </div>
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
