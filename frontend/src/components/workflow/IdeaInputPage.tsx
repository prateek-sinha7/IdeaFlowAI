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

const TYPE_CONFIG: Record<WorkflowType, { label: string; subtitle: string; icon: typeof FileText; color: string }> = {
  user_stories: { label: "Turn an idea into product requirements", subtitle: "Shape a fuzzy idea into a PRD with epics, user stories, and Gherkin criteria.", icon: FileText, color: "text-blue-600" },
  prototype: { label: "Build a clickable prototype", subtitle: "Go from stories or sketches to a high-fidelity, navigable prototype in minutes.", icon: Layout, color: "text-emerald-600" },
  ppt: { label: "Create a Powerpoint Presentation", subtitle: "Hand us a brief and we'll deliver a polished slide deck with charts, data, and speaker notes.", icon: Presentation, color: "text-amber-600" },
  validate_pitch: { label: "Validate an idea, then pitch it", subtitle: "Stress-test the concept, size the market, and turn it into an investor-ready deck.", icon: FileText, color: "text-violet-600" },
  app_builder: { label: "Build an app from existing material", subtitle: "Hand us a deck, a repo, or a brief — we'll deliver a working app, end to end.", icon: Layout, color: "text-orange-600" },
  reverse_engineer: { label: "Reverse-engineer a codebase", subtitle: "Map architecture, dependencies, risks, and hidden user journeys from any repo.", icon: FileText, color: "text-rose-600" },
  custom: { label: "Design your own workflow", subtitle: "Compose specialist agents and skills into a bespoke pipeline for anything else.", icon: Layout, color: "text-slate-600" },
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

  const config = TYPE_CONFIG[workflowType];
  const Icon = config.icon;

  useEffect(() => { if (isListening && transcript) setIdeaInput(preSpeechTextRef.current ? `${preSpeechTextRef.current} ${transcript}` : transcript); }, [transcript, isListening]);
  useEffect(() => { setTimeout(() => inputRef.current?.focus(), 200); }, []);

  const handleRun = () => { if (!ideaInput.trim()) return; onRun(ideaInput.trim(), pipelineAgents.map((a) => a.id)); };
  const handleAddAgent = useCallback((agent: AgentDef) => { setPipelineAgents((prev) => prev.find((a) => a.id === agent.id) ? prev : [...prev, { ...agent, order: prev.length + 1 }]); }, []);
  const handleRemoveAgent = useCallback((agentId: string) => { setPipelineAgents((prev) => prev.filter((a) => a.id !== agentId)); }, []);
  const handleReorderAgents = useCallback((reordered: AgentDef[]) => { setPipelineAgents(reordered); }, []);

  return (
    <div className="flex h-full flex-col overflow-y-auto bg-[#f5f4ed]">
      <div className="relative flex-1 flex flex-col items-center px-8 py-10 max-w-3xl mx-auto w-full">
        {/* Back */}
        <div className="w-full mb-8">
          <motion.button initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} onClick={onBack} className="flex items-center gap-2 text-xs text-[#5e5d59] hover:text-[#141413] transition-colors">
            <ArrowLeft className="h-4 w-4" />
            Back to workflows
          </motion.button>
        </div>

        {/* Header */}
        <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }} className="text-center mb-10 w-full">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-[#faf9f5] border border-[#e8e6dc] mx-auto mb-4">
            <Icon className={`h-6 w-6 ${config.color}`} />
          </div>
          <h1 className="text-xl md:text-2xl font-bold text-[#141413] tracking-tight mb-2">{config.label}</h1>
          <p className="text-sm text-[#5e5d59]">{config.subtitle}</p>
        </motion.div>

        {/* Input Area */}
        <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, delay: 0.1 }} className="w-full">
          <div className="rounded-2xl border border-[#e8e6dc] bg-white overflow-hidden focus-within:border-[#c96442]/40 focus-within:shadow-lg focus-within:shadow-[#c96442]/5 transition-all shadow-sm">
            <textarea
              ref={inputRef}
              value={ideaInput}
              onChange={(e) => setIdeaInput(e.target.value)}
              placeholder={isListening ? "🎙️ Listening... speak your idea" : "Describe your idea in as much or as little detail as you like..."}
              className="w-full resize-none bg-transparent text-sm text-[#141413] placeholder-[#87867f] px-6 py-5 focus:outline-none min-h-[140px] max-h-[280px] leading-relaxed"
              rows={5}
              onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) handleRun(); }}
            />
            {/* Toolbar */}
            <div className="flex items-center justify-between px-5 py-3 border-t border-[#f0eee6]">
              <div className="flex items-center gap-2">
                <input ref={fileInputRef} type="file" multiple accept=".pdf,.doc,.docx,.pptx,.txt,.md,.json,.csv" className="hidden" onChange={(e) => { const files = e.target.files; if (files) { const nf = Array.from(files).map((f) => ({ name: f.name, size: f.size < 1024 ? `${f.size}B` : f.size < 1048576 ? `${(f.size / 1024).toFixed(1)}KB` : `${(f.size / 1048576).toFixed(1)}MB` })); setAttachedFiles((p) => [...p, ...nf]); setIdeaInput((p) => p ? `${p}\n\n[Attached: ${nf.map((f) => f.name).join(", ")}]` : `[Attached: ${nf.map((f) => f.name).join(", ")}]`); } e.target.value = ""; }} />
                <button onClick={() => fileInputRef.current?.click()} className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[11px] text-[#5e5d59] hover:text-[#141413] hover:bg-[#f5f4ed] transition-all" title="Attach file">
                  <Paperclip className="h-3.5 w-3.5" /> Attach
                </button>
                <button onClick={() => { if (isListening) stopListening(); else { preSpeechTextRef.current = ideaInput; startListening(); } }} disabled={!speechSupported} className={`flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[11px] transition-all ${isListening ? "text-red-500 bg-red-50 animate-pulse" : speechSupported ? "text-[#5e5d59] hover:text-[#141413] hover:bg-[#f5f4ed]" : "text-[#87867f] cursor-not-allowed"}`}>
                  {isListening ? <MicOff className="h-3.5 w-3.5" /> : <Mic className="h-3.5 w-3.5" />}
                  {isListening ? "Stop" : "Voice"}
                </button>
              </div>
              <motion.button whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.97 }} onClick={handleRun} disabled={!ideaInput.trim()} className="flex items-center gap-2 rounded-xl bg-[#c96442] text-white px-5 py-2.5 text-sm font-semibold transition-all hover:bg-[#b5573a] shadow-md shadow-[#c96442]/20 disabled:opacity-30 disabled:cursor-not-allowed disabled:shadow-none">
                <Play className="h-4 w-4" /> Run Workflow
              </motion.button>
            </div>
          </div>

          {/* Attached files */}
          {attachedFiles.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mt-3">
              {attachedFiles.map((file, idx) => (
                <span key={`${file.name}-${idx}`} className="inline-flex items-center gap-1 rounded-lg bg-[#faf9f5] border border-[#e8e6dc] px-2.5 py-1 text-[10px] text-[#5e5d59]">
                  <File className="h-2.5 w-2.5" /> {file.name} <span className="text-[#87867f]">({file.size})</span>
                  <button onClick={() => setAttachedFiles((p) => p.filter((_, i) => i !== idx))} className="ml-1 text-[#87867f] hover:text-red-500"><X className="h-2.5 w-2.5" /></button>
                </span>
              ))}
            </div>
          )}
        </motion.div>

        {/* View Agents */}
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.3 }} className="flex items-center gap-3 mt-6">
          <button onClick={() => setShowAgents(true)} className="flex items-center gap-2 rounded-xl border border-[#e8e6dc] bg-white hover:bg-[#faf9f5] hover:border-[#c96442]/30 px-4 py-2.5 text-xs text-[#5e5d59] hover:text-[#141413] transition-all shadow-sm">
            <Eye className="h-3.5 w-3.5" /> View & Manage Agents ({pipelineAgents.length})
          </button>
        </motion.div>

        <p className="mt-4 text-[10px] text-[#87867f]">Ctrl+Enter to run • Attach files for context</p>
      </div>

      <AgentsPopup isOpen={showAgents} onClose={() => setShowAgents(false)} agents={pipelineAgents} pipelineType={workflowType} onAddAgent={handleAddAgent} onRemoveAgent={handleRemoveAgent} onReorder={handleReorderAgents} />
    </div>
  );
}
