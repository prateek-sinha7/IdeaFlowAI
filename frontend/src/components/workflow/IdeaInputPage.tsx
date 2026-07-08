"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { motion } from "motion/react";
import {
  ArrowLeft, ArrowRight, Paperclip, File, X, FileText,
  Presentation, Layout, Settings2, Mic, MicOff, GitBranch,
  Save, Check, Image as ImageIcon,
} from "lucide-react";
import { AgentsPopup } from "./AgentsPopup";
import { ReviewGatesSection } from "./ReviewGatesSection";
import { LIBRARY_AGENTS, ALL_LIBRARY_AGENTS } from "./AgentLibraryData";
import { NameWorkflowModal } from "@/components/catalog/NameWorkflowModal";
import { useSpeechRecognition } from "@/hooks/useSpeechRecognition";
import { useSkillsHooks } from "@/context/SkillsHooksContext";
import { createUserWorkflow, getToken, getWorkflowDetail, extractFileText } from "@/lib/api";
import { ATTACH_MAX_CHARS } from "@/lib/constants";
import { resizeImage } from "@/lib/resizeImage";
import { AnimatePresence } from "motion/react";
import type { WorkflowType, AgentDef, AttachedSkill, AttachedHook } from "@/types/index";

// Migration is a meta-pipeline: the home page sends `workflowType="migration"`
// and this page lets the user pick the concrete sub-pipeline before running.
// Defined at module scope so the constant is identity-stable for hook deps.
const MIGRATION_OPTIONS: { type: WorkflowType; label: string; tagline: string }[] = [
  {
    type: "mulesoft_to_springboot",
    label: "Mulesoft → Spring Boot microservices on AWS",
    tagline: "Catalogue the Mule estate, decompose into Spring Boot 3 services, generate the AWS landing zone, and harness the cutover.",
  },
  {
    type: "dotnet_to_azure",
    label: ".NET → Azure (AI-augmented)",
    tagline: "Inventory .NET projects, map each to the right Azure service, modernise to .NET 8, and bolt on Azure AI where it pays off.",
  },
];

interface IdeaInputPageProps {
  workflowType: WorkflowType;
  onBack: () => void;
  // `resolvedType` is the concrete pipeline the backend should dispatch.
  // For all standard workflows it equals `workflowType`; for the `migration`
  // meta-pipeline it is the sub-pipeline the user picked in the tile selector.
  // `extraParams` carries the run-level `context` (merged at the top level of the
  // run_pipeline payload by useWorkflow). Currently used only for the per-run
  // `gate_agent_ids` toggle — present only when the user touches the Review-gates
  // section; omitted otherwise so the backend uses its static default.
  onRun: (message: string, agentIds: string[], resolvedType: WorkflowType, extraParams?: Record<string, unknown>) => void;
  // Phase 21 (LAUNCH-EXISTING-PATH §4.6) — saved-workflow launch preload. When a
  // saved row is launched, `DashboardLayout` threads its persisted composition in
  // here so the composer mounts PRE-LOADED instead of re-deriving from the (empty
  // for `custom`) `LIBRARY_AGENTS.filter(type)`. Absent ⇒ behavior is byte-for-byte
  // the existing custom/idea flow (the seed branch is purely additive).
  initialAgentIds?: string[];                       // saved-workflow agent seed
  initialModelOverrides?: Record<string, string>;   // saved-workflow per-agent model seed
  // WR-01 — saved-workflow Advanced-lever seed (the persisted compact selections
  // map from manifest_json). When a saved row is launched, threading this in lets the
  // composer re-load AND re-send the user-composed levers. Absent ⇒ no selections
  // (byte-identical to the existing custom/idea flow — additive only).
  initialSelections?: Record<string, Record<string, unknown>>;
  // SAVE-BRIEF — pre-fill the brief textarea when reopening a saved workflow
  initialInput?: string;
  // SAVE-GATES — pre-fill the review gate selection when reopening a saved workflow
  initialGateIds?: string[];
  // SURF-03 — the known backend workflow id of the launchable/saved workflow being
  // opened in the composer (built-in: the workflow id == the resolved pipeline type;
  // saved: its `base_pipeline_type`). When present, the composer fetches the compiled
  // per-step capability projection (GET /api/workflows/{id}) and surfaces it as the
  // AgentsPopup "Declared by this workflow" strip. Absent (a brand-new from-scratch
  // composition) ⇒ no fetch and the strip does not render (nothing declared yet).
  workflowId?: string;
}

