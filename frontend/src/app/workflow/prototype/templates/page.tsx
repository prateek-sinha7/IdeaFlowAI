"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, ArrowRight, Sparkles, ChevronDown, ChevronRight, Layers, Eye } from "lucide-react";
import { getToken } from "@/lib/api";
import {
  listDesignSystems,
  listPrototypeTemplates,
  type DesignSystemListItem,
  type PrototypeTemplate,
} from "@/lib/prototype-api";
import { TemplateGallery } from "@/components/workflow/prototype/TemplateGallery";
import { DesignSystemPicker } from "@/components/workflow/prototype/DesignSystemPicker";
import type { CustomDesignSystem } from "@/components/workflow/prototype/CustomDesignSystemModal";
import type { CustomTemplate } from "@/components/workflow/prototype/CustomTemplateModal";

const STORAGE_KEY = "prototype.draft";

export default function PrototypeTemplatesPage() {
  const router = useRouter();

  const [authChecked, setAuthChecked] = useState(false);
  const [templates, setTemplates] = useState<PrototypeTemplate[]>([]);
  const [systems, setSystems] = useState<DesignSystemListItem[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [selectedTemplateId, setSelectedTemplateId] = useState<string | null>(null);
  const [selectedDsId, setSelectedDsId] = useState<string | null>(null);
  // Holds the body of a custom DS when one is selected; null for built-in systems
  const [customDsBody, setCustomDsBody] = useState<string | null>(null);
  // Holds the body of a custom template when one is selected; null for built-in templates
  const [customTemplateBody, setCustomTemplateBody] = useState<string | null>(null);
  const [brief, setBrief] = useState("");
  const [chainFrom, setChainFrom] = useState<string | null>(null);
  const [chainContextBlock, setChainContextBlock] = useState<string | null>(null);
  const [contextExpanded, setContextExpanded] = useState(false);

  useEffect(() => {
    const token = getToken();
    if (!token) { router.replace("/login"); return; }
    setAuthChecked(true);
    // Check if we arrived via a chain action
    const from = sessionStorage.getItem("chain.from");
    if (from) setChainFrom(from);
    // Read the structured context block from the previous pipeline
    const ctx = sessionStorage.getItem("chain.context_block");
    if (ctx) setChainContextBlock(ctx);
  }, [router]);

  // Restore draft on refresh
  useEffect(() => {
    if (!authChecked) return;
    try {
      // Check for chain brief first (higher priority than saved draft)
      const chainBrief = sessionStorage.getItem("chain.brief");
      if (chainBrief) {
        setBrief(chainBrief);
        sessionStorage.removeItem("chain.brief");
        sessionStorage.removeItem("chain.from");
        return; // Don't restore old draft when chaining
      }
      const raw = sessionStorage.getItem(STORAGE_KEY);
      if (!raw) return;
      const d = JSON.parse(raw) as {
        templateId?: string; designSystemId?: string; brief?: string; customDsBody?: string; customTemplateBody?: string;
      };
      if (d.templateId) setSelectedTemplateId(d.templateId);
      if (d.designSystemId) setSelectedDsId(d.designSystemId);
      if (d.brief) setBrief(d.brief);
      if (d.customDsBody) setCustomDsBody(d.customDsBody);
      if (d.customTemplateBody) setCustomTemplateBody(d.customTemplateBody);
    } catch { /* ignore */ }
  }, [authChecked]);

  useEffect(() => {
    if (!authChecked) return;
    const token = getToken();
    if (!token) return;
    let cancelled = false;

    // Fetch templates and design systems independently so one failure
    // doesn't block the other. On 401, redirect to login.
    listPrototypeTemplates(token)
      .then((t) => { if (!cancelled) setTemplates(t); })
      .catch((err: Error) => {
        if (cancelled) return;
        if (err.message.startsWith("401")) {
          router.replace("/login");
          return;
        }
        setLoadError(err.message);
      });

    listDesignSystems(token)
      .then((s) => { if (!cancelled) setSystems(s); })
      .catch((err: Error) => {
        if (cancelled) return;
        if (err.message.startsWith("401")) {
          router.replace("/login");
        }
        // Non-fatal — design system picker will just stay empty
      });

    return () => { cancelled = true; };
  }, [authChecked, router]);

  const selectedTemplate = useMemo(
    () => templates.find((t) => t.id === selectedTemplateId) ?? null,
    [templates, selectedTemplateId],
  );

  const handleSelectCustomDs = useCallback((ds: CustomDesignSystem | null) => {
    if (ds) {
      setSelectedDsId(ds.id);
      setCustomDsBody(ds.body);
    } else {
      setCustomDsBody(null);
    }
  }, []);

  const handleSelectBuiltInDs = useCallback((id: string | null) => {
    setSelectedDsId(id);
    setCustomDsBody(null); // clear custom body when switching to built-in
  }, []);

  const handleSelectCustomTemplate = useCallback((ct: CustomTemplate | null) => {
    if (ct) {
      setSelectedTemplateId(ct.id);
      setCustomTemplateBody(ct.body);
    } else {
      setSelectedTemplateId(null);
      setCustomTemplateBody(null);
    }
  }, []);

  const isChaining = Boolean(chainFrom);
  const canContinue = Boolean(
    selectedTemplateId && selectedDsId &&
    (isChaining || brief.trim())  // brief not required when chaining
  );

  const handleContinue = useCallback(() => {
    if (!canContinue) return;
    const sourceRunId = sessionStorage.getItem("chain.source_run_id") ?? undefined;
    const contextBlock = sessionStorage.getItem("chain.context_block") ?? undefined;
    sessionStorage.removeItem("chain.context_block");

    // When chaining: use context block as the brief (it contains the full topic + content).
    // When fresh: append context block to user's brief if available.
    let finalBrief: string;
    if (isChaining && contextBlock) {
      finalBrief = contextBlock;
    } else if (contextBlock && brief.trim()) {
      finalBrief = `${brief.trim()}\n\n${contextBlock}`;
    } else {
      finalBrief = brief.trim();
    }

    sessionStorage.setItem(STORAGE_KEY, JSON.stringify({
      templateId: selectedTemplateId,
      designSystemId: selectedDsId,
      brief: finalBrief,
      ...(customDsBody ? { customDsBody } : {}),
      ...(customTemplateBody ? { customTemplateBody } : {}),
      ...(sourceRunId ? { sourceRunId } : {}),
    }));
    sessionStorage.setItem("od_prototype.pending", "true");
    router.push("/dashboard");
  }, [canContinue, isChaining, selectedTemplateId, selectedDsId, brief, customDsBody, customTemplateBody, router]);

  if (!authChecked) {
    return (
      <div className="flex h-screen items-center justify-center" style={{ background: "#f5f5f0" }}>
        <div className="text-sm text-gray-500">Loading…</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen" style={{ background: "#f5f5f0" }}>
      {/* Header */}
      <header className="sticky top-0 z-20 border-b border-gray-200/70 bg-[#f5f5f0]/95 backdrop-blur">
        <div className="mx-auto flex max-w-5xl items-center gap-3 px-6 py-3.5">
          <button
            type="button"
            onClick={() => router.push("/dashboard")}
            className="flex items-center justify-center rounded-lg p-1.5 text-gray-500 transition-colors hover:bg-white hover:text-gray-900"
          >
            <ArrowLeft className="h-4 w-4" />
          </button>
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-gray-400">
              {isChaining ? "Chained prototype" : "New prototype"} · {isChaining ? "Step 1 of 1" : "Step 1 of 2"}
            </p>
            <h1
              className="text-[15px] font-normal italic text-gray-900"
              style={{ fontFamily: "var(--font-fraunces)" }}
            >
              {isChaining ? "Pick a template & design system" : "Configure your prototype"}
            </h1>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-5xl space-y-8 px-6 py-8 pb-16">

        {/* Chain context panel — shows extracted content from previous pipeline */}
        {chainFrom && chainContextBlock && (
          <div className="rounded-xl border border-emerald-200 bg-emerald-50 overflow-hidden">
            <button
              type="button"
              onClick={() => setContextExpanded(v => !v)}
              className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-emerald-100/50 transition-colors"
            >
              <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-emerald-100 flex-shrink-0">
                <Layers className="h-3.5 w-3.5 text-emerald-700" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-[12px] font-semibold text-emerald-800">
                  Context from previous pipeline
                </p>
                <p className="text-[10px] text-emerald-600 truncate">
                  {{
                    od_ppt: "Presentation slide plan", od_ppt_revision: "Presentation slide plan",
                    ppt: "Presentation slide plan", ppt_revision: "Presentation slide plan",
                    user_stories: "Product backlog", user_stories_revision: "Product backlog",
                    app_builder: "App architecture", app_builder_revision: "App architecture",
                  }[chainFrom] ?? "Previous pipeline output"} · will be passed to agents
                </p>
              </div>
              <div className="flex items-center gap-2 flex-shrink-0">
                <span className="text-[9px] bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded-full font-medium">
                  {contextExpanded ? "Hide" : "Preview"}
                </span>
                {contextExpanded
                  ? <ChevronDown className="h-4 w-4 text-emerald-600" />
                  : <ChevronRight className="h-4 w-4 text-emerald-600" />}
              </div>
            </button>
            {contextExpanded && (
              <div className="border-t border-emerald-200 px-4 py-3">
                <p className="text-[10px] font-semibold text-emerald-700 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                  <Eye className="h-3 w-3" /> What agents will receive
                </p>
                <pre className="text-[10px] text-emerald-900 whitespace-pre-wrap leading-relaxed bg-white/60 rounded-lg p-3 max-h-[200px] overflow-y-auto font-mono border border-emerald-100">
                  {chainContextBlock}
                </pre>
                <p className="text-[10px] text-emerald-600 mt-2">
                  This context is automatically appended to your brief when the pipeline runs. You can edit the brief above to add more details.
                </p>
              </div>
            )}
          </div>
        )}

        {/* Chain banner (no context yet — still loading) */}
        {chainFrom && !chainContextBlock && (
          <div className="rounded-xl border border-blue-200 bg-blue-50 px-4 py-3 flex items-center gap-3">
            <div className="flex h-6 w-6 items-center justify-center rounded-full bg-blue-100 flex-shrink-0">
              <span className="text-[11px]">→</span>
            </div>
            <p className="text-[12px] text-blue-700">
              Continuing from your <strong>{{
                od_ppt: "Presentation", od_ppt_revision: "Presentation",
                ppt: "Presentation", ppt_revision: "Presentation",
                od_prototype: "Prototype", prototype: "Prototype", prototype_revision: "Prototype",
                user_stories: "User Stories", user_stories_revision: "User Stories",
                app_builder: "App Builder", app_builder_revision: "App Builder",
              }[chainFrom] ?? chainFrom}</strong> — your brief is pre-filled.
            </p>
          </div>
        )}

        {/* ── Section 1: Brief — hidden when chaining (topic comes from previous run) */}
        {!isChaining && (
          <section>
            <SectionLabel number={1} title="Describe what you're building" />
            <div className="mt-3 rounded-2xl border border-gray-200/70 bg-white">
              <textarea
                value={brief}
                onChange={(e) => setBrief(e.target.value)}
                placeholder="e.g. A kanban board for a 5-person growth squad — backlog, doing, review, done. Show real ticket titles and assignee avatars."
                rows={5}
                className="w-full resize-none rounded-2xl bg-transparent px-5 py-4 text-[14px] leading-relaxed text-gray-900 placeholder:text-gray-400 focus:outline-none"
              />
              {selectedTemplate?.example_prompt && (
                <div className="border-t border-gray-100 px-5 py-2.5">
                  <button
                    type="button"
                    onClick={() => setBrief(selectedTemplate.example_prompt ?? "")}
                    className="inline-flex items-center gap-1.5 text-[11px] text-gray-500 hover:text-[#1B2A4A]"
                  >
                    <Sparkles className="h-3 w-3" />
                    Use template example
                    <span className="italic text-gray-400">"{selectedTemplate.example_prompt}"</span>
                  </button>
                </div>
              )}
            </div>
          </section>
        )}

        {/* ── Section 2 (or 1 when chaining): Template ──────────────────── */}
        <section>
          <SectionLabel number={isChaining ? 1 : 2} title="Choose a template" subtitle="Sets the visual DNA — chrome, layout patterns, component style." />
          <div className="mt-3">
            {loadError ? (
              <div className="rounded-2xl border border-red-200 bg-red-50 px-5 py-4 text-[13px] text-red-700">
                Couldn't load templates: {loadError}
              </div>
            ) : templates.length === 0 ? (
              <SkeletonGrid />
            ) : (
              <TemplateGallery
                templates={templates}
                selectedId={customTemplateBody ? null : selectedTemplateId}
                onSelect={(id) => { setSelectedTemplateId(id); setCustomTemplateBody(null); }}
                onSelectCustomTemplate={handleSelectCustomTemplate}
                selectedCustomTemplateId={customTemplateBody ? selectedTemplateId : null}
              />
            )}
          </div>
        </section>

        {/* ── Section 3 (or 2 when chaining): Design system ─────────────── */}
        <section>
          <SectionLabel number={isChaining ? 2 : 3} title="Choose a design system" />
          <div className="mt-3">
            {systems.length === 0 ? (
              <div className="h-48 animate-pulse rounded-2xl bg-white/60" />
            ) : (
              <DesignSystemPicker
                systems={systems}
                selectedId={selectedDsId}
                onSelect={handleSelectBuiltInDs}
                onSelectCustom={handleSelectCustomDs}
              />
            )}
          </div>
        </section>

        {/* ── Continue ───────────────────────────────────────────────────── */}
        <div className="pt-2">
          {!canContinue && (
            <div className="mb-4 flex flex-wrap gap-2">
              {!isChaining && !brief.trim() && <Pill label="Add a brief" />}
              {!selectedTemplateId && <Pill label="Pick a template" />}
              {!selectedDsId && <Pill label="Pick a design system" />}
            </div>
          )}

          <button
            type="button"
            onClick={handleContinue}
            disabled={!canContinue}
            className="flex w-full items-center justify-center gap-2 rounded-2xl bg-[#1B2A4A] px-6 py-4 text-[14px] font-semibold text-white shadow-sm transition-all hover:bg-[#0F1B33] disabled:cursor-not-allowed disabled:bg-gray-200 disabled:text-gray-400 disabled:shadow-none"
          >
            Continue
            <ArrowRight className="h-4 w-4" />
          </button>

          {canContinue && (
            <p className="mt-2 text-center text-[11px] text-gray-500">
              {customTemplateBody ? "Custom template" : selectedTemplate?.name} template · {customDsBody ? "Custom design system" : selectedDsId}
            </p>
          )}
        </div>

      </main>
    </div>
  );
}

function SectionLabel({ number, title, subtitle }: { number: number; title: string; subtitle?: string }) {
  return (
    <div className="flex items-start gap-3">
      <div className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full bg-[#1B2A4A]/10 text-[11px] font-bold text-[#1B2A4A]">
        {number}
      </div>
      <div>
        <h2 className="text-[14px] font-semibold text-gray-900">{title}</h2>
        {subtitle && <p className="mt-0.5 text-[12px] text-gray-500">{subtitle}</p>}
      </div>
    </div>
  );
}

function Pill({ label }: { label: string }) {
  return (
    <span className="inline-flex items-center rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-[11px] font-medium text-amber-700">
      {label}
    </span>
  );
}

function SkeletonGrid() {
  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
      {Array.from({ length: 8 }).map((_, i) => (
        <div key={i} className="overflow-hidden rounded-xl border border-gray-200 bg-white">
          <div className="h-40 animate-pulse bg-gray-100" />
          <div className="space-y-1.5 px-3.5 py-3">
            <div className="h-3 w-2/3 animate-pulse rounded bg-gray-100" />
            <div className="h-2.5 w-full animate-pulse rounded bg-gray-100" />
          </div>
        </div>
      ))}
    </div>
  );
}
