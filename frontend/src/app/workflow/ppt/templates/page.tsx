"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, ArrowRight, Sparkles } from "lucide-react";
import { getToken } from "@/lib/api";
import { listPPTTemplates, type PPTTemplate } from "@/lib/ppt-api";
import { listDesignSystems, type DesignSystemListItem } from "@/lib/prototype-api";
import { PPTTemplateGallery } from "@/components/workflow/ppt/PPTTemplateGallery";
import { DesignSystemPicker } from "@/components/workflow/prototype/DesignSystemPicker";
import type { CustomDesignSystem } from "@/components/workflow/prototype/CustomDesignSystemModal";
import type { CustomTemplate } from "@/components/workflow/prototype/CustomTemplateModal";

const STORAGE_KEY = "ppt.draft";

export default function PPTTemplatesPage() {
  const router = useRouter();

  const [authChecked, setAuthChecked] = useState(false);
  const [templates, setTemplates] = useState<PPTTemplate[]>([]);
  const [systems, setSystems] = useState<DesignSystemListItem[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [selectedTemplateId, setSelectedTemplateId] = useState<string | null>(null);
  const [selectedDsId, setSelectedDsId] = useState<string | null>(null);
  const [customDsBody, setCustomDsBody] = useState<string | null>(null);
  const [customTemplateBody, setCustomTemplateBody] = useState<string | null>(null);
  const [brief, setBrief] = useState("");

  const [chainFrom, setChainFrom] = useState<string | null>(null);

  useEffect(() => {
    const token = getToken();
    if (!token) { router.replace("/login"); return; }
    setAuthChecked(true);
    const from = sessionStorage.getItem("chain.from");
    if (from) setChainFrom(from);
  }, [router]);

  // Restore draft
  useEffect(() => {
    if (!authChecked) return;
    try {
      // Check for chain brief first (higher priority than saved draft)
      const chainBrief = sessionStorage.getItem("chain.brief");
      if (chainBrief) {
        setBrief(chainBrief);
        sessionStorage.removeItem("chain.brief");
        sessionStorage.removeItem("chain.from");
        return;
      }
      const raw = sessionStorage.getItem(STORAGE_KEY);
      if (!raw) return;
      const d = JSON.parse(raw) as {
        templateId?: string; designSystemId?: string; brief?: string;
        customDsBody?: string; customTemplateBody?: string;
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

    listPPTTemplates(token)
      .then((t) => { if (!cancelled) setTemplates(t); })
      .catch((err: Error) => {
        if (cancelled) return;
        if (err.message.startsWith("401")) { router.replace("/login"); return; }
        setLoadError(err.message);
      });

    listDesignSystems(token)
      .then((s) => { if (!cancelled) setSystems(s); })
      .catch(() => { /* non-fatal */ });

    return () => { cancelled = true; };
  }, [authChecked, router]);

  const selectedTemplate = useMemo(
    () => templates.find((t) => t.id === selectedTemplateId) ?? null,
    [templates, selectedTemplateId],
  );

  // Design system is only required for templates that declare it
  const dsRequired = selectedTemplate?.design_system?.requires === true;

  const handleSelectCustomDs = useCallback((ds: CustomDesignSystem | null) => {
    if (ds) { setSelectedDsId(ds.id); setCustomDsBody(ds.body); }
    else { setCustomDsBody(null); }
  }, []);

  const handleSelectBuiltInDs = useCallback((id: string | null) => {
    setSelectedDsId(id);
    setCustomDsBody(null);
  }, []);

  const handleSelectCustomTemplate = useCallback((ct: CustomTemplate | null) => {
    if (ct) { setSelectedTemplateId(ct.id); setCustomTemplateBody(ct.body); }
    else { setSelectedTemplateId(null); setCustomTemplateBody(null); }
  }, []);

  // canContinue: DS only required when template declares it
  const canContinue = Boolean(
    selectedTemplateId && brief.trim() &&
    (!dsRequired || selectedDsId),
  );

  const handleContinue = useCallback(() => {
    if (!canContinue) return;
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify({
      templateId: selectedTemplateId,
      designSystemId: dsRequired ? selectedDsId : null,
      brief: brief.trim(),
      ...(customDsBody ? { customDsBody } : {}),
      ...(customTemplateBody ? { customTemplateBody } : {}),
    }));
    sessionStorage.setItem("od_ppt.pending", "true");
    router.push("/dashboard");
  }, [canContinue, selectedTemplateId, selectedDsId, dsRequired, brief, customDsBody, customTemplateBody, router]);

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
          <button type="button" onClick={() => router.push("/dashboard")}
            className="flex items-center justify-center rounded-lg p-1.5 text-gray-500 transition-colors hover:bg-white hover:text-gray-900">
            <ArrowLeft className="h-4 w-4" />
          </button>
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-gray-400">
              New presentation · Step 1 of 2
            </p>
            <h1 className="text-[15px] font-normal italic text-gray-900"
              style={{ fontFamily: "var(--font-fraunces)" }}>
              Configure your presentation
            </h1>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-5xl space-y-8 px-6 py-8 pb-16">

        {/* Chain context banner */}
        {chainFrom && (
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
              }[chainFrom] ?? chainFrom}</strong> — your brief is pre-filled. Pick a template to generate the presentation.
            </p>
          </div>
        )}

        {/* Section 1: Brief */}
        <section>
          <SectionLabel number={1} title="Describe your presentation" />
          <div className="mt-3 rounded-2xl border border-gray-200/70 bg-white">
            <textarea
              value={brief} onChange={(e) => setBrief(e.target.value)}
              placeholder="e.g. A pitch deck for our Series A fundraise — $5M ask, B2B SaaS, 10 slides for investors."
              rows={5}
              className="w-full resize-none rounded-2xl bg-transparent px-5 py-4 text-[14px] leading-relaxed text-gray-900 placeholder:text-gray-400 focus:outline-none"
            />
            {selectedTemplate?.example_prompt && (
              <div className="border-t border-gray-100 px-5 py-2.5">
                <button type="button" onClick={() => setBrief(selectedTemplate.example_prompt ?? "")}
                  className="inline-flex items-center gap-1.5 text-[11px] text-gray-500 hover:text-[#1B2A4A]">
                  <Sparkles className="h-3 w-3" />
                  Use template example
                  <span className="italic text-gray-400">"{selectedTemplate.example_prompt}"</span>
                </button>
              </div>
            )}
          </div>
        </section>

        {/* Section 2: Template */}
        <section>
          <SectionLabel number={2} title="Choose a deck template"
            subtitle="Sets the visual style — layouts, themes, animation, and slide structure." />
          <div className="mt-3">
            {loadError ? (
              <div className="rounded-2xl border border-red-200 bg-red-50 px-5 py-4 text-[13px] text-red-700">
                Couldn't load templates: {loadError}
              </div>
            ) : templates.length === 0 ? (
              <SkeletonGrid />
            ) : (
              <PPTTemplateGallery
                templates={templates}
                selectedId={customTemplateBody ? null : selectedTemplateId}
                onSelect={(id) => { setSelectedTemplateId(id); setCustomTemplateBody(null); }}
                onSelectCustomTemplate={handleSelectCustomTemplate}
                selectedCustomTemplateId={customTemplateBody ? selectedTemplateId : null}
              />
            )}
          </div>
        </section>

        {/* Section 3: Design system — only shown when template requires it */}
        {dsRequired && (
          <section>
            <SectionLabel number={3} title="Choose a design system"
              subtitle="This template uses your design system's tokens for colors and typography." />
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
        )}

        {/* Continue */}
        <div className="pt-2">
          {!canContinue && (
            <div className="mb-4 flex flex-wrap gap-2">
              {!brief.trim() && <Pill label="Add a brief" />}
              {!selectedTemplateId && <Pill label="Pick a template" />}
              {dsRequired && !selectedDsId && <Pill label="Pick a design system" />}
            </div>
          )}
          <button type="button" onClick={handleContinue} disabled={!canContinue}
            className="flex w-full items-center justify-center gap-2 rounded-2xl bg-[#1B2A4A] px-6 py-4 text-[14px] font-semibold text-white shadow-sm transition-all hover:bg-[#0F1B33] disabled:cursor-not-allowed disabled:bg-gray-200 disabled:text-gray-400 disabled:shadow-none">
            Continue
            <ArrowRight className="h-4 w-4" />
          </button>
          {canContinue && (
            <p className="mt-2 text-center text-[11px] text-gray-500">
              {customTemplateBody ? "Custom template" : selectedTemplate?.name}
              {dsRequired && selectedDsId && ` · ${customDsBody ? "Custom design system" : selectedDsId}`}
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