const TYPE_CONFIG: Record<WorkflowType, {
  tag: string;
  heading: string;
  subtitle: string;
  placeholder: string;
  icon: typeof FileText;
}> = {
  user_stories: {
    tag: "Generate product requirements",
    heading: "Provide the brief",
    subtitle: "Turn an idea or brief into a Jira-ready backlog — epics, stories, and Gherkin acceptance criteria.",
    placeholder: "e.g. Generate epics and stories for a refunds workflow with multi-currency support.",
    icon: FileText,
  },
  user_stories_revision: {
    tag: "Refine an existing PRD or story set",
    heading: "What would you like to change?",
    subtitle: "Apply targeted edits to an existing backlog without rewriting what already works.",
    placeholder: "e.g. Add acceptance criteria for the multi-currency refund flow and split epic E2 into two.",
    icon: FileText,
  },
  od_ppt: {
    tag: "Build an executive presentation",
    heading: "Specify the topic",
    subtitle: "Shape a topic into an enterprise-grade pitch deck with charts, data tables, and executive-ready visuals.",
    placeholder: "e.g. Blockchain technology — enterprise adoption trends and ROI analysis for 2025.",
    icon: Presentation,
  },
  od_ppt_revision: {
    tag: "Refine an existing presentation",
    heading: "What should change?",
    subtitle: "Apply precise, scoped edits to an existing deck — every other slide stays untouched.",
    placeholder: "e.g. Tighten the ROI section to 3 slides and add a competitive-landscape slide before the conclusion.",
    icon: Presentation,
  },
  prototype: {
    tag: "Build an interactive prototype",
    heading: "Describe the product",
    subtitle: "Translate a brief, story set, or wireframes into a navigable, high-fidelity HTML prototype.",
    placeholder: "e.g. Build a dashboard for tracking SaaS subscription metrics with charts and filters.",
    icon: Layout,
  },
  od_prototype: {
    tag: "Build an interactive prototype",
    heading: "Describe the product",
    subtitle: "Translate a brief into a multi-page SPA prototype using a selected template and design system.",
    placeholder: "e.g. Build a project management SaaS with login, dashboard, and settings.",
    icon: Layout,
  },
  prototype_revision: {
    tag: "Iterate on an existing prototype",
    heading: "What should change?",
    subtitle: "Surgically refine an existing prototype — preserve the rest of the design exactly as-is.",
    placeholder: "e.g. Swap the side filter for a top tab bar and add a dark-mode toggle.",
    icon: Layout,
  },
  ppt: {
    tag: "Build an executive presentation",
    heading: "Specify the topic",
    subtitle: "Shape a topic into an enterprise-grade pitch deck with charts, data tables, and executive-ready visuals.",
    placeholder: "e.g. Blockchain technology — enterprise adoption trends and ROI analysis for 2025.",
    icon: Presentation,
  },
  ppt_revision: {
    tag: "Refine an existing presentation",
    heading: "What should change?",
    subtitle: "Apply precise, scoped edits to an existing deck — every other slide stays untouched.",
    placeholder: "e.g. Tighten the ROI section to 3 slides and add a competitive-landscape slide before the conclusion.",
    icon: Presentation,
  },
  app_builder: {
    tag: "Generate a full-stack application",
    heading: "Describe the application",
    subtitle: "Stand up a complete enterprise application — code, tests, and infrastructure produced by specialist agents.",
    placeholder: "e.g. A SaaS platform for managing freelance invoices with Stripe integration.",
    icon: Layout,
  },
  app_builder_revision: {
    tag: "Extend or refine an existing app",
    heading: "What should change?",
    subtitle: "Extend an existing blueprint with targeted changes — every file you didn't touch stays exactly the same.",
    placeholder: "e.g. Add a webhook receiver for Stripe events and persist invoice status to the existing schema.",
    icon: Layout,
  },
  custom: {
    tag: "Compose a custom workflow",
    heading: "Describe the task",
    subtitle: "Assemble specialist agents and skills into a custom workflow for tasks outside the standard pipelines.",
    placeholder: "e.g. Research the competitive landscape for AI coding assistants and generate a SWOT analysis.",
    icon: Layout,
  },
  migration: {
    tag: "Platform workflows",
    heading: "Modernise a legacy estate",
    subtitle: "Modernise a legacy estate end-to-end with a 13-agent SDLC pipeline — inventory, design, code, tests, and cutover.",
    placeholder: "e.g. Migrate three Mulesoft 4 apps powering our orders + claims platform onto AWS, splitting into Spring Boot microservices with Aurora Postgres and SQS messaging.",
    icon: GitBranch,
  },
  mulesoft_to_springboot: {
    tag: "Mulesoft → Spring Boot microservices on AWS",
    heading: "Modernise off Mulesoft",
    subtitle: "Decompose the Mule estate into Spring Boot 3 services on AWS, with parallel-run validation before cutover.",
    placeholder: "e.g. Migrate three Mulesoft 4 apps powering our orders + claims platform onto AWS, splitting into Spring Boot microservices with Aurora Postgres and SQS messaging.",
    icon: GitBranch,
  },
  dotnet_to_azure: {
    tag: ".NET → Azure (AI-augmented)",
    heading: "Modernise .NET onto Azure",
    subtitle: "Map .NET projects to the right Azure services, modernise to .NET 8, and bolt on Azure AI where it pays off.",
    placeholder: "e.g. Rehost two ASP.NET MVC 4.7 apps and a Windows Service onto Azure App Service + Functions, with Azure SQL and Service Bus. Surface AI document triage where it helps the claims workflow.",
    icon: GitBranch,
  },
};

