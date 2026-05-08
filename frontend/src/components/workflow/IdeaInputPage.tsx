"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { motion } from "motion/react";
import {
  ArrowLeft,
  Play,
  Mic,
  MicOff,
  Paperclip,
  Eye,
  File,
  X,
  FileText,
  Presentation,
  Layout,
  Plus,
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

const TYPE_CONFIG: Record<WorkflowType, { label: string; subtitle: string; icon: typeof FileText }> = {
  user_stories: {
    label: "Product Requirements",
    subtitle: "Shape a fuzzy idea into a PRD with epics, user stories, and Gherkin acceptance criteria.",
    icon: FileText,
  },
  prototype: {
    label: "Clickable Prototype",
    subtitle: "Go from stories or sketches to a high-fidelity, navigable prototype in minutes.",
    icon: Layout,
  },
  ppt: {
    label: "Craft a Presentation",
    subtitle: "Generate an enterprise-grade slide deck with charts, data tables, and compelling visuals.",
    icon: Presentation,
  },
  app_builder: {
    label: "Build an App",
    subtitle: "Hand us a deck, a repo, or a brief — we'll deliver a working app, end to end.",
    icon: Layout,
  },
  reverse_engineer: {
    label: "Reverse-Engineer a Codebase",
    subtitle: "Map architecture, dependencies, risks, and hidden user journeys from any repo.",
    icon: FileText,
  },
  custom: {
    label: "Custom Workflow",
    subtitle: "Compose specialist agents and skills into a bespoke pipeline for anything else.",
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
  const Icon = config.icon;

  useEffect(() => { if (isListening && transcript) setIdeaInput(preSpeechTextRef.current ? `${preSpeechTextRef.current} ${transcript}` : transcript); }, [transcript, isListening]);
  useEffect(() => { setTimeout(() => inputRef.current?.focus(), 200); }, []);

  const handleRun = () => {
    if (!ideaInput.trim()) return;
    if (pipelineAgents.length === 0) return;
    onRun(ideaInput.trim(), pipelineAgents.map((a) => a.id));
  };

  const defaultAgentIds = new Set(LIBRARY_AGENTS.filter((a) => a.pipeline_type === workflowType).map((a) => a.id));
  const optionalAgentCount = pipelineAgents.filter((a) => !defaultAgentIds.has(a.id)).length;
  const maxOptional = workflowType === "custom" ? 8 : 2;
  const canAddMore = optionalAgentCount < maxOptional;

  const handleAddAgent = useCallback((agent: AgentDef) => {
    setPipelineAgents((prev) => {
      if (prev.find((a) => a.id === agent.id)) return prev;
      const currentDefaults = new Set(LIBRARY_AGENTS.filter((a) => a.pipeline_type === workflowType).map((a) => a.id));
      const currentOptional = prev.filter((a) => !currentDefaults.has(a.id)).length;
      const limit = workflowType === "custom" ? 8 : 2;
      if (currentOptional >= limit) return prev;
      const insertIdx = workflowType === "custom" ? prev.length : (prev.length > 0 ? prev.length - 1 : 0);
      const updated = [...prev];
      updated.splice(insertIdx, 0, { ...agent, order: insertIdx + 1 });
      return updated;
    });
  }, [workflowType]);

  const handleRemoveAgent = useCallback((agentId: string) => { setPipelineAgents((prev) => prev.filter((a) => a.id !== agentId)); }, []);
  const handleReorderAgents = useCallback((reordered: AgentDef[]) => { setPipelineAgents(reordered); }, []);

  return (
    <div className="flex h-full flex-col overflow-y-auto bg-gray-50">
      <div className="relative flex-1 flex flex-col items-center px-4 sm:px-6 md:px-8 py-6 sm:py-10 max-w-3xl mx-auto w-full">
        {/* Back */}
        <div className="w-full mb-8">
          <motion.button
            initial={{ opacity: 0, x: -10 }}
            animate={{ opacity: 1, x: 0 }}
            onClick={onBack}
            className="flex items-center gap-2 text-xs text-gray-500 hover:text-gray-900 transition-colors"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to workflows
          </motion.button>
        </div>

        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          className="text-center mb-8 w-full"
        >
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-gray-100 mx-auto mb-3">
            <Icon className="h-5 w-5 text-gray-600" />
          </div>
          <h1 className="text-xl font-semibold text-gray-900 tracking-tight mb-1">{config.label}</h1>
          <p className="text-sm text-gray-500">{config.subtitle}</p>
        </motion.div>

        {/* Input Area */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.1 }}
          className="w-full"
        >
          <div className="rounded-lg border border-gray-200 bg-white overflow-hidden focus-within:border-blue-400 focus-within:ring-1 focus-within:ring-blue-400 transition-all shadow-sm">
            <textarea
              ref={inputRef}
              value={ideaInput}
              onChange={(e) => setIdeaInput(e.target.value)}
              placeholder={isListening ? "Listening... speak your idea" : "Describe your idea in as much or as little detail as you like..."}
              className="w-full resize-none bg-transparent text-sm text-gray-900 placeholder-gray-400 px-4 py-4 focus:outline-none min-h-[140px] max-h-[280px] leading-relaxed"
              rows={5}
              onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) handleRun(); }}
            />
            {/* Toolbar */}
            <div className="flex items-center justify-between px-4 py-3 border-t border-gray-100">
              <div className="flex items-center gap-2">
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
                  className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[11px] text-gray-500 hover:text-gray-900 hover:bg-gray-100 transition-all"
                  title="Attach file"
                >
                  <Paperclip className="h-3.5 w-3.5" /> Attach
                </button>
                <button
                  onClick={() => { if (isListening) stopListening(); else { preSpeechTextRef.current = ideaInput; startListening(); } }}
                  disabled={!speechSupported}
                  className={`flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[11px] transition-all ${
                    isListening ? "text-red-500 bg-red-50 animate-pulse" :
                    speechSupported ? "text-gray-500 hover:text-gray-900 hover:bg-gray-100" :
                    "text-gray-300 cursor-not-allowed"
                  }`}
                >
                  {isListening ? <MicOff className="h-3.5 w-3.5" /> : <Mic className="h-3.5 w-3.5" />}
                  {isListening ? "Stop" : "Voice"}
                </button>
              </div>
              <button
                onClick={handleRun}
                disabled={!ideaInput.trim() || pipelineAgents.length === 0}
                className="flex items-center gap-2 rounded-lg bg-blue-600 text-white px-4 py-2 text-sm font-medium hover:bg-blue-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <Play className="h-4 w-4" />
                {pipelineAgents.length === 0 ? "Add Agents First" : "Run Workflow"}
              </button>
            </div>
          </div>

          {/* Attached files */}
          {attachedFiles.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mt-3">
              {attachedFiles.map((file, idx) => (
                <span key={`${file.name}-${idx}`} className="inline-flex items-center gap-1 rounded-lg bg-gray-100 border border-gray-200 px-2.5 py-1 text-[10px] text-gray-600">
                  <File className="h-2.5 w-2.5" /> {file.name} <span className="text-gray-400">({file.size})</span>
                  <button onClick={() => setAttachedFiles((p) => p.filter((_, i) => i !== idx))} className="ml-1 text-gray-400 hover:text-red-500">
                    <X className="h-2.5 w-2.5" />
                  </button>
                </span>
              ))}
            </div>
          )}
        </motion.div>

        {/* View Agents */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.3 }}
          className="flex items-center gap-3 mt-6"
        >
          <button
            onClick={() => setShowAgents(true)}
            className="flex items-center gap-2 rounded-lg border border-gray-200 bg-white hover:bg-gray-50 hover:border-gray-300 px-4 py-2.5 text-xs text-gray-600 hover:text-gray-900 transition-all shadow-sm"
          >
            <Eye className="h-3.5 w-3.5" /> View &amp; Manage Agents ({pipelineAgents.length})
          </button>
        </motion.div>

        <p className="mt-4 text-[10px] text-gray-400">Ctrl+Enter to run · Attach files for context</p>
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
