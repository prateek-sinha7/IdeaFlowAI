"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowRight, Sparkles, ChevronDown, ChevronRight, Layers, Eye, Paperclip,
  Mic, MicOff, X, File, Settings2, Save, Image as ImageIcon, ArrowLeft,
} from "lucide-react";
import { getToken, extractFileText, createUserWorkflow } from "@/lib/api";
import { ATTACH_MAX_CHARS } from "@/lib/constants";
import {
  listDesignSystems,
  listPrototypeTemplates,
  type DesignSystemListItem,
  type PrototypeTemplate,
} from "@/lib/prototype-api";
import { listPPTTemplates, type PPTTemplate } from "@/lib/ppt-api";
import { WizardStepper } from "@/components/workflow/WizardStepper";
import { DesignSystemPicker } from "@/components/workflow/prototype/DesignSystemPicker";
import {
  DiscoveryForm,
  EMPTY_ANSWERS,
  type DiscoveryAnswers,
} from "@/components/workflow/prototype/DiscoveryForm";
import { ReviewGatesSection } from "@/components/workflow/ReviewGatesSection";
import { AgentsPopup } from "@/components/workflow/AgentsPopup";
import { useAgentLibrary } from "@/hooks/useAgentLibrary";
import { useSpeechRecognition } from "@/hooks/useSpeechRecognition";
import { NameWorkflowModal } from "@/components/catalog/NameWorkflowModal";
import {
  buildLaunchDraft,
  buildDiscoveryValue,
  DISCOVERY_KEY,
  type LaunchMode,
} from "@/lib/launchDraft";
import type { CustomDesignSystem } from "@/components/workflow/prototype/CustomDesignSystemModal";
import type { CustomTemplate } from "@/components/workflow/prototype/CustomTemplateModal";
import type { AgentDef } from "@/types/index";
import { collectAgentIds, instantiateIfTemplate } from "@/store/api/userWorkflows";

/**
 * LaunchWizard (plan 37-07) — the ONE unified deliverable-launch page. It
 * replaces the two retired route-split pages (prototype/templates +
 * ppt/templates), hosting the WizardStepper chrome (Template → Design System →
 * Discovery + a Web/Deck toggle) and wrapping it with the brief, review gates,
 * agent composer, save-workflow, and launch affordances.
 *
 * SC-001 / INV-1: the page is keyed on a GENERIC `mode` value
 * ("prototype" | "ppt") — the deliverable family the Web/Deck toggle switches —
 * NEVER a per-workflow-name branch. Every mode difference is expressed as data
 * in MODE_CONFIG or the launch-contract library (buildLaunchDraft), so the
 * wizard→dashboard hand-off is byte-identical to the retired flow (proven by
 * the launch-contract parity gate).
 *
 * All colours route through the @theme token layer; NO retired palette.
 */

/** The Web/Deck stepper toggle value ↔ the deliverable mode. */
const STEPPER_MODE: Record<LaunchMode, "web" | "deck"> = { prototype: "web", ppt: "deck" };
function modeFromStepper(m: "web" | "deck"): LaunchMode {
  return m === "web" ? "prototype" : "ppt";
}

interface ModeConfig {
  /** AgentLibraryData `pipeline_type` for the default lineup. */
  agentPipeline: "prototype" | "ppt";
  /** `base_pipeline_type` sent to POST /api/user-workflows on Save. */
  savePipeline: "od_prototype" | "od_ppt";
  title: string;
  chainingTitle: string;
  eyebrow: string;
  chainingEyebrow: string;
  placeholder: string;
  briefLabel: string;
  saveTitle: string;
}

const MODE_CONFIG: Record<LaunchMode, ModeConfig> = {
  prototype: {
    agentPipeline: "prototype",
    savePipeline: "od_prototype",
    title: "Configure your prototype",
    chainingTitle: "Pick a template & design system",
    eyebrow: "New prototype",
    chainingEyebrow: "Chained prototype",
    placeholder:
      "e.g. A kanban board for a 5-person growth squad — backlog, doing, review, done. Show real ticket titles and assignee avatars.",
    briefLabel: "Describe what you're building",
    saveTitle: "Save prototype workflow",
  },
  ppt: {
    agentPipeline: "ppt",
    savePipeline: "od_ppt",
    title: "Configure your presentation",
    chainingTitle: "Pick a template",
    eyebrow: "New presentation",
    chainingEyebrow: "Chained presentation",
    placeholder:
      "e.g. A pitch deck for our Series A fundraise — $5M ask, B2B SaaS, 10 slides for investors.",
    briefLabel: "Describe your presentation",
    saveTitle: "Save presentation workflow",
  },
};

