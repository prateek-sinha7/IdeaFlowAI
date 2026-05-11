"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { motion } from "motion/react";
import {
  ArrowLeft, ArrowRight, Paperclip, File, X, FileText,
  Presentation, Layout, Settings2, Mic, MicOff,
} from "lucide-react";
import { AgentsPopup } from "./AgentsPopup";
import { LIBRARY_AGENTS } from "./AgentLibraryData";
import { useSpeechRecognition } from "@/hooks/useSpeechRecognition";
import type { WorkflowType, AgentDef } from "@/types/index";

interface IdeaInputPageProps {
  workflowType: WorkflowType;
  onBack: () => void;
  onRun: (message: string, agentIds: string[]) => void;
}

const TYPE_CONFIG: Record<WorkflowType, {
  tag: string;
  heading: string;
  inputLabel: string;
  outputLabel: string;
  placeholder: string;
  icon: typeof FileText;
}> = {
  user_stories: {
    tag: "Turn an idea into product requirements",
    heading: "Tell us a bit more.",
    inputLabel: "Idea, PRD, or requirements doc",
    outputLabel: "PRD + epics + Jira-ready stories",
    placeholder: "e.g. Generate epics and stories for a refunds workflow with multi-currency support.",
    icon: FileText,
  },
  prototype: {
    tag: "Turn stories into a clickable prototype",
    heading: "Describe your product.",
    inputLabel: "Idea, user stories, or wireframes",
    outputLabel: "Interactive HTML prototype",
    placeholder: "e.g. Build a dashboard for tracking SaaS subscription metrics with charts and filters.",
    icon: Layout,
  },
  ppt: {
    tag: "Create a professional presentation",
    heading: "What's the topic?",
    inputLabel: "Topic, brief, or outline",
    outputLabel: "Slide deck with charts & visuals",
    placeholder: "e.g. Blockchain technology — enterprise adoption trends and ROI analysis for 2025.",
    icon: Presentation,
  },
  app_builder: {
    tag: "Build a full-stack application",
    heading: "Describe your app.",
    inputLabel: "Brief, PRD, or repo description",
    outputLabel: "Full-stack code + infrastructure",
    placeholder: "e.g. A SaaS platform for managing freelance invoices with Stripe integration.",
    icon: Layout,
  },
  custom: {
    tag: "Design your own workflow",
    heading: "What do you need?",
    inputLabel: "Any idea or task",
    outputLabel: "Custom agent output",
    placeholder: "e.g. Research the competitive landscape for AI coding assistants and generate a SWOT analysis.",
    icon: Layout,
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
  const [pipelineAgents, setPipelineAgents] = useState<AgentDef[]>(() =>
    LIBRARY_AGENTS.filter((a) => a.pipeline_type === workflowType).sort((a, b) => a.order - b.order)
  );

  useEffect(() => {
    setPipelineAgents(LIBRARY_AGENTS.filter((a) => a.pipeline_type === workflowType).sort((a, b) => a.order - b.order));
  }, [workflowType]);

  const config = TYPE_CONFIG[workflowType];

  useEffect(() => {
    if (isListening && transcript) setIdeaInput(preSpeechTextRef.current ? `${preSpeechTextRef.current} ${transcript}` : transcript);
  }, [transcript, isListening]);

  useEffect(() => { setTimeout(() => inputRef.current?.focus(), 200); }, []);

  const handleRun = () => {
    if (!ideaInput.trim() || pipelineAgents.length === 0) return;
    onRun(ideaInput.trim(), pipelineAgents.map((a) => a.id));
  };

  const defaultAgentIds = new Set(LIBRARY_AGENTS.filter((a) => a.pipeline_type === workflowType).map((a) => a.id));
  const optionalAgentCount = pipelineAgents.filter((a) => !defaultAgentIds.has(a.id)).length;
  const maxOptional = workflowType === "custom" ? 8 : 5;
  const canAddMore = optionalAgentCount < maxOptional;

  const handleAddAgent = useCallback((agent: AgentDef) => {
    setPipelineAgents((prev) => {
      if (prev.find((a) => a.id === agent.id)) return prev;
      const currentDefaults = new Set(LIBRARY_AGENTS.filter((a) => a.pipeline_type === workflowType).map((a) => a.id));
      const currentOptional = prev.filter((a) => !currentDefaults.has(a.id)).length;
      const limit = workflowType === "custom" ? 8 : 5;
      if (currentOptional >= limit) return prev;
      const insertIdx = workflowType === "custom" ? prev.length : (prev.length > 0 ? prev.length - 1 : 0);
      const updated = [...prev];
      updated.splice(insertIdx, 0, { ...agent, order: insertIdx + 1 });
      return updated;
    });
  }, [workflowType]);

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
          <h1 className="text-[32px] font-bold text-gray-900 leading-tight tracking-tight mb-2">
            {config.heading}
          </h1>
          <p className="text-[13px] text-gray-500">
            <span className="text-gray-400">Input:</span>{" "}
            <span className="text-gray-600">{config.inputLabel}</span>
            {" · "}
            <span className="text-gray-400">Output:</span>{" "}
            <span className="font-medium text-gray-700">{config.outputLabel}</span>
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
                disabled={!ideaInput.trim() || pipelineAgents.length === 0}
                className="flex items-center gap-2 rounded-xl bg-gray-900 text-white px-5 py-2.5 text-[13px] font-semibold hover:bg-gray-800 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
              >
                {pipelineAgents.length === 0 ? "Add agents first" : "Run workflow"}
                <ArrowRight className="h-4 w-4" />
              </button>
            </div>
          </div>
        </motion.div>

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
            </span>
          </button>
        </motion.div>

      </div>

      <AgentsPopup
        isOpen={showAgents}
        onClose={() => setShowAgents(false)}
        agents={pipelineAgents}
        pipelineType={workflowType}
        onAddAgent={handleAddAgent}
        onRemoveAgent={handleRemoveAgent}
        onReorder={handleReorderAgents}
        canAddMore={canAddMore}
      />
    </div>
  );
}
