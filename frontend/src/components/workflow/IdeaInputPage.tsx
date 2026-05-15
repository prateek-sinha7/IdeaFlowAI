"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { motion } from "motion/react";
import {
  ArrowLeft, ArrowRight, Paperclip, File, X, FileText,
  Presentation, Layout, Settings2, Mic, MicOff, GitBranch,
} from "lucide-react";
import { AgentsPopup } from "./AgentsPopup";
import { LIBRARY_AGENTS } from "./AgentLibraryData";
import { useSpeechRecognition } from "@/hooks/useSpeechRecognition";
import { useSkillsHooks } from "@/context/SkillsHooksContext";
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
  onRun: (message: string, agentIds: string[], resolvedType: WorkflowType) => void;
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
  prototype: {
    tag: "Build an interactive prototype",
    heading: "Describe the product",
    subtitle: "Translate a brief, story set, or wireframes into a navigable, high-fidelity HTML prototype.",
    placeholder: "e.g. Build a dashboard for tracking SaaS subscription metrics with charts and filters.",
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

export function IdeaInputPage({ workflowType, onBack, onRun }: IdeaInputPageProps) {
  const [ideaInput, setIdeaInput] = useState("");
  const [showAgents, setShowAgents] = useState(false);
  const [attachedFiles, setAttachedFiles] = useState<{ name: string; size: string }[]>([]);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const preSpeechTextRef = useRef("");
  const { isListening, transcript, startListening, stopListening, isSupported: speechSupported } = useSpeechRecognition();

  // For the "migration" meta-pipeline, the user must pick a concrete sub-pipeline
  // (Mulesoft→Spring Boot or .NET→Azure) before Run is allowed. Once picked, the
  // chosen sub-type drives config, agents, and the Run dispatch.
  const isMigrationMeta = workflowType === "migration";
  const [migrationChoice, setMigrationChoice] = useState<WorkflowType | null>(null);
  const effectiveType: WorkflowType = isMigrationMeta && migrationChoice ? migrationChoice : workflowType;

  const [pipelineAgents, setPipelineAgents] = useState<AgentDef[]>(() =>
    LIBRARY_AGENTS.filter((a) => a.pipeline_type === effectiveType).sort((a, b) => a.order - b.order)
  );

  const { attachedSkills, attachedHooks } = useSkillsHooks();

  useEffect(() => {
    setPipelineAgents(LIBRARY_AGENTS.filter((a) => a.pipeline_type === effectiveType).sort((a, b) => a.order - b.order));
  }, [effectiveType]);

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
    onRun(ideaInput.trim(), pipelineAgents.map((a) => a.id), effectiveType);
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
                    <button onClick={() => setAttachedFiles((p) => p.filter((_, i) => i !== idx))} className="ml-1 text-gray-400 hover:text-red-500">
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
                  accept=".pdf,.doc,.docx,.pptx,.txt,.md,.json,.csv"
                  className="hidden"
                  onChange={(e) => {
                    const files = e.target.files;
                    if (files) {
                      const nf = Array.from(files).map((f) => ({
                        name: f.name,
                        size: f.size < 1024 ? `${f.size}B` : f.size < 1048576 ? `${(f.size / 1024).toFixed(1)}KB` : `${(f.size / 1048576).toFixed(1)}MB`,
                      }));
                      setAttachedFiles((p) => [...p, ...nf]);
                      setIdeaInput((p) => p ? `${p}\n\n[Attached: ${nf.map((f) => f.name).join(", ")}]` : `[Attached: ${nf.map((f) => f.name).join(", ")}]`);
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
      />
    </div>
  );
}