/** Copy for the chain context/banner, keyed on the source pipeline (data map). */
const CHAIN_SOURCE_LABEL: Record<string, string> = {
  ppt: "Presentation", ppt_revision: "Presentation",
  prototype: "Prototype", prototype_revision: "Prototype",
  user_stories: "User Stories", user_stories_revision: "User Stories",
  app_builder: "App Builder", app_builder_revision: "App Builder",
};

const defaultAgentsFor = (libraryAgents: AgentDef[], mode: LaunchMode): AgentDef[] =>
  libraryAgents.filter((a) => a.pipeline_type === MODE_CONFIG[mode].agentPipeline).sort(
    (a, b) => a.order - b.order,
  );

export interface LaunchWizardProps {
  /** The deliverable family to launch, from the generic `?mode=` route param. */
  initialMode: LaunchMode;
}

export function LaunchWizard({ initialMode }: LaunchWizardProps) {
  const router = useRouter();
  const { libraryAgents } = useAgentLibrary();

  const [authChecked, setAuthChecked] = useState(false);
  const [mode, setMode] = useState<LaunchMode>(initialMode);
  // Chrome (title/eyebrow/brief label/placeholder/save-modal title) MUST track the
  // LIVE mode, not the immutable initialMode — the Web/Deck toggle switches families
  // in-page, and freezing chrome to initialMode mislabels a deck as a prototype.
  const cfg = MODE_CONFIG[mode];

  // ── Template registries (both families fetched so the toggle just swaps). ──
  const [webTemplates, setWebTemplates] = useState<PrototypeTemplate[]>([]);
  const [deckTemplates, setDeckTemplates] = useState<PPTTemplate[]>([]);
  const [systems, setSystems] = useState<DesignSystemListItem[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

  // ── Selection state. Template is per-mode (the toggle preserves nothing:
  //    switching families is a fresh deliverable choice), so it resets on
  //    switch alongside the agent lineup + levers. DS/brief/files/images/
  //    discovery are shared inputs that carry across a toggle. ──
  const [selectedTemplateId, setSelectedTemplateId] = useState<string | null>(null);
  const [customTemplateBody, setCustomTemplateBody] = useState<string | null>(null);
  const [selectedDsId, setSelectedDsId] = useState<string | null>(null);
  const [customDsBody, setCustomDsBody] = useState<string | null>(null);
  const [brief, setBrief] = useState("");
  const [discoveryAnswers, setDiscoveryAnswers] = useState<DiscoveryAnswers>(EMPTY_ANSWERS);

  const [attachedFiles, setAttachedFiles] = useState<{ name: string; size: string }[]>([]);
  // KAN-91: file content stored separately so the textarea stays clean.
  const [attachedFileContents, setAttachedFileContents] = useState<{ name: string; content: string }[]>([]);
  // Image-input Wave 2 (D3): images ride OUT-OF-BAND via the draft `images`
  // field — SEPARATE from attachedFileContents (which is inlined into the brief).
  const [attachedImages, setAttachedImages] = useState<{ name: string; mime_type: string; data: string }[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const preSpeechTextRef = useRef("");
  const { isListening, transcript, startListening, stopListening, isSupported: speechSupported } =
    useSpeechRecognition();

  const [chainFrom, setChainFrom] = useState<string | null>(null);
  const [chainContextBlock, setChainContextBlock] = useState<string | null>(null);
  const [contextExpanded, setContextExpanded] = useState(false);
  const [showAgents, setShowAgents] = useState(false);

  const [pipelineAgents, setPipelineAgents] = useState<AgentDef[]>(() => defaultAgentsFor(libraryAgents, initialMode));

  const selectionsRef = useRef<Record<string, Record<string, unknown>>>({});
  const gateSelectionRef = useRef<{ ids: string[]; touched: boolean }>({ ids: [], touched: false });

  // Save-workflow state.
  const [showSaveModal, setShowSaveModal] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [savedConfirm, setSavedConfirm] = useState(false);

  const isChaining = Boolean(chainFrom);

  // Auth + chain pickup (mirrors the retired pages).
  useEffect(() => {
    const token = getToken();
    if (!token) { router.replace("/login"); return; }
    setAuthChecked(true);
    const from = sessionStorage.getItem("chain.from");
    if (from) {
      setChainFrom(from);
      sessionStorage.removeItem("chain.from");
    }
    const ctx = sessionStorage.getItem("chain.context_block");
    if (ctx) setChainContextBlock(ctx);
  }, [router]);

  // Restore the draft the dashboard/Saved-workflow hand-off wrote for THIS mode,
  // then clear it (FIX-005: one-shot, so a fresh open never pre-fills stale data).
  useEffect(() => {
    if (!authChecked) return;
    try {
      const chainBrief = sessionStorage.getItem("chain.brief");
      if (chainBrief) {
        setBrief(chainBrief);
        sessionStorage.removeItem("chain.brief");
        sessionStorage.removeItem("chain.from");
        return;
      }
      const draftKey = initialMode === "prototype" ? "prototype.draft" : "ppt.draft";
      const raw = sessionStorage.getItem(draftKey);
      if (!raw) return;
      const d = JSON.parse(raw) as {
        templateId?: string; designSystemId?: string | null; brief?: string;
        customDsBody?: string; customTemplateBody?: string;
        agentIds?: string[]; gateAgentIds?: string[];
        selections?: Record<string, Record<string, unknown>>;
      };
      if (d.templateId) setSelectedTemplateId(d.templateId);
      if (d.designSystemId) setSelectedDsId(d.designSystemId);
      if (d.brief) setBrief(d.brief);
      if (d.customDsBody) setCustomDsBody(d.customDsBody);
      if (d.customTemplateBody) setCustomTemplateBody(d.customTemplateBody);
      if (d.agentIds && d.agentIds.length > 0) {
        const restored = d.agentIds
          .map((id) => libraryAgents.find((a) => a.id === id))
          .filter(Boolean) as AgentDef[];
        if (restored.length > 0) setPipelineAgents(restored);
      }
      if (d.selections) selectionsRef.current = d.selections;
      if (d.gateAgentIds !== undefined) gateSelectionRef.current = { ids: d.gateAgentIds, touched: true };
      sessionStorage.removeItem(draftKey);
    } catch { /* ignore malformed session data */ }
  }, [authChecked, initialMode]);

  // Load both template families + the design-system registry once authed.
  useEffect(() => {
    if (!authChecked) return;
    const token = getToken();
    if (!token) return;
    let cancelled = false;

    listPrototypeTemplates(token)
      .then((t) => { if (!cancelled) setWebTemplates(t); })
      .catch((err: Error) => {
        if (cancelled) return;
        if (err.message.startsWith("401")) { router.replace("/login"); return; }
        setLoadError(err.message);
      });
    listPPTTemplates(token)
      .then((t) => { if (!cancelled) setDeckTemplates(t); })
      .catch((err: Error) => {
        if (cancelled) return;
        if (err.message.startsWith("401")) { router.replace("/login"); }
      });
    listDesignSystems(token)
      .then((s) => {
        if (!cancelled) {
          setSystems(s);
          // FIX-103: Auto-select "Design System Inspired by Apple" on a fresh
          // prototype launch. Only fires when no DS has been selected yet (null)
          // so draft-restored selections and user choices are never overwritten.
          // Gracefully skips if "apple" is not in the loaded list.
          setSelectedDsId((prev) => {
            if (prev !== null) return prev; // preserve draft / user selection
            if (mode !== "prototype") return prev;
            return s.some((ds) => ds.id === "apple") ? "apple" : prev;
          });
        }
      })
      .catch(() => { /* non-fatal — the picker stays empty */ });

    return () => { cancelled = true; };
  }, [authChecked, router]);

  // Mirror speech transcript into the brief textarea (same pattern as the pages).
  useEffect(() => {
    if (transcript) {
      setBrief(preSpeechTextRef.current + (preSpeechTextRef.current ? " " : "") + transcript);
    }
  }, [transcript]);

  const selectedDeckTemplate = useMemo(
    () => deckTemplates.find((t) => t.id === selectedTemplateId) ?? null,
    [deckTemplates, selectedTemplateId],
  );
  const selectedWebTemplate = useMemo(
    () => webTemplates.find((t) => t.id === selectedTemplateId) ?? null,
    [webTemplates, selectedTemplateId],
  );
  // ppt design system is only required for templates that declare it.
  const dsRequired = mode === "ppt" && selectedDeckTemplate?.design_system?.requires === true;
  const dsVisible = mode === "prototype" || dsRequired;

  const examplePrompt =
    mode === "prototype" ? selectedWebTemplate?.example_prompt : selectedDeckTemplate?.example_prompt;

  // Optional-agent budget (defaults are free; up to 5 extra), per active lineup.
  const defaultAgentIds = useMemo(
    () => new Set(defaultAgentsFor(libraryAgents, mode).map((a) => a.id)),
    [libraryAgents, mode],
  );
  const optionalAgentCount = pipelineAgents.filter((a) => !defaultAgentIds.has(a.id)).length;
  const canAddMore = optionalAgentCount < 5;

  const handleModeChange = useCallback((next: "web" | "deck") => {
    const nextMode = modeFromStepper(next);
    setMode(nextMode);
    // Switching deliverable family is a fresh choice: reset the family-specific
    // selection + lineup + levers; shared inputs (brief/DS/files/images) persist.
    setSelectedTemplateId(null);
    setCustomTemplateBody(null);
    setPipelineAgents(defaultAgentsFor(libraryAgents, nextMode));
    selectionsRef.current = {};
    gateSelectionRef.current = { ids: [], touched: false };
  }, [libraryAgents]);

  const handleAddAgent = useCallback((agent: AgentDef) => {
    setPipelineAgents((prev) => {
      // Reusable blank template — mint a fresh instance id per add (R-03).
      const node = instantiateIfTemplate(agent, collectAgentIds(prev));
      if (prev.find((a) => a.id === node.id)) return prev;
      if (prev.filter((a) => !defaultAgentIds.has(a.id)).length >= 5) return prev;
      const insertIdx = prev.length > 0 ? prev.length - 1 : 0;
      const updated = [...prev];
      updated.splice(insertIdx, 0, { ...node, order: insertIdx + 1 });
      return updated;
    });
  }, [defaultAgentIds]);

  const handleRemoveAgent = useCallback((agentId: string) => {
    setPipelineAgents((prev) => prev.filter((a) => a.id !== agentId));
  }, []);

  const handleReorderAgents = useCallback((reordered: AgentDef[]) => {
    setPipelineAgents(reordered);
  }, []);

  const handleSelectionsChange = useCallback((s: Record<string, Record<string, unknown>>) => {
    selectionsRef.current = s;
  }, []);
  const handleGatesChange = useCallback((ids: string[], touched: boolean) => {
    gateSelectionRef.current = { ids, touched };
  }, []);

  const handleSelectTemplate = useCallback((id: string | null) => {
    setSelectedTemplateId(id);
    setCustomTemplateBody(null);
  }, []);
  const handleSelectCustomTemplate = useCallback((ct: CustomTemplate | null) => {
    if (ct) { setSelectedTemplateId(ct.id); setCustomTemplateBody(ct.body); }
    else { setSelectedTemplateId(null); setCustomTemplateBody(null); }
  }, []);
  const handleSelectBuiltInDs = useCallback((id: string | null) => {
    setSelectedDsId(id);
    setCustomDsBody(null);
  }, []);
  const handleSelectCustomDs = useCallback((ds: CustomDesignSystem | null) => {
    if (ds) { setSelectedDsId(ds.id); setCustomDsBody(ds.body); }
    else { setCustomDsBody(null); }
  }, []);

  const removeFile = useCallback((idx: number) => {
    setAttachedFiles((prev) => {
      const removedName = prev[idx]?.name;
      if (removedName) setAttachedFileContents((c) => c.filter((f) => f.name !== removedName));
      return prev.filter((_, i) => i !== idx);
    });
  }, []);

  const onFilesPicked = useCallback((files: FileList) => {
    Array.from(files).forEach((f) => {
      const isImageFile =
        ["image/png", "image/jpeg", "image/webp", "image/gif"].includes(f.type) ||
        /\.(png|jpe?g|webp|gif)$/i.test(f.name);
      if (isImageFile) {
        const reader = new FileReader();
        reader.onload = (ev) => {
          const result = (ev.target?.result as string) ?? "";
          const rawBase64 = result.replace(/^data:[^;]+;base64,/, "");
          setAttachedImages((p) => [...p, { name: f.name, mime_type: f.type || "image/png", data: rawBase64 }]);
        };
        reader.readAsDataURL(f);
        return;
      }
      const meta = {
        name: f.name,
        size: f.size < 1024 ? `${f.size}B` : f.size < 1048576 ? `${(f.size / 1024).toFixed(1)}KB` : `${(f.size / 1048576).toFixed(1)}MB`,
      };
      setAttachedFiles((p) => [...p, meta]);
      const isTextFile = /\.(txt|md|json|csv)$/i.test(f.name);
      const isBinaryFile = /\.(pdf|docx|pptx)$/i.test(f.name);
      if (isTextFile) {
        const reader = new FileReader();
        reader.onload = (ev) => {
          const content = (ev.target?.result as string) ?? "";
          setAttachedFileContents((p) => [...p, { name: f.name, content: content.slice(0, ATTACH_MAX_CHARS) }]);
        };
        reader.readAsText(f);
      } else if (isBinaryFile) {
        const jwt = getToken();
        if (jwt) {
          extractFileText(jwt, f)
            .then((res) => {
              const truncNote = res.truncated ? `\n[Content truncated to ${ATTACH_MAX_CHARS.toLocaleString()} chars]` : "";
              setAttachedFileContents((p) => [...p, { name: res.filename, content: `${res.text}${truncNote}` }]);
            })
            .catch(() => {
              setAttachedFileContents((p) => [...p, { name: f.name, content: "[could not extract text]" }]);
            });
        } else {
          setAttachedFileContents((p) => [...p, { name: f.name, content: "" }]);
        }
      }
    });
  }, []);

  // ISS-155: validate what `handleLaunch` ACTUALLY consumes, not a proxy for it.
  // The previous form was `isChaining || brief.trim()` — chaining WAIVED the brief
  // on the assumption a chain context block would stand in for it, but nothing ever
  // checked that the block exists. `DashboardLayout` swallows a failed
  // `getChainContext` as non-fatal and (FIX-217) now clears `chain.context_block`
  // up front, so "chaining with no context block" is reachable — and `handleLaunch`
  // then falls through to `brief.trim()`, the empty string. Requiring the union of
  // the two things `handleLaunch` reads keeps dev's UX goal (no brief needed when
  // chaining WORKS) while closing the briefless launch.
  const hasBuildInput = Boolean(brief.trim() || chainContextBlock?.trim());

  const canContinue = useMemo(() => {
    if (mode === "prototype") {
      // KAN-87: template optional; DS required (color tokens).
      return Boolean(selectedDsId && hasBuildInput);
    }
    // ppt: template required; DS only when the template declares it.
    return Boolean(selectedTemplateId && hasBuildInput && (!dsRequired || selectedDsId));
  }, [mode, selectedDsId, selectedTemplateId, dsRequired, hasBuildInput]);

  const handleSaveWorkflow = useCallback(async (name: string, description: string) => {
    setShowSaveModal(false);
    setSaveError(null);
    const jwt = getToken();
    if (!jwt) { setSaveError("Not authenticated."); return; }
    const sel = selectionsRef.current;
    const { ids: gateAgentIds, touched: gatesTouched } = gateSelectionRef.current;
    const wizardConfig: Record<string, unknown> = {
      templateId: selectedTemplateId,
      designSystemId: mode === "ppt" ? (dsRequired ? selectedDsId : null) : selectedDsId,
      brief,
      ...(gatesTouched ? { gateAgentIds } : {}),
      ...(customDsBody ? { customDsBody } : {}),
      ...(customTemplateBody ? { customTemplateBody } : {}),
    };
    try {
      await createUserWorkflow(jwt, {
        name,
        description: description || undefined,
        base_pipeline_type: MODE_CONFIG[mode].savePipeline,
        agent_ids: pipelineAgents.map((a) => a.id),
        selections: { ...sel, _wizard: wizardConfig },
      });
      setSavedConfirm(true);
      setTimeout(() => setSavedConfirm(false), 2500);
    } catch (e) {
      setSaveError((e as Error)?.message ?? "Failed to save workflow.");
    }
  }, [mode, selectedTemplateId, selectedDsId, dsRequired, brief, customDsBody, customTemplateBody, pipelineAgents]);

  const handleLaunch = useCallback(() => {
    if (!canContinue) return;
    const sourceRunId = isChaining ? (sessionStorage.getItem("chain.source_run_id") ?? undefined) : undefined;
    sessionStorage.removeItem("chain.source_run_id");
    const contextBlock = sessionStorage.getItem("chain.context_block") ?? undefined;
    sessionStorage.removeItem("chain.context_block");

    let finalBrief: string;
    if (isChaining && contextBlock) finalBrief = contextBlock;
    else if (contextBlock && brief.trim()) finalBrief = `${brief.trim()}\n\n${contextBlock}`;
    else finalBrief = brief.trim();

    const fileBlocks = attachedFileContents
      .map((f) => `\n\n=== Attached: ${f.name} ===\n${f.content}\n=== End: ${f.name} ===`)
      .join("");
    if (fileBlocks) finalBrief = `${finalBrief}${fileBlocks}`;

    const { ids: gateAgentIds, touched: gatesTouched } = gateSelectionRef.current;
    const designSystemId = mode === "ppt" ? (dsRequired ? selectedDsId : null) : selectedDsId;

    const draft = buildLaunchDraft(mode, {
      templateId: selectedTemplateId,
      designSystemId,
      brief: finalBrief,
      customDsBody,
      customTemplateBody,
      sourceRunId,
      gateAgentIds,
      gatesTouched,
      selections: selectionsRef.current,
      images: attachedImages,
      agentIds: pipelineAgents.map((a) => a.id),
    });

    sessionStorage.setItem(draft.draftKey, draft.draftJson);
    // Prototype discovery hand-off — write the answers, or clear the key so no
    // stale answers leak; ppt has no discovery step.
    if (mode === "prototype") {
      const discovery = buildDiscoveryValue(discoveryAnswers);
      if (discovery) sessionStorage.setItem(DISCOVERY_KEY, discovery);
      else sessionStorage.removeItem(DISCOVERY_KEY);
    }
    sessionStorage.setItem(draft.pendingKey, "true");
    router.push("/dashboard");
  }, [
    canContinue, mode, isChaining, brief, attachedFileContents, attachedImages,
    dsRequired, selectedDsId, selectedTemplateId, customDsBody, customTemplateBody,
    discoveryAnswers, pipelineAgents, router,
  ]);

  if (!authChecked) {
    return (
      <div className="flex h-screen items-center justify-center bg-surface-paper">
        <div className="text-[13px] text-ink-500">Loading…</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-surface-paper">
      <header className="sticky top-0 z-20 border-b border-line-border bg-surface-paper/95 backdrop-blur">
        <div className="mx-auto flex max-w-5xl items-center gap-3 px-6 py-3.5">
          <button
            type="button"
            onClick={() => router.push("/dashboard")}
            aria-label="Back to dashboard"
            className="flex items-center justify-center rounded-[var(--radius-button)] p-1.5 text-ink-500 transition-colors hover:bg-surface-white hover:text-ink-900"
          >
            <ArrowLeft className="h-4 w-4" />
          </button>
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-ink-400">
              {isChaining ? cfg.chainingEyebrow : cfg.eyebrow}
            </p>
            <h1 className="font-serif text-[15px] font-normal italic text-ink-900">
              {isChaining ? cfg.chainingTitle : cfg.title}
            </h1>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-5xl space-y-8 px-6 py-8 pb-16">
        {/* Chain context panel — expandable preview of the upstream output. */}
        {chainFrom && chainContextBlock && (
          <div className="overflow-hidden rounded-[var(--radius-card)] border border-[var(--status-done-border)] bg-[var(--status-done-fill)]">
            <button
              type="button"
              onClick={() => setContextExpanded((v) => !v)}
              aria-expanded={contextExpanded}
              className="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-[var(--status-done-fill)]"
            >
              <div className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-[var(--radius-button)] bg-surface-white">
                <Layers className="h-3.5 w-3.5 text-status-done" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-[12px] font-semibold text-status-done">Context from previous pipeline</p>
                <p className="truncate text-[10px] text-status-done/80">
                  {CHAIN_SOURCE_LABEL[chainFrom] ?? "Previous pipeline output"} · will be passed to agents
                </p>
              </div>
              <div className="flex flex-shrink-0 items-center gap-2">
                <span className="rounded-[var(--radius-pill)] bg-surface-white px-2 py-0.5 text-[9px] font-medium text-status-done">
                  {contextExpanded ? "Hide" : "Preview"}
                </span>
                {contextExpanded ? (
                  <ChevronDown className="h-4 w-4 text-status-done" />
                ) : (
                  <ChevronRight className="h-4 w-4 text-status-done" />
                )}
              </div>
            </button>
            {contextExpanded && (
              <div className="border-t border-[var(--status-done-border)] px-4 py-3">
                <p className="mb-2 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-status-done">
                  <Eye className="h-3 w-3" /> What agents will receive
                </p>
                <pre className="max-h-[200px] overflow-y-auto whitespace-pre-wrap rounded-[var(--radius-button)] border border-[var(--status-done-border)] bg-surface-white/60 p-3 font-mono text-[10px] leading-relaxed text-ink-800">
                  {chainContextBlock}
                </pre>
                <p className="mt-2 text-[10px] text-status-done/80">
                  This context is automatically appended to your brief when the pipeline runs.
                </p>
              </div>
            )}
          </div>
        )}

        {/* Chain banner (context still loading). */}
        {chainFrom && !chainContextBlock && (
          <div className="flex items-center gap-3 rounded-[var(--radius-card)] border border-[var(--status-running-border)] bg-[var(--status-running-fill)] px-4 py-3">
            <div className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-[var(--radius-pill)] bg-surface-white">
              <span className="text-[11px] text-status-running">→</span>
            </div>
            <p className="text-[12px] text-status-running">
              Continuing from your <strong>{CHAIN_SOURCE_LABEL[chainFrom] ?? chainFrom}</strong> — your brief is pre-filled.
            </p>
          </div>
        )}

        {/* ── Brief (hidden when chaining — topic comes from the previous run). ── */}
        {!isChaining && (
          <section>
            <SectionLabel title={cfg.briefLabel} />
            <div className="mt-3 rounded-[var(--radius-card)] border border-line-border bg-surface-white">
              <textarea
                value={brief}
                onChange={(e) => setBrief(e.target.value)}
                name="brief"
                aria-label="Brief"
                placeholder={isListening ? "Listening... speak your idea" : cfg.placeholder}
                rows={5}
                className="w-full resize-none rounded-[var(--radius-card)] bg-transparent px-5 py-4 text-[14px] leading-relaxed text-ink-900 placeholder:text-ink-400 focus:outline-none"
              />
              {attachedFiles.length > 0 && (
                <div className="flex flex-wrap gap-1.5 px-5 pb-2">
                  {attachedFiles.map((file, idx) => (
                    <span key={`${file.name}-${idx}`} className="inline-flex items-center gap-1 rounded-[var(--radius-button)] bg-surface-warm px-2.5 py-1 text-[10px] text-ink-600">
                      <File className="h-2.5 w-2.5" /> {file.name}
                      <button onClick={() => removeFile(idx)} aria-label={`Remove ${file.name}`} className="ml-1 text-ink-400 hover:text-status-failed">
                        <X className="h-2.5 w-2.5" />
                      </button>
                    </span>
                  ))}
                </div>
              )}
              {attachedImages.length > 0 && (
                <div className="flex flex-wrap gap-1.5 px-5 pb-2">
                  {attachedImages.map((img, idx) => (
                    <span key={`${img.name}-${idx}`} className="inline-flex items-center gap-1 rounded-[var(--radius-button)] bg-surface-warm px-2.5 py-1 text-[10px] text-ink-600">
                      <ImageIcon className="h-2.5 w-2.5" /> {img.name}
                      <button onClick={() => setAttachedImages((p) => p.filter((_, i) => i !== idx))} aria-label={`Remove ${img.name}`} className="ml-1 text-ink-400 hover:text-status-failed">
                        <X className="h-2.5 w-2.5" />
                      </button>
                    </span>
                  ))}
                </div>
              )}
              <div className="flex items-center gap-1 border-t border-line-divider px-4 py-2.5">
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  accept=".pdf,.doc,.docx,.pptx,.txt,.md,.json,.csv,image/png,image/jpeg,image/webp,image/gif"
                  className="hidden"
                  onChange={(e) => { if (e.target.files) onFilesPicked(e.target.files); e.target.value = ""; }}
                />
                <button
                  onClick={() => fileInputRef.current?.click()}
                  className="flex items-center gap-1.5 rounded-[var(--radius-button)] border border-transparent px-2.5 py-1.5 text-[11px] text-ink-400 transition-all hover:border-line-border hover:bg-surface-warm hover:text-ink-700"
                >
                  <Paperclip className="h-3.5 w-3.5" /> + Attach file
                </button>
                {speechSupported && (
                  <button
                    onClick={() => { if (isListening) stopListening(); else { preSpeechTextRef.current = brief; startListening(); } }}
                    className={`flex items-center gap-1.5 rounded-[var(--radius-button)] border px-2.5 py-1.5 text-[11px] transition-all ${
                      isListening
                        ? "animate-pulse border-[var(--status-failed-border)] bg-[var(--status-failed-fill)] text-status-failed"
                        : "border-transparent text-ink-400 hover:border-line-border hover:bg-surface-warm hover:text-ink-700"
                    }`}
                  >
                    {isListening ? <MicOff className="h-3.5 w-3.5" /> : <Mic className="h-3.5 w-3.5" />}
                    {isListening ? "Stop" : "Voice"}
                  </button>
                )}
              </div>
              {examplePrompt && (
                <div className="border-t border-line-divider px-5 py-2.5">
                  <button
                    type="button"
                    onClick={() => setBrief(examplePrompt ?? "")}
                    className="inline-flex items-center gap-1.5 text-[11px] text-ink-500 hover:text-brand"
                  >
                    <Sparkles className="h-3 w-3" />
                    Use template example
                    <span className="italic text-ink-400">&ldquo;{examplePrompt}&rdquo;</span>
                  </button>
                </div>
              )}
            </div>
          </section>
        )}

        {/* Advanced / agent composer trigger. */}
        {!isChaining && (
          <button
            type="button"
            onClick={() => setShowAgents(true)}
            className="flex items-center gap-2 text-[12px] text-ink-400 transition-colors hover:text-ink-700"
          >
            <Settings2 className="h-3.5 w-3.5" />
            <span className="font-medium text-ink-600">Advanced</span>
            <span className="text-ink-400">{pipelineAgents.length} agent{pipelineAgents.length !== 1 ? "s" : ""}</span>
          </button>
        )}

        {/* ── The unified Template → Design System → Discovery stepper. ── */}
        <section>
          {loadError && (
            <div className="mb-3 rounded-[var(--radius-card)] border border-[var(--status-failed-border)] bg-[var(--status-failed-fill)] px-5 py-4 text-[13px] text-status-failed">
              Couldn&apos;t load templates: {loadError}
            </div>
          )}
          <WizardStepper
            mode={STEPPER_MODE[mode]}
            onModeChange={handleModeChange}
            steps={mode === "ppt" ? ["template"] : ["template", "design-system", "discovery"]}
            webTemplates={webTemplates}
            webSelectedId={mode === "prototype" && !customTemplateBody ? selectedTemplateId : null}
            onWebSelect={handleSelectTemplate}
            onWebSelectCustomTemplate={handleSelectCustomTemplate}
            webSelectedCustomTemplateId={mode === "prototype" && customTemplateBody ? selectedTemplateId : null}
            deckTemplates={deckTemplates}
            deckSelectedId={mode === "ppt" && !customTemplateBody ? selectedTemplateId : null}
            onDeckSelect={handleSelectTemplate}
            onDeckSelectCustomTemplate={handleSelectCustomTemplate}
            deckSelectedCustomTemplateId={mode === "ppt" && customTemplateBody ? selectedTemplateId : null}
            dsSlot={
              dsVisible ? (
                systems.length === 0 ? (
                  <div className="h-48 animate-pulse rounded-[var(--radius-card)] bg-surface-white/60" />
                ) : (
                  <DesignSystemPicker
                    systems={systems}
                    selectedId={selectedDsId}
                    onSelect={handleSelectBuiltInDs}
                    onSelectCustom={handleSelectCustomDs}
                  />
                )
              ) : (
                <StepNote>This deck template doesn&apos;t require a design system — the template supplies its own theme.</StepNote>
              )
            }
            discoverySlot={
              mode === "prototype" ? (
                <DiscoveryForm templateInputs={[]} answers={discoveryAnswers} onChange={setDiscoveryAnswers} />
              ) : (
                <StepNote>Discovery questions apply to web prototypes. Your deck brief is enough to generate.</StepNote>
              )
            }
          />
        </section>

        {/* ── Review gates (operate on the active lineup). ── */}
        <section>
          <SectionLabel
            title="Review gates"
            subtitle="Optionally pause the pipeline for your review after specific agents."
          />
          <div className="mt-3">
            <ReviewGatesSection agents={pipelineAgents} onChange={handleGatesChange} />
          </div>
        </section>

        {/* ── Launch. ── */}
        <div className="pt-2">
          {!canContinue && (
            <div className="mb-4 flex flex-wrap gap-2">
              {/* ISS-155: keyed on hasBuildInput, NOT on `!isChaining`. A chained
                  launch whose context block failed to load now blocks Continue, and
                  the old condition hid this pill for every chained launch — leaving
                  a disabled button with no stated reason. */}
              {!hasBuildInput && <Pill label="Add a brief" />}
              {mode === "ppt" && !selectedTemplateId && <Pill label="Pick a template" />}
              {(mode === "prototype" || dsRequired) && !selectedDsId && <Pill label="Pick a design system" />}
            </div>
          )}

          {saveError && (
            <div className="mb-3 rounded-[var(--radius-button)] border border-[var(--status-failed-border)] bg-[var(--status-failed-fill)] px-3 py-2 text-[11px] text-status-failed">
              {saveError}
            </div>
          )}
          {savedConfirm && (
            <div className="mb-3 rounded-[var(--radius-button)] border border-[var(--status-done-border)] bg-[var(--status-done-fill)] px-3 py-2 text-[11px] font-medium text-status-done">
              Workflow saved to your catalogue
            </div>
          )}

          <div className="flex gap-3">
            <button
              type="button"
              onClick={() => { setSaveError(null); setShowSaveModal(true); }}
              title="Save this workflow configuration to reuse later"
              className="flex flex-shrink-0 items-center gap-2 rounded-[var(--radius-card)] border border-line-border bg-surface-white px-5 py-4 text-[14px] font-semibold text-ink-700 shadow-[var(--elevation-raised)] transition-all hover:border-line-control hover:bg-surface-warm"
            >
              <Save className="h-4 w-4" />
              Save workflow
            </button>
            <button
              type="button"
              onClick={handleLaunch}
              disabled={!canContinue}
              className="flex flex-1 items-center justify-center gap-2 rounded-[var(--radius-card)] bg-brand px-6 py-4 text-[14px] font-semibold text-white shadow-[var(--elevation-raised)] transition-all hover:bg-brand-pressed disabled:cursor-not-allowed disabled:bg-line-divider disabled:text-ink-400 disabled:shadow-none"
            >
              Continue
              <ArrowRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      </main>

      <AgentsPopup
        isOpen={showAgents}
        onClose={() => setShowAgents(false)}
        agents={pipelineAgents}
        pipelineType={MODE_CONFIG[mode].agentPipeline}
        onAddAgent={handleAddAgent}
        onRemoveAgent={handleRemoveAgent}
        onReorder={handleReorderAgents}
        canAddMore={canAddMore}
        onSelectionsChange={handleSelectionsChange}
      />

      {showSaveModal && (
        <NameWorkflowModal
          title={cfg.saveTitle}
          onSave={handleSaveWorkflow}
          onCancel={() => setShowSaveModal(false)}
        />
      )}
    </div>
  );
}

function SectionLabel({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="flex items-start gap-3">
      <div>
        <h2 className="text-[14px] font-semibold text-ink-900">{title}</h2>
        {subtitle && <p className="mt-0.5 text-[12px] text-ink-500">{subtitle}</p>}
      </div>
    </div>
  );
}

function Pill({ label }: { label: string }) {
  return (
    <span className="inline-flex items-center rounded-[var(--radius-pill)] border border-[var(--status-amber-border)] bg-[var(--status-amber-fill)] px-3 py-1 text-[11px] font-medium text-status-amber">
      {label}
    </span>
  );
}

function StepNote({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-[8rem] items-center justify-center rounded-[var(--radius-card)] border border-dashed border-line-control bg-surface-warm px-6 text-center text-[12px] text-ink-500">
      {children}
    </div>
  );
}

export default LaunchWizard;
