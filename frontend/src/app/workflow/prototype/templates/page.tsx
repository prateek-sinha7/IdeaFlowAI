"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, ArrowRight, Sparkles, ChevronDown, ChevronRight, Layers, Eye, Paperclip, Mic, MicOff, X, File, Settings2, Save } from "lucide-react";
import { getToken, extractFileText, createUserWorkflow } from "@/lib/api";
import { ATTACH_MAX_CHARS } from "@/lib/constants";
import {
  listDesignSystems,
  listPrototypeTemplates,
  type DesignSystemListItem,
  type PrototypeTemplate,
} from "@/lib/prototype-api";
import { TemplateGallery } from "@/components/workflow/prototype/TemplateGallery";
import { DesignSystemPicker } from "@/components/workflow/prototype/DesignSystemPicker";
import { ReviewGatesSection } from "@/components/workflow/ReviewGatesSection";
import { AgentsPopup } from "@/components/workflow/AgentsPopup";
import { LIBRARY_AGENTS } from "@/components/workflow/AgentLibraryData";
import { useSpeechRecognition } from "@/hooks/useSpeechRecognition";
import { NameWorkflowModal } from "@/components/catalog/NameWorkflowModal";
import type { CustomDesignSystem } from "@/components/workflow/prototype/CustomDesignSystemModal";
import type { CustomTemplate } from "@/components/workflow/prototype/CustomTemplateModal";
import type { AgentDef } from "@/types/index";

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
  const [attachedFiles, setAttachedFiles] = useState<{ name: string; size: string }[]>([]);
  // KAN-91: file content stored separately so textarea stays clean.
  const [attachedFileContents, setAttachedFileContents] = useState<{ name: string; content: string }[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const preSpeechTextRef = useRef("");
  const { isListening, transcript, startListening, stopListening, isSupported: speechSupported } = useSpeechRecognition();
  const [chainFrom, setChainFrom] = useState<string | null>(null);
  const [chainContextBlock, setChainContextBlock] = useState<string | null>(null);
  const [contextExpanded, setContextExpanded] = useState(false);
  const [showAgents, setShowAgents] = useState(false);
  const modelOverridesRef = useRef<Record<string, string>>({});
  const handleModelOverridesChange = useCallback((overrides: Record<string, string>) => {
    modelOverridesRef.current = overrides;
  }, []);
  const selectionsRef = useRef<Record<string, Record<string, unknown>>>({});
  const handleSelectionsChange = useCallback((s: Record<string, Record<string, unknown>>) => {
    selectionsRef.current = s;
  }, []);

  // Save workflow state
  const [showSaveModal, setShowSaveModal] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [savedConfirm, setSavedConfirm] = useState(false);

  useEffect(() => {
    const token = getToken();
    if (!token) { router.replace("/login"); return; }
    setAuthChecked(true);
    // Check if we arrived via a chain action
    const from = sessionStorage.getItem("chain.from");
    if (from) {
      setChainFrom(from);
      // Clear chain.from immediately after reading into component state so
      // it doesn't persist across fresh navigations to this page.
      sessionStorage.removeItem("chain.from");
    }
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
        agentIds?: string[];
        gateAgentIds?: string[];
        modelOverrides?: Record<string, string>;
        selections?: Record<string, Record<string, unknown>>;
      };
      if (d.templateId) setSelectedTemplateId(d.templateId);
      if (d.designSystemId) setSelectedDsId(d.designSystemId);
      if (d.brief) setBrief(d.brief);
      if (d.customDsBody) setCustomDsBody(d.customDsBody);
      if (d.customTemplateBody) setCustomTemplateBody(d.customTemplateBody);
      // Restore agent composition from saved workflow
      if (d.agentIds && d.agentIds.length > 0) {
        const allAgents = LIBRARY_AGENTS;
        const restored = d.agentIds
          .map((id) => allAgents.find((a) => a.id === id))
          .filter(Boolean) as AgentDef[];
        if (restored.length > 0) setPipelineAgents(restored);
      }
      // Restore model overrides
      if (d.modelOverrides) {
        modelOverridesRef.current = d.modelOverrides;
      }
      // Restore selections
      if (d.selections) {
        selectionsRef.current = d.selections;
      }
      // Restore gate selection
      if (d.gateAgentIds !== undefined) {
        gateSelectionRef.current = { ids: d.gateAgentIds, touched: true };
      }
      // FIX-005: always clear the draft after reading — it is only needed for the
      // single wizard→dashboard redirect. Leaving it in sessionStorage causes every
      // subsequent fresh wizard open to pre-fill the previous run's brief/template/DS.
      sessionStorage.removeItem(STORAGE_KEY);
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

  // Prototype pipeline agents — starts from static defaults, can be augmented via AgentsPopup.
  const [pipelineAgents, setPipelineAgents] = useState<AgentDef[]>(
    () => LIBRARY_AGENTS.filter((a) => a.pipeline_type === "prototype").sort((a, b) => a.order - b.order)
  );

  const defaultAgentIds = useMemo(
    () => new Set(LIBRARY_AGENTS.filter((a) => a.pipeline_type === "prototype").map((a) => a.id)),
    [],
  );
  const optionalAgentCount = pipelineAgents.filter((a) => !defaultAgentIds.has(a.id)).length;
  const canAddMore = optionalAgentCount < 5;

  const handleAddAgent = useCallback((agent: AgentDef) => {
    setPipelineAgents((prev) => {
      if (prev.find((a) => a.id === agent.id)) return prev;
      const currentOptional = prev.filter((a) => !defaultAgentIds.has(a.id)).length;
      if (currentOptional >= 5) return prev;
      const insertIdx = prev.length > 0 ? prev.length - 1 : 0;
      const updated = [...prev];
      updated.splice(insertIdx, 0, { ...agent, order: insertIdx + 1 });
      return updated;
    });
  }, [defaultAgentIds]);

  const handleRemoveAgent = useCallback((agentId: string) => {
    setPipelineAgents((prev) => prev.filter((a) => a.id !== agentId));
  }, []);

  const handleReorderAgents = useCallback((reordered: AgentDef[]) => {
    setPipelineAgents(reordered);
  }, []);

  // Per-run Human-review gate selection, surfaced by <ReviewGatesSection>.
  // Held in a ref so the section reporting its state doesn't re-render this page
  // and so `handleContinue` always reads the latest value. Untouched ⇒ we omit
  // the gate field from the draft (backend keeps its static default → byte-identical);
  // touched ⇒ we persist the explicit array (even empty = "no gates").
  const gateSelectionRef = useRef<{ ids: string[]; touched: boolean }>({ ids: [], touched: false });
  const handleGatesChange = useCallback((ids: string[], touched: boolean) => {
    gateSelectionRef.current = { ids, touched };
  }, []);

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

  // Mirror transcript into the brief textarea (same pattern as IdeaInputPage)
  useEffect(() => {
    if (transcript) {
      setBrief(preSpeechTextRef.current + (preSpeechTextRef.current ? " " : "") + transcript);
    }
  }, [transcript]);

  const canContinue = Boolean(
    // KAN-87: template selection is now optional — user may proceed without a template.
    // A design system is still required (it provides the color tokens the agents use).
    // When no template is selected, selectedTemplateId stays null — that is valid.
    selectedDsId &&
    (isChaining || brief.trim())  // brief not required when chaining
  );

  const handleSaveWorkflow = useCallback(async (name: string, description: string) => {
    setShowSaveModal(false);
    setSaveError(null);
    const jwt = getToken();
    if (!jwt) { setSaveError("Not authenticated."); return; }
    const overrides = modelOverridesRef.current;
    const sel = selectionsRef.current;
    const { ids: gateAgentIds, touched: gatesTouched } = gateSelectionRef.current;
    const wizardConfig: Record<string, unknown> = {
      templateId: selectedTemplateId,
      designSystemId: selectedDsId,
      brief,
      ...(gatesTouched ? { gateAgentIds } : {}),
      ...(customDsBody ? { customDsBody } : {}),
      ...(customTemplateBody ? { customTemplateBody } : {}),
    };
    try {
      await createUserWorkflow(jwt, {
        name,
        description: description || undefined,
        base_pipeline_type: "od_prototype",
        agent_ids: pipelineAgents.map((a) => a.id),
        model_overrides: Object.keys(overrides).length > 0 ? overrides : undefined,
        selections: {
          ...sel,
          _wizard: wizardConfig,
        },
      });
      setSavedConfirm(true);
      setTimeout(() => setSavedConfirm(false), 2500);
    } catch (e) {
      setSaveError((e as Error)?.message ?? "Failed to save workflow.");
    }
  }, [selectedTemplateId, selectedDsId, brief, customDsBody, customTemplateBody, pipelineAgents]);

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

    // KAN-91: compose attached file content blocks into the brief at send time
    const fileBlocks = attachedFileContents
      .map((f) => `\n\n=== Attached: ${f.name} ===\n${f.content}\n=== End: ${f.name} ===`)
      .join("");
    if (fileBlocks) finalBrief = `${finalBrief}${fileBlocks}`;

    // Per-run gate selection: persist `gateAgentIds` into the draft ONLY when the
    // user touched the Review-gates section. Untouched ⇒ the field is omitted, the
    // dashboard leaves `pendingOdProtoParams.gateAgentIds` undefined, and
    // DashboardLayout drops `gate_agent_ids` → backend static default (byte-identical
    // to before this feature). Touched ⇒ the explicit array (even []) flows through.
    const { ids: gateAgentIds, touched: gatesTouched } = gateSelectionRef.current;

    sessionStorage.setItem(STORAGE_KEY, JSON.stringify({
      templateId: selectedTemplateId,
      designSystemId: selectedDsId,
      brief: finalBrief,
      ...(customDsBody ? { customDsBody } : {}),
      ...(customTemplateBody ? { customTemplateBody } : {}),
      ...(sourceRunId ? { sourceRunId } : {}),
      ...(gatesTouched ? { gateAgentIds } : {}),
      ...(Object.keys(modelOverridesRef.current).length > 0 ? { modelOverrides: modelOverridesRef.current } : {}),
      ...(Object.keys(selectionsRef.current).length > 0 ? { selections: selectionsRef.current } : {}),
      agentIds: pipelineAgents.map((a) => a.id),
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
                placeholder={isListening ? "Listening... speak your idea" : "e.g. A kanban board for a 5-person growth squad — backlog, doing, review, done. Show real ticket titles and assignee avatars."}
                rows={5}
                className="w-full resize-none rounded-2xl bg-transparent px-5 py-4 text-[14px] leading-relaxed text-gray-900 placeholder:text-gray-400 focus:outline-none"
              />
              {attachedFiles.length > 0 && (
                <div className="flex flex-wrap gap-1.5 px-5 pb-2">
                  {attachedFiles.map((file, idx) => (
                    <span key={`${file.name}-${idx}`} className="inline-flex items-center gap-1 rounded-lg bg-gray-100 px-2.5 py-1 text-[10px] text-gray-600">
                      <File className="h-2.5 w-2.5" /> {file.name}
                      <button onClick={() => {
                        setAttachedFiles((p) => p.filter((_, i) => i !== idx));
                        const removedName = attachedFiles[idx]?.name;
                        if (removedName) setAttachedFileContents((p) => p.filter((c) => c.name !== removedName));
                      }} className="ml-1 text-gray-400 hover:text-red-500">
                        <X className="h-2.5 w-2.5" />
                      </button>
                    </span>
                  ))}
                </div>
              )}
              <div className="flex items-center gap-1 px-4 py-2.5 border-t border-gray-100">
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  accept=".pdf,.doc,.docx,.pptx,.txt,.md,.json,.csv"
                  className="hidden"
                  onChange={(e) => {
                    const files = e.target.files;
                    if (files) {
                      Array.from(files).forEach((f) => {
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
                            // KAN-91: store content separately, not in textarea
                            setAttachedFileContents((p) => [...p, { name: f.name, content: content.slice(0, ATTACH_MAX_CHARS) }]);
                          };
                          reader.readAsText(f);
                        } else if (isBinaryFile) {
                          const jwt = getToken();
                          if (jwt) {
                            extractFileText(jwt, f)
                              .then((res) => {
                                // KAN-91: store extracted content separately
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
                        // For other file types: chip shows but no content is sent
                      });
                    }
                    e.target.value = "";
                  }}
                />
                <button
                  onClick={() => fileInputRef.current?.click()}
                  className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[11px] text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-all border border-transparent hover:border-gray-200"
                >
                  <Paperclip className="h-3.5 w-3.5" /> + Attach file
                </button>
                {speechSupported && (
                  <button
                    onClick={() => { if (isListening) stopListening(); else { preSpeechTextRef.current = brief; startListening(); } }}
                    className={`flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[11px] transition-all border border-transparent ${
                      isListening
                        ? "text-red-500 bg-red-50 border-red-100 animate-pulse"
                        : "text-gray-400 hover:text-gray-700 hover:bg-gray-100 hover:border-gray-200"
                    }`}
                  >
                    {isListening ? <MicOff className="h-3.5 w-3.5" /> : <Mic className="h-3.5 w-3.5" />}
                    {isListening ? "Stop" : "Voice"}
                  </button>
                )}
              </div>
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

        {/* Advanced / agents config — below the brief, always visible */}
        {!isChaining && (
          <button
            type="button"
            onClick={() => setShowAgents(true)}
            className="flex items-center gap-2 text-[12px] text-gray-400 hover:text-gray-700 transition-colors"
          >
            <Settings2 className="h-3.5 w-3.5" />
            <span className="font-medium text-gray-600">Advanced</span>
            <span className="text-gray-400">
              {pipelineAgents.length} agent{pipelineAgents.length !== 1 ? "s" : ""}
            </span>
          </button>
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

        {/* ── Section 4 (or 3 when chaining): Review gates ──────────────── */}
        <section>
          <SectionLabel
            number={isChaining ? 3 : 4}
            title="Review gates"
            subtitle="Optionally pause the pipeline for your review after specific agents. Pre-set to the recommended defaults."
          />
          <div className="mt-3">
            <ReviewGatesSection agents={pipelineAgents} onChange={handleGatesChange} />
          </div>
        </section>

        {/* ── Continue ───────────────────────────────────────────────────── */}
        <div className="pt-2">
          {!canContinue && (
            <div className="mb-4 flex flex-wrap gap-2">
              {!isChaining && !brief.trim() && <Pill label="Add a brief" />}
              {!selectedDsId && <Pill label="Pick a design system" />}
            </div>
          )}

          {/* Save workflow error */}
          {saveError && (
            <div className="mb-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-[11px] text-red-600">
              {saveError}
            </div>
          )}

          {/* Save confirmation */}
          {savedConfirm && (
            <div className="mb-3 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-[11px] text-emerald-700 font-medium">
              ✓ Workflow saved to your catalogue
            </div>
          )}

          <div className="flex gap-3">
            {/* Save workflow button */}
            <button
              type="button"
              onClick={() => { setSaveError(null); setShowSaveModal(true); }}
              className="flex items-center gap-2 rounded-2xl border border-gray-200 bg-white px-5 py-4 text-[14px] font-semibold text-gray-700 shadow-sm transition-all hover:bg-gray-50 hover:border-gray-300 flex-shrink-0"
              title="Save this workflow configuration to reuse later"
            >
              <Save className="h-4 w-4" />
              Save workflow
            </button>

            <button
              type="button"
              onClick={handleContinue}
              disabled={!canContinue}
              className="flex flex-1 items-center justify-center gap-2 rounded-2xl bg-[#1B2A4A] px-6 py-4 text-[14px] font-semibold text-white shadow-sm transition-all hover:bg-[#0F1B33] disabled:cursor-not-allowed disabled:bg-gray-200 disabled:text-gray-400 disabled:shadow-none"
            >
              Continue
              <ArrowRight className="h-4 w-4" />
            </button>
          </div>

          {canContinue && (
            <p className="mt-2 text-center text-[11px] text-gray-500">
              {customTemplateBody ? "Custom template" : selectedTemplate?.name} template · {customDsBody ? "Custom design system" : selectedDsId}
            </p>
          )}
        </div>

      </main>

      <AgentsPopup
        isOpen={showAgents}
        onClose={() => setShowAgents(false)}
        agents={pipelineAgents}
        pipelineType="prototype"
        onAddAgent={handleAddAgent}
        onRemoveAgent={handleRemoveAgent}
        onReorder={handleReorderAgents}
        canAddMore={canAddMore}
        onModelOverridesChange={handleModelOverridesChange}
        onSelectionsChange={handleSelectionsChange}
      />

      {/* Save workflow modal */}
      {showSaveModal && (
        <NameWorkflowModal
          title="Save prototype workflow"
          onSave={handleSaveWorkflow}
          onCancel={() => setShowSaveModal(false)}
        />
      )}
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