export function IdeaInputPage({ workflowType, onBack, onRun, initialAgentIds, initialModelOverrides, initialSelections, initialInput, initialGateIds, workflowId }: IdeaInputPageProps) {
  const [ideaInput, setIdeaInput] = useState(initialInput ?? "");
  const [showAgents, setShowAgents] = useState(false);
  const [attachedFiles, setAttachedFiles] = useState<{ name: string; size: string }[]>([]);
  // KAN-91: file content stored separately so textarea stays clean.
  // Composed into the pipeline message at send time, not at attach time.
  const [attachedFileContents, setAttachedFileContents] = useState<{ name: string; content: string }[]>([]);
  // Image-input Wave 2: captured images ride OUT-OF-BAND as the `images` payload
  // field (Phase 25 D3) — a SEPARATE state from attachedFileContents (which is
  // inlined into the brief text). base64 must NEVER enter the brief: one ~340KB
  // image ≈ the whole ATTACH_MAX_CHARS cap.
  const [attachedImages, setAttachedImages] = useState<{ name: string; mime_type: string; data: string }[]>([]);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const preSpeechTextRef = useRef("");
  const { isListening, transcript, startListening, stopListening, isSupported: speechSupported } = useSpeechRecognition();

  // Strip _wizard key from selections — it's FE-only metadata, not a capability selector
  const cleanSelections = initialSelections
    ? Object.fromEntries(Object.entries(initialSelections).filter(([k]) => k !== "_wizard"))
    : undefined;

  // For the "migration" meta-pipeline, the user must pick a concrete sub-pipeline
  // (Mulesoft→Spring Boot or .NET→Azure) before Run is allowed. Once picked, the
  // chosen sub-type drives config, agents, and the Run dispatch.
  const isMigrationMeta = workflowType === "migration";
  const [migrationChoice, setMigrationChoice] = useState<WorkflowType | null>(null);
  const effectiveType: WorkflowType = isMigrationMeta && migrationChoice ? migrationChoice : workflowType;

  // Phase 21 (LAUNCH-EXISTING-PATH §4.6) — when launching a saved workflow, seed
  // `pipelineAgents` from the persisted `initialAgentIds` instead of the
  // empty-for-custom `LIBRARY_AGENTS.filter(type)`. Resolve each id through
  // ALL_LIBRARY_AGENTS (LIBRARY_AGENTS ∪ CUSTOM_AGENTS) — the SAME superset the
  // composer's AgentLibrary uses — because saved custom workflows reference the
  // CUSTOM_AGENTS, which are NOT in the base LIBRARY_AGENTS list.
  // Absent ⇒ the existing derive is preserved byte-for-byte.
  const [pipelineAgents, setPipelineAgents] = useState<AgentDef[]>(() =>
    initialAgentIds?.length
      ? (initialAgentIds
          .map((id) => ALL_LIBRARY_AGENTS.find((a) => a.id === id))
          .filter(Boolean) as AgentDef[])
      : LIBRARY_AGENTS.filter((a) => a.pipeline_type === effectiveType).sort((a, b) => a.order - b.order)
  );

  const { attachedSkills, attachedHooks } = useSkillsHooks();

  // Per-run Human-review gate selection, surfaced by <ReviewGatesSection>.
  // Held in a ref so the section reporting its state doesn't re-render this page
  // and so `handleRun` always reads the latest value. Untouched ⇒ we omit
  // `gate_agent_ids` (backend uses its static default); touched ⇒ we send the
  // explicit array (even when empty = "no gates").
  const gateSelectionRef = useRef<{ ids: string[]; touched: boolean }>({ ids: [], touched: false });
  const handleGatesChange = useCallback((ids: string[], touched: boolean) => {
    gateSelectionRef.current = { ids, touched };
  }, []);

  // ISS-014 (MODEL-03): per-agent model overrides selected in the relocated
  // AgentModelPicker (AgentsPopup Agents tab). Held in a ref so the popup
  // reporting its selection doesn't re-render this page, and so `handleRun`
  // always reads the latest value. An empty map ⇒ we omit `model_overrides`
  // entirely (the run_pipeline payload stays byte-identical to before).
  // Phase 21 (LAUNCH-EXISTING-PATH §4.6) — seed the override ref from the saved
  // workflow's persisted per-agent models; absent ⇒ empty map (existing default).
  const modelOverridesRef = useRef<Record<string, string>>(initialModelOverrides ?? {});
  const handleModelOverridesChange = useCallback((overrides: Record<string, string>) => {
    modelOverridesRef.current = overrides;
  }, []);

  // EMP-01 (D-05) — the per-agent Advanced-expander selections map. Held in a
  // ref (like model_overrides) so the popup reporting a selection doesn't
  // re-render this page, and so `handleSaveWorkflow` always reads the latest.
  // An empty map ⇒ we omit `selections` entirely (the save payload stays
  // byte-identical — INV-3). Threads into the createUserWorkflow payload as the
  // EXACT compact shape 22-04 persists in manifest_json; `onRun`/launch stay
  // pure data (SC-001).
  const selectionsRef = useRef<Record<string, Record<string, unknown>>>(cleanSelections ?? {});
  const handleSelectionsChange = useCallback(
    (selections: Record<string, Record<string, unknown>>) => {
      selectionsRef.current = selections;
    },
    [],
  );

  // SURF-03 — when a launchable/saved workflow is opened with a known backend
  // workflow id, fetch its compiled per-step capability projection
  // (GET /api/workflows/{id}) and surface it as the AgentsPopup "Declared by this
  // workflow" strip. Mirrors the AgentModelPicker / CapabilityPaletteSection fetch
  // idiom (useEffect + cancelled guard); no new fetch shell. When there is no id
  // (a brand-new from-scratch composition) the fetch is skipped, `declaredCapabilities`
  // stays undefined, and the strip does not render (nothing declared yet). The
  // projection is registry/manifest-sourced (SC-001) — no hardcoded capability list.
  const [declaredCapabilities, setDeclaredCapabilities] = useState<
    { step: string; capabilities: string[] }[] | undefined
  >(undefined);
  useEffect(() => {
    if (!workflowId) {
      setDeclaredCapabilities(undefined);
      return;
    }
    let cancelled = false;
    const jwt = getToken();
    if (!jwt) {
      setDeclaredCapabilities(undefined);
      return;
    }
    getWorkflowDetail(jwt, workflowId)
      .then((detail) => {
        if (cancelled) return;
        // Map each compiled step to its declared capabilities, sourced entirely
        // from the projection (strategy + gates + validators + compaction +
        // task_source kind) — no hardcoded names. Steps with zero declared caps
        // are omitted so the strip stays terse.
        const mapped = detail.steps
          .map((s) => {
            const caps: string[] = [];
            if (s.strategy) caps.push(`strategy:${s.strategy}`);
            for (const g of s.gates) caps.push(`gate:${g}`);
            for (const v of s.validators) caps.push(`validator:${v}`);
            if (s.compaction) caps.push(`compaction:${s.compaction}`);
            if (s.task_source?.kind) caps.push(`task_source:${s.task_source.kind}`);
            return { step: s.name || s.agent_id, capabilities: caps };
          })
          .filter((d) => d.capabilities.length > 0);
        setDeclaredCapabilities(mapped.length > 0 ? mapped : undefined);
      })
      .catch(() => {
        // Unknown id (404) or transient error ⇒ treat as "nothing declared":
        // leave it undefined so the strip simply does not render (no noisy UI).
        if (!cancelled) setDeclaredCapabilities(undefined);
      });
    return () => {
      cancelled = true;
    };
  }, [workflowId]);

  useEffect(() => {
    // Phase 21 (gotcha #1) — GUARD: when launching a saved workflow the seed lives
    // in `pipelineAgents` already; the empty-for-custom re-derive would clobber it
    // on the first effect run, so bail out and keep the seed.
    // However, when initialAgentIds is cleared (savedComposition set to null after
    // navigating to a different workflow type), we MUST reset to the correct defaults
    // for the new type — otherwise stale agents from a previous saved workflow bleed in.
    if (initialAgentIds?.length) return;
    setPipelineAgents(LIBRARY_AGENTS.filter((a) => a.pipeline_type === effectiveType).sort((a, b) => a.order - b.order));
  }, [effectiveType, initialAgentIds]);

  // Reset the sub-choice when the parent switches us off the migration meta-type.
  useEffect(() => {
    if (!isMigrationMeta) setMigrationChoice(null);
  }, [isMigrationMeta]);

  const config = TYPE_CONFIG[effectiveType];

  useEffect(() => {
    if (isListening && transcript) setIdeaInput(preSpeechTextRef.current ? `${preSpeechTextRef.current} ${transcript}` : transcript);
  }, [transcript, isListening]);

  useEffect(() => { setTimeout(() => inputRef.current?.focus(), 200); }, []);

  const handleRun = () => {
    if (!ideaInput.trim() || pipelineAgents.length === 0) return;
    // For the migration meta-type, Run is gated on a sub-pipeline being chosen.
    if (isMigrationMeta && !migrationChoice) return;
    // KAN-91: compose file content blocks into the message at send time,
    // keeping the textarea clean. ATTACH_MAX_CHARS already applied at attach time.
    const fileBlocks = attachedFileContents
      .map((f) => `\n\n=== Attached: ${f.name} ===\n${f.content}\n=== End: ${f.name} ===`)
      .join("");
    const finalMessage = fileBlocks ? `${ideaInput.trim()}${fileBlocks}` : ideaInput.trim();
    // Only attach gate_agent_ids when the user actually touched the Review-gates
    // section; otherwise omit it entirely so the backend keeps its static default
    // (the run_pipeline payload is byte-identical to before this feature).
    const { ids, touched } = gateSelectionRef.current;
    // ISS-014 (MODEL-03): include per-agent model_overrides only when the user
    // actually picked a non-default model for ≥1 agent. An unselected picker
    // emits an empty map → omitted → byte-identical payload (preserves INV-3).
    const overrides = modelOverridesRef.current;
    const hasOverrides = Object.keys(overrides).length > 0;
    // WR-01 (EMP-01): include the per-agent Advanced-expander selections so the
    // backend overlay (engine._apply_selections) actually applies the user-composed
    // levers at launch — previously selections only reached SAVE, never a run. Mirror
    // the model_overrides discipline: include ONLY when ≥1 lever is set, so an
    // untouched composer emits a byte-identical payload (INV-3 / SC-001).
    const selections = selectionsRef.current;
    const hasSelections = Object.keys(selections).length > 0;
    // Image-input Wave 2: ship captured images OUT-OF-BAND as `images` (D3 —
    // NEVER inlined into finalMessage). Include only when ≥1 image is attached
    // so an image-less run emits a byte-identical payload (INV-3).
    const hasImages = attachedImages.length > 0;
    const extraParams =
      touched || hasOverrides || hasSelections || hasImages
        ? {
            ...(touched ? { gate_agent_ids: ids } : {}),
            ...(hasOverrides ? { model_overrides: overrides } : {}),
            ...(hasSelections ? { selections } : {}),
            ...(hasImages ? { images: attachedImages } : {}),
          }
        : undefined;
    onRun(finalMessage, pipelineAgents.map((a) => a.id), effectiveType, extraParams);
  };

  // Phase 21 (SAVE-FROM-BOTH composer entry) — "Save workflow" persists the
  // composer as a named, reusable workflow. The payload is the EXACT triple
  // `onRun` already sends — base_pipeline_type, agent_ids, model_overrides —
  // so saving is pure data: no new pipeline name, no `if saved_workflow:` fork
  // (SC-001). Server re-validates with the launch predicates (save == launch).
  const [showSaveModal, setShowSaveModal] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [savedConfirm, setSavedConfirm] = useState(false);
  const handleSaveWorkflow = async (name: string, description: string) => {
    setShowSaveModal(false);
    setSaveError(null);
    const jwt = getToken();
    if (!jwt) {
      setSaveError("Not authenticated.");
      return;
    }
    const overrides = modelOverridesRef.current;
    const selections = selectionsRef.current;
    const { ids: gateAgentIds, touched: gatesTouched } = gateSelectionRef.current;
    // Store the brief and gate selection in _wizard so the catalogue card
    // can show a clean summary without relying on the user-typed description.
    const wizardConfig: Record<string, unknown> = {
      brief: ideaInput.trim(),
      ...(gatesTouched ? { gateAgentIds } : {}),
    };
    try {
      await createUserWorkflow(jwt, {
        name,
        description: description || undefined,
        base_pipeline_type: effectiveType,
        agent_ids: pipelineAgents.map((a) => a.id),
        model_overrides: Object.keys(overrides).length > 0 ? overrides : undefined,
        // EMP-01/03: the Advanced-expander selections (omitted when empty so the
        // payload stays byte-identical). Server re-compiles trust="user" (22-04).
        selections: {
          ...selections,
          _wizard: wizardConfig,
        },
      });
      setSavedConfirm(true);
      setTimeout(() => setSavedConfirm(false), 2500);
    } catch (e) {
      setSaveError((e as Error)?.message ?? "Failed to save workflow.");
    }
  };

  const defaultAgentIds = new Set(LIBRARY_AGENTS.filter((a) => a.pipeline_type === effectiveType).map((a) => a.id));
  const optionalAgentCount = pipelineAgents.filter((a) => !defaultAgentIds.has(a.id)).length;
  const maxOptional = effectiveType === "custom" ? 8 : 5;
  const canAddMore = optionalAgentCount < maxOptional;

  const handleAddAgent = useCallback((agent: AgentDef) => {
    setPipelineAgents((prev) => {
      if (prev.find((a) => a.id === agent.id)) return prev;
      const currentDefaults = new Set(LIBRARY_AGENTS.filter((a) => a.pipeline_type === effectiveType).map((a) => a.id));
      const currentOptional = prev.filter((a) => !currentDefaults.has(a.id)).length;
      const limit = effectiveType === "custom" ? 8 : 5;
      if (currentOptional >= limit) return prev;
      const insertIdx = effectiveType === "custom" ? prev.length : (prev.length > 0 ? prev.length - 1 : 0);
      const updated = [...prev];
      updated.splice(insertIdx, 0, { ...agent, order: insertIdx + 1 });
      return updated;
    });
  }, [effectiveType]);

  const handleRemoveAgent = useCallback((agentId: string) => {
    setPipelineAgents((prev) => prev.filter((a) => a.id !== agentId));
  }, []);

  const handleReorderAgents = useCallback((reordered: AgentDef[]) => {
    setPipelineAgents(reordered);
  }, []);

  const totalEstimatedTime = Math.round(pipelineAgents.reduce((s, a) => s + a.estimated_duration, 0));

  return (
    <div className="flex h-full flex-col overflow-y-auto" style={{ background: "#f5f5f0" }}>
      <div className="flex-1 flex flex-col items-center justify-center px-4 sm:px-6 py-10 max-w-2xl mx-auto w-full">

        {/* Back */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="w-full mb-8"
        >
          <button
            onClick={onBack}
            className="flex items-center gap-1.5 text-[12px] text-gray-500 hover:text-gray-900 transition-colors"
          >
            <ArrowLeft className="h-3.5 w-3.5" /> Back
          </button>
        </motion.div>

        {/* Heading */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35 }}
          className="w-full mb-6"
        >
          <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-[0.15em] mb-3">
            {config.tag}
          </p>
          <h1
            className="text-[32px] font-normal italic text-gray-900 leading-tight tracking-tight mb-2"
            style={{ fontFamily: "var(--font-fraunces)" }}
          >
            {config.heading}
          </h1>
          <p className="text-[13px] text-gray-500 leading-relaxed max-w-xl">
            {config.subtitle}
          </p>
        </motion.div>

        {/* Input card */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35, delay: 0.08 }}
          className="w-full"
        >
          <div className="rounded-2xl bg-white shadow-sm border border-gray-200/80 overflow-hidden">
            {/* Textarea */}
            <textarea
              ref={inputRef}
              value={ideaInput}
              onChange={(e) => setIdeaInput(e.target.value)}
              placeholder={isListening ? "Listening... speak your idea" : config.placeholder}
              className="w-full resize-none bg-transparent text-[14px] text-gray-900 placeholder-gray-400 px-5 pt-5 pb-3 focus:outline-none min-h-[130px] max-h-[260px] leading-relaxed"
              rows={5}
              onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) handleRun(); }}
            />

            {/* Attached files */}
            {attachedFiles.length > 0 && (
              <div className="flex flex-wrap gap-1.5 px-5 pb-2">
                {attachedFiles.map((file, idx) => (
                  <span key={`${file.name}-${idx}`} className="inline-flex items-center gap-1 rounded-lg bg-gray-100 px-2.5 py-1 text-[10px] text-gray-600">
                    <File className="h-2.5 w-2.5" /> {file.name}
                    <button onClick={() => {
                      setAttachedFiles((p) => p.filter((_, i) => i !== idx));
                      // KAN-91: also remove stored content so it's not sent
                      const removedName = attachedFiles[idx]?.name;
                      if (removedName) {
                        setAttachedFileContents((p) => p.filter((c) => c.name !== removedName));
                      }
                    }} className="ml-1 text-gray-400 hover:text-red-500">
                      <X className="h-2.5 w-2.5" />
                    </button>
                  </span>
                ))}
              </div>
            )}

            {/* Attached images (Wave 2) — chips only; base64 never inlined (D3) */}
            {attachedImages.length > 0 && (
              <div className="flex flex-wrap gap-1.5 px-5 pb-2">
                {attachedImages.map((img, idx) => (
                  <span key={`${img.name}-${idx}`} className="inline-flex items-center gap-1 rounded-lg bg-gray-100 px-2.5 py-1 text-[10px] text-gray-600">
                    <ImageIcon className="h-2.5 w-2.5" /> {img.name}
                    <button onClick={() => {
                      setAttachedImages((p) => p.filter((_, i) => i !== idx));
                    }} className="ml-1 text-gray-400 hover:text-red-500">
                      <X className="h-2.5 w-2.5" />
                    </button>
                  </span>
                ))}
              </div>
            )}

            {/* Bottom toolbar */}
            <div className="flex items-center justify-between px-4 py-3 border-t border-gray-100">
              <div className="flex items-center gap-1">
                {/* Hidden file input */}
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  accept=".pdf,.doc,.docx,.pptx,.txt,.md,.json,.csv,image/png,image/jpeg,image/webp,image/gif"
                  className="hidden"
                  onChange={(e) => {
                    const files = e.target.files;
                    if (files) {
                      Array.from(files).forEach((f) => {
                        // Image-input Wave 2: images ride OUT-OF-BAND (D3) — they
                        // are captured into attachedImages, NEVER into
                        // attachedFileContents (which is inlined into the brief).
                        const isImageFile =
                          ["image/png", "image/jpeg", "image/webp", "image/gif"].includes(f.type) ||
                          /\.(png|jpe?g|webp|gif)$/i.test(f.name);
                        if (isImageFile) {
                          // UPLD-04: downscale oversized images client-side BEFORE
                          // base64. resizeImage is aspect-preserving, no-upscale, and
                          // degrade-not-block (it resolves to the original file's
                          // base64 on any failure — never throws). The resulting
                          // base64 still rides OUT-OF-BAND as the `images` payload
                          // (D3); it NEVER enters the brief. Server caps stay
                          // authoritative (this is a client optimization only).
                          resizeImage(f).then((resized) => {
                            setAttachedImages((p) => [
                              ...p,
                              { name: f.name, mime_type: resized.mime_type, data: resized.data },
                            ]);
                          });
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
                            // KAN-91: store content separately, not in textarea
                            setAttachedFileContents((p) => [
                              ...p,
                              { name: f.name, content: content.slice(0, ATTACH_MAX_CHARS) },
                            ]);
                          };
                          reader.readAsText(f);
                        } else if (isBinaryFile) {
                          const jwt = getToken();
                          if (jwt) {
                            extractFileText(jwt, f)
                              .then((res) => {
                                // KAN-91: store extracted content separately
                                const truncNote = res.truncated ? `\n[Content truncated to ${ATTACH_MAX_CHARS.toLocaleString()} chars]` : "";
                                setAttachedFileContents((p) => [
                                  ...p,
                                  { name: res.filename, content: `${res.text}${truncNote}` },
                                ]);
                              })
                              .catch(() => {
                                // Extraction failed — store a placeholder so the agent knows the file was attached
                                setAttachedFileContents((p) => [
                                  ...p,
                                  { name: f.name, content: "[could not extract text]" },
                                ]);
                              });
                          } else {
                            setAttachedFileContents((p) => [...p, { name: f.name, content: "" }]);
                          }
                        }
                        // For other file types: chip shows but no content is sent (no text to extract)
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
                    onClick={() => { if (isListening) stopListening(); else { preSpeechTextRef.current = ideaInput; startListening(); } }}
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

              <div className="flex items-center gap-2">
                {/* Save workflow — SAVE-FROM-BOTH composer entry (Phase 21).
                    Reuses the gray-900 pill style; persists the composer triple. */}
                {savedConfirm ? (
                  <span className="flex items-center gap-1.5 rounded-xl px-3 py-2.5 text-[12px] font-semibold text-green-600 bg-green-50 border border-green-100">
                    <Check className="h-3.5 w-3.5" /> Saved
                  </span>
                ) : (
                  <button
                    onClick={() => { setSaveError(null); setShowSaveModal(true); }}
                    disabled={pipelineAgents.length === 0 || (isMigrationMeta && !migrationChoice)}
                    className="flex items-center gap-1.5 rounded-xl border border-gray-200 px-4 py-2.5 text-[12px] font-medium text-gray-600 hover:bg-gray-50 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                    title="Save this composition as a reusable workflow"
                  >
                    <Save className="h-3.5 w-3.5" /> Save workflow
                  </button>
                )}

                {/* Run button */}
                <button
                  onClick={handleRun}
                  disabled={!ideaInput.trim() || pipelineAgents.length === 0 || (isMigrationMeta && !migrationChoice)}
                  className="flex items-center gap-2 rounded-xl bg-gray-900 text-white px-5 py-2.5 text-[13px] font-semibold hover:bg-gray-800 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                >
                  {pipelineAgents.length === 0
                    ? "Add agents first"
                    : isMigrationMeta && !migrationChoice
                    ? "Pick a migration path"
                    : "Run workflow"}
                  <ArrowRight className="h-4 w-4" />
                </button>
              </div>
            </div>

            {saveError && (
              <div className="px-4 pb-3 -mt-1 text-[11px] text-red-600">{saveError}</div>
            )}

            {/* Save modal — reuses NameWorkflowModal (Phase 21). */}
            <AnimatePresence>
              {showSaveModal && (
                <NameWorkflowModal
                  title="Save workflow"
                  onSave={handleSaveWorkflow}
                  onCancel={() => setShowSaveModal(false)}
                />
              )}
            </AnimatePresence>
          </div>
        </motion.div>

        {/* Migration sub-pipeline selector — only when the meta-type was picked.
            Two tiles, always visible (no tap-to-reveal). Tapping a tile drives
            the rest of the page (config copy, agent lineup, Run dispatch). */}
        {isMigrationMeta && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, delay: 0.12 }}
            className="w-full mt-5"
          >
            <p className="text-[10px] font-semibold text-[#1B2A4A] uppercase tracking-[0.14em] mb-2.5">
              Choose your migration path
            </p>
            <div className="grid gap-2 sm:grid-cols-2">
              {MIGRATION_OPTIONS.map((opt) => {
                const isSelected = migrationChoice === opt.type;
                return (
                  <button
                    key={opt.type}
                    onClick={() => setMigrationChoice(opt.type)}
                    className={`group text-left rounded-2xl border-2 px-4 py-3.5 transition-all ${
                      isSelected
                        ? "border-[#1B2A4A] bg-[#1B2A4A] shadow-md"
                        : "border-gray-200 bg-white hover:border-[#1B2A4A]/40 hover:bg-[#F1F4FB]"
                    }`}
                  >
                    <div className="flex items-start gap-2.5">
                      <GitBranch className={`h-4 w-4 mt-0.5 flex-shrink-0 ${isSelected ? "text-white" : "text-[#1B2A4A]"}`} />
                      <div className="min-w-0">
                        <p className={`text-[12px] font-semibold leading-snug ${isSelected ? "text-white" : "text-gray-900"}`}>
                          {opt.label}
                        </p>
                        <p className={`text-[10px] mt-1 leading-relaxed ${isSelected ? "text-white/85" : "text-gray-500"}`}>
                          {opt.tagline}
                        </p>
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          </motion.div>
        )}

        {/* Advanced / agents info */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.2 }}
          className="w-full mt-4"
        >
          <button
            onClick={() => setShowAgents(true)}
            className="flex items-center gap-2 text-[12px] text-gray-400 hover:text-gray-700 transition-colors"
          >
            <Settings2 className="h-3.5 w-3.5" />
            <span className="font-medium text-gray-600">Advanced</span>
            <span className="text-gray-400">
              {pipelineAgents.length} agent{pipelineAgents.length !== 1 ? "s" : ""}
              {totalEstimatedTime > 0 && ` · ~${totalEstimatedTime < 60 ? `${totalEstimatedTime}s` : `${Math.round(totalEstimatedTime / 60)}m`}`}
              {(attachedSkills.length + attachedHooks.length) > 0 && ` · ${attachedSkills.length + attachedHooks.length} skill${attachedSkills.length + attachedHooks.length !== 1 ? "s/hooks" : "/hook"}`}
            </span>
          </button>
        </motion.div>

        {/* Review gates — inline expandable, sits beside the Skills/Hooks
            ("Advanced") controls. Self-hides when there are no agents (e.g. the
            migration meta-type before a sub-pipeline is chosen). */}
        {(!isMigrationMeta || migrationChoice) && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.24 }}
            className="w-full mt-3"
          >
            <ReviewGatesSection agents={pipelineAgents} onChange={handleGatesChange} initialGateIds={initialGateIds} />
          </motion.div>
        )}

      </div>

      <AgentsPopup
        isOpen={showAgents}
        onClose={() => setShowAgents(false)}
        agents={pipelineAgents}
        pipelineType={effectiveType}
        onAddAgent={handleAddAgent}
        onRemoveAgent={handleRemoveAgent}
        onReorder={handleReorderAgents}
        canAddMore={canAddMore}
        onModelOverridesChange={handleModelOverridesChange}
        onSelectionsChange={handleSelectionsChange}
        initialModelOverrides={initialModelOverrides}
        initialSelections={cleanSelections}
        declaredCapabilities={declaredCapabilities}
      />
    </div>
  );
}
