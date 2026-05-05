"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import {
  X,
  Rocket,
  CheckCircle2,
  BookOpen,
  Plus,
  Trash2,
  GripVertical,
  ChevronDown,
  ChevronRight,
  ChevronLeft,
  Clock,
  Zap,
  FileText,
  Presentation,
  Layout,
  Mic,
  MicOff,
  Paperclip,
  Send,
  ArrowLeft,
  Play,
  RotateCcw,
  File,
} from "lucide-react";
import { PipelineGraph } from "./PipelineGraph";
import { AgentLibrary } from "./AgentLibrary";
import { LIBRARY_AGENTS } from "./AgentLibraryData";
import { useSpeechRecognition } from "@/hooks/useSpeechRecognition";
import type { AgentDef, PipelineRunState } from "@/types/index";

interface WorkflowViewProps {
  pipelineType: "user_stories" | "ppt" | "prototype";
  userMessage: string;
  onClose: () => void;
  websocketSend: (msg: string) => void;
  pipelineState?: PipelineRunState;
  onStartPipeline?: (type: string, message: string, agentIds?: string[]) => void;
  onResetPipeline?: () => void;
  onViewResults?: (pipelineType: string) => void;
}

type WorkflowStep = "select" | "build" | "running" | "complete";

const FEATURE_CARDS = [
  {
    id: "user_stories",
    label: "User Stories",
    tagline: "From idea to sprint-ready backlog",
    description: "Turn a rough concept into a complete product backlog — personas, epics, prioritized stories with acceptance criteria, and story points. Ready for your next sprint planning.",
    icon: FileText,
    color: "from-blue-500/20 to-cyan-500/20",
    borderColor: "border-blue-500/30",
    textColor: "text-blue-400",
    agents: 12,
  },
  {
    id: "ppt",
    label: "Presentation",
    tagline: "Pitch-perfect decks in seconds",
    description: "Craft a compelling narrative with structured slides, data visualizations, speaker notes, and a polished visual flow — whether you're pitching investors or aligning your team.",
    icon: Presentation,
    color: "from-amber-500/20 to-orange-500/20",
    borderColor: "border-amber-500/30",
    textColor: "text-amber-400",
    agents: 10,
  },
  {
    id: "prototype",
    label: "Prototype",
    tagline: "See your product before you build it",
    description: "Generate a clickable UI prototype with page layouts, navigation flows, component hierarchy, and interactive states — so you can validate ideas before writing a single line of code.",
    icon: Layout,
    color: "from-emerald-500/20 to-green-500/20",
    borderColor: "border-emerald-500/30",
    textColor: "text-emerald-400",
    agents: 12,
  },
];

export function WorkflowView({
  pipelineType: initialType,
  userMessage: externalMessage,
  onClose,
  websocketSend,
  pipelineState: externalPipelineState,
  onStartPipeline,
  onResetPipeline,
  onViewResults,
}: WorkflowViewProps) {
  const [step, setStep] = useState<WorkflowStep>("build");
  const [selectedType, setSelectedType] = useState<string>(initialType);
  const [ideaInput, setIdeaInput] = useState(externalMessage || "");
  const [isLibraryOpen, setIsLibraryOpen] = useState(false);
  const [expandedAgent, setExpandedAgent] = useState<string | null>(null);
  const [attachedFiles, setAttachedFiles] = useState<{ name: string; size: string }[]>([]);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const preSpeechTextRef = useRef("");

  // Speech recognition
  const { isListening, transcript, startListening, stopListening, isSupported: speechSupported } = useSpeechRecognition();

  // Sync transcript to input — replace (not append) using the pre-speech snapshot
  useEffect(() => {
    if (isListening && transcript) {
      setIdeaInput(preSpeechTextRef.current ? `${preSpeechTextRef.current} ${transcript}` : transcript);
    }
  }, [transcript, isListening]);

  // Pipeline agents for the selected type
  const [pipelineAgents, setPipelineAgents] = useState<AgentDef[]>([]);

  // Drag state
  const [draggedIdx, setDraggedIdx] = useState<number | null>(null);
  const [dragOverIdx, setDragOverIdx] = useState<number | null>(null);

  // Update agents when type changes
  useEffect(() => {
    setPipelineAgents(
      LIBRARY_AGENTS.filter((a) => a.pipeline_type === selectedType).sort((a, b) => a.order - b.order)
    );
  }, [selectedType]);

  // External pipeline state
  const pipelineState = externalPipelineState || {
    isRunning: false,
    pipeline_type: "",
    agents: [],
    currentAgentIndex: -1,
    totalDuration: null,
    completedCount: 0,
  };

  // Detect when pipeline starts running or completes
  useEffect(() => {
    if (pipelineState.isRunning && step !== "running") {
      setStep("running");
    }
    if (!pipelineState.isRunning && pipelineState.agents.length > 0 && pipelineState.completedCount === pipelineState.agents.length && step === "running") {
      setStep("complete");
    }
  }, [pipelineState.isRunning, pipelineState.agents.length, pipelineState.completedCount, step]);

  // Handlers
  const handleSelectFeature = (featureId: string) => {
    setSelectedType(featureId);
    setStep("build");
    setTimeout(() => inputRef.current?.focus(), 100);
  };

  const handleBack = () => {
    if (step === "build") onClose(); // Go back to home (card selection)
  };

  const handleRun = () => {
    if (!ideaInput.trim()) return;
    if (onStartPipeline) {
      const agentIds = pipelineAgents.map((a) => a.id);
      onStartPipeline(selectedType, ideaInput.trim(), agentIds);
    }
  };

  const handleRunAnother = () => {
    if (onResetPipeline) onResetPipeline();
    setIdeaInput("");
    onClose(); // Go back to home
  };

  const handleAddAgent = useCallback((agent: AgentDef) => {
    setPipelineAgents((prev) => {
      if (prev.find((a) => a.id === agent.id)) return prev;
      return [...prev, { ...agent, order: prev.length + 1 }];
    });
  }, []);

  const handleRemoveAgent = useCallback((agentId: string) => {
    setPipelineAgents((prev) => prev.filter((a) => a.id !== agentId));
  }, []);

  // Drag handlers
  const handleDragStart = useCallback((idx: number) => setDraggedIdx(idx), []);
  const handleDragOver = useCallback((e: React.DragEvent, idx: number) => {
    e.preventDefault();
    setDragOverIdx(idx);
  }, []);
  const handleDrop = useCallback((idx: number) => {
    if (draggedIdx === null || draggedIdx === idx) { setDraggedIdx(null); setDragOverIdx(null); return; }
    setPipelineAgents((prev) => {
      const updated = [...prev];
      const [moved] = updated.splice(draggedIdx, 1);
      updated.splice(idx, 0, moved);
      return updated;
    });
    setDraggedIdx(null);
    setDragOverIdx(null);
  }, [draggedIdx]);
  const handleDragEnd = useCallback(() => { setDraggedIdx(null); setDragOverIdx(null); }, []);

  const totalEstimatedTime = pipelineAgents.reduce((sum, a) => sum + a.estimated_duration, 0);
  const selectedFeature = FEATURE_CARDS.find((f) => f.id === selectedType);

  return (
    <div className="flex flex-col h-full" style={{ backgroundColor: "var(--theme-bg)" }}>
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-grey/10">
        <div className="flex items-center gap-3">
          {step === "build" && (
            <button
              onClick={handleBack}
              className="flex items-center justify-center rounded-lg p-1.5 text-grey/50 hover:text-white hover:bg-white/5 transition-all"
              aria-label="Back"
            >
              <ArrowLeft className="h-4 w-4" />
            </button>
          )}
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-blue-500/20 to-purple-500/20 border border-white/10">
            <Rocket className="h-3.5 w-3.5 text-white" />
          </div>
          <div>
            <h2 className="text-sm font-semibold text-white">
              {step === "select" && "IdeaFlow AI Design Studio"}
              {step === "build" && (selectedFeature?.label || "Build")}
              {step === "running" && "Running Pipeline"}
              {step === "complete" && "Pipeline Complete"}
            </h2>
            {step === "build" && (
              <p className="text-[10px] text-grey/50">{pipelineAgents.length} agents • ~{Math.ceil(totalEstimatedTime / 60)} min</p>
            )}
          </div>
        </div>
        <button
          onClick={onClose}
          className="flex items-center justify-center rounded-lg p-2 text-grey/50 hover:text-white hover:bg-white/5 transition-all"
          aria-label="Close"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* Body */}
      <div className="flex-1 min-h-0 overflow-y-auto">
        <AnimatePresence mode="wait">
          {/* ============ STEP 1: Feature Selection ============ */}
          {step === "select" && (
            <motion.div
              key="select"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              transition={{ duration: 0.25 }}
              className="flex flex-col items-center justify-center h-full px-6 py-8"
            >
              <div className="text-center mb-8">
                <h3 className="text-base font-semibold text-white mb-2">What would you like to create?</h3>
                <p className="text-xs text-grey/50">Pick a workflow and let our AI agents handle the heavy lifting</p>
              </div>

              <div className="w-full max-w-sm space-y-3">
                {FEATURE_CARDS.map((card) => {
                  const Icon = card.icon;
                  return (
                    <motion.button
                      key={card.id}
                      whileHover={{ scale: 1.02, y: -2 }}
                      whileTap={{ scale: 0.98 }}
                      onClick={() => handleSelectFeature(card.id)}
                      className={`w-full flex items-start gap-4 rounded-xl border ${card.borderColor} bg-gradient-to-r ${card.color} p-4 text-left transition-all duration-200 hover:shadow-lg hover:shadow-black/20`}
                    >
                      <div className={`flex h-10 w-10 items-center justify-center rounded-xl bg-black/30 border border-white/10 flex-shrink-0 mt-0.5`}>
                        <Icon className={`h-5 w-5 ${card.textColor}`} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between">
                          <span className="text-sm font-medium text-white">{card.label}</span>
                          <div className="flex items-center gap-1 text-[10px] text-grey/40">
                            <Zap className="h-2.5 w-2.5" />
                            {card.agents} agents
                          </div>
                        </div>
                        <p className={`text-[10px] ${card.textColor} font-medium mt-0.5`}>{card.tagline}</p>
                        <p className="text-[10px] text-grey/55 mt-1 leading-relaxed">{card.description}</p>
                      </div>
                    </motion.button>
                  );
                })}
              </div>
            </motion.div>
          )}

          {/* ============ STEP 2: Build View ============ */}
          {step === "build" && (
            <motion.div
              key="build"
              initial={{ opacity: 0, x: 30 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -30 }}
              transition={{ duration: 0.25 }}
              className="flex flex-col h-full"
            >
              {/* Idea Input Area */}
              <div className="px-5 py-4 border-b border-grey/10">
                <label className="text-[11px] text-grey/60 font-medium mb-2 block">Describe your idea</label>
                <div className="relative rounded-xl border border-grey/15 bg-white/[0.02] overflow-hidden focus-within:border-grey/30 transition-colors">
                  <textarea
                    ref={inputRef}
                    value={ideaInput}
                    onChange={(e) => setIdeaInput(e.target.value)}
                    placeholder={isListening ? "🎙️ Listening... speak your idea" : "Describe what you want to build..."}
                    className="w-full resize-none bg-transparent text-xs text-white placeholder-grey/40 px-4 py-3 pr-24 focus:outline-none min-h-[72px] max-h-[120px]"
                    rows={3}
                    onKeyDown={(e) => { if (e.key === "Enter" && e.metaKey) handleRun(); }}
                  />
                  {/* Action buttons inside input */}
                  <div className="absolute bottom-2 right-2 flex items-center gap-1">
                    <input
                      ref={fileInputRef}
                      type="file"
                      multiple
                      accept=".pdf,.doc,.docx,.pptx,.txt,.md,.json,.csv"
                      className="hidden"
                      onChange={(e) => {
                        const files = e.target.files;
                        if (files) {
                          const newFiles = Array.from(files).map((f) => ({
                            name: f.name,
                            size: f.size < 1024 ? `${f.size}B` : f.size < 1048576 ? `${(f.size / 1024).toFixed(1)}KB` : `${(f.size / 1048576).toFixed(1)}MB`,
                          }));
                          setAttachedFiles((prev) => [...prev, ...newFiles]);
                          // Append file names to the idea input as context
                          const fileNames = newFiles.map((f) => f.name).join(", ");
                          setIdeaInput((prev) => prev ? `${prev}\n\n[Attached: ${fileNames}]` : `[Attached: ${fileNames}]`);
                        }
                        e.target.value = "";
                      }}
                    />
                    <button
                      onClick={() => fileInputRef.current?.click()}
                      className="p-1.5 rounded-md text-grey/40 hover:text-white hover:bg-white/5 transition-all"
                      title="Attach file (PDF, DOCX, PPTX, TXT)"
                    >
                      <Paperclip className="h-3.5 w-3.5" />
                    </button>
                    <button
                      onClick={() => {
                        if (isListening) {
                          stopListening();
                        } else {
                          preSpeechTextRef.current = ideaInput;
                          startListening();
                        }
                      }}
                      disabled={!speechSupported}
                      className={`p-1.5 rounded-md transition-all ${
                        isListening
                          ? "text-red-400 bg-red-500/10 animate-pulse"
                          : speechSupported
                          ? "text-grey/40 hover:text-white hover:bg-white/5"
                          : "text-grey/20 cursor-not-allowed"
                      }`}
                      title={!speechSupported ? "Speech recognition not supported in this browser" : isListening ? "Stop listening" : "Voice input"}
                    >
                      {isListening ? <MicOff className="h-3.5 w-3.5" /> : <Mic className="h-3.5 w-3.5" />}
                    </button>
                  </div>
                </div>

                {/* Attached files display */}
                {attachedFiles.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 mt-2">
                    {attachedFiles.map((file, idx) => (
                      <span
                        key={`${file.name}-${idx}`}
                        className="inline-flex items-center gap-1 rounded-md bg-white/5 border border-grey/15 px-2 py-1 text-[10px] text-grey/70"
                      >
                        <File className="h-2.5 w-2.5" />
                        {file.name}
                        <span className="text-grey/40">({file.size})</span>
                        <button
                          onClick={() => setAttachedFiles((prev) => prev.filter((_, i) => i !== idx))}
                          className="ml-0.5 text-grey/40 hover:text-red-400 transition-colors"
                        >
                          <X className="h-2.5 w-2.5" />
                        </button>
                      </span>
                    ))}
                  </div>
                )}
              </div>

              {/* Agent Workflow Section */}
              <div className="flex-1 min-h-0 overflow-y-auto">
                {/* Section header */}
                <div className="flex items-center justify-between px-5 py-3 sticky top-0 z-10 backdrop-blur-sm" style={{ backgroundColor: "var(--theme-bg)" }}>
                  <div className="flex items-center gap-2">
                    <Zap className="h-3 w-3 text-amber-400" />
                    <span className="text-[11px] font-medium text-white/80">Workflow Agents</span>
                    <span className="text-[10px] text-grey/40">({pipelineAgents.length})</span>
                  </div>
                  <button
                    onClick={() => setIsLibraryOpen(true)}
                    className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[10px] font-medium text-grey/60 hover:text-white bg-white/5 hover:bg-white/10 border border-white/10 transition-all"
                  >
                    <BookOpen className="h-3 w-3" />
                    Browse Library
                  </button>
                </div>

                {/* Agent list */}
                <div className="px-5 pb-4 space-y-1.5">
                  {pipelineAgents.map((agent, idx) => (
                    <div
                      key={agent.id}
                      draggable
                      onDragStart={() => handleDragStart(idx)}
                      onDragOver={(e) => handleDragOver(e, idx)}
                      onDrop={() => handleDrop(idx)}
                      onDragEnd={handleDragEnd}
                      className="relative"
                    >
                      {dragOverIdx === idx && draggedIdx !== null && draggedIdx !== idx && (
                        <div className="absolute -top-0.5 left-0 right-0 h-0.5 bg-blue-400 rounded-full z-10" />
                      )}
                      <div className={`flex items-center gap-2 rounded-lg border border-grey/10 px-2.5 py-2 bg-white/[0.01] hover:bg-white/[0.03] hover:border-grey/20 transition-all ${draggedIdx === idx ? "opacity-40 scale-[0.98]" : ""}`}>
                        <GripVertical className="h-3 w-3 text-grey/25 cursor-grab active:cursor-grabbing flex-shrink-0" />
                        <div className="flex h-6 w-6 items-center justify-center rounded-md bg-white/5 text-[11px] flex-shrink-0">{agent.icon}</div>
                        <div
                          className="flex-1 min-w-0 cursor-pointer"
                          onClick={() => setExpandedAgent(expandedAgent === agent.id ? null : agent.id)}
                        >
                          <span className="text-[11px] font-medium text-white/90 truncate block">{agent.name}</span>
                          {expandedAgent === agent.id && (
                            <p className="text-[10px] text-grey/50 mt-0.5 leading-relaxed">{agent.description}</p>
                          )}
                        </div>
                        <span className="text-[9px] text-grey/35 flex-shrink-0">~{agent.estimated_duration}s</span>
                        <button
                          onClick={() => handleRemoveAgent(agent.id)}
                          className="p-0.5 text-grey/25 hover:text-red-400 transition-colors flex-shrink-0"
                          aria-label="Remove"
                        >
                          <Trash2 className="h-2.5 w-2.5" />
                        </button>
                      </div>
                    </div>
                  ))}

                  {/* Add agent button */}
                  <button
                    onClick={() => setIsLibraryOpen(true)}
                    className="w-full flex items-center justify-center gap-1.5 rounded-lg border border-dashed border-grey/15 py-2 text-[10px] text-grey/40 hover:text-white hover:border-grey/30 hover:bg-white/[0.02] transition-all"
                  >
                    <Plus className="h-3 w-3" />
                    Add Agent
                  </button>
                </div>
              </div>

              {/* Run button */}
              <div className="border-t border-grey/10 px-5 py-3">
                <motion.button
                  whileHover={{ scale: 1.01 }}
                  whileTap={{ scale: 0.98 }}
                  onClick={handleRun}
                  disabled={!ideaInput.trim()}
                  className="w-full flex items-center justify-center gap-2 rounded-xl bg-white text-black px-5 py-3 text-sm font-semibold transition-all duration-200 hover:bg-white/90 shadow-lg shadow-white/10 disabled:opacity-40 disabled:cursor-not-allowed disabled:shadow-none"
                >
                  <Play className="h-4 w-4" />
                  Run Workflow
                </motion.button>
              </div>
            </motion.div>
          )}

          {/* ============ STEP 3: Running ============ */}
          {step === "running" && (
            <motion.div
              key="running"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="h-full"
            >
              <PipelineGraph
                agents={pipelineState.agents}
                currentIndex={pipelineState.currentAgentIndex}
                pipelineType={pipelineState.pipeline_type || selectedType}
                totalDuration={pipelineState.totalDuration}
              />
            </motion.div>
          )}

          {/* ============ STEP 4: Complete ============ */}
          {step === "complete" && (
            <motion.div
              key="complete"
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.3 }}
              className="h-full"
            >
              <PipelineGraph
                agents={pipelineState.agents}
                currentIndex={pipelineState.currentAgentIndex}
                pipelineType={pipelineState.pipeline_type || selectedType}
                totalDuration={pipelineState.totalDuration}
              />
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Footer for complete state */}
      {step === "complete" && (
        <div className="border-t border-grey/10 px-5 py-3 space-y-2">
          <motion.button
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            whileHover={{ scale: 1.01 }}
            whileTap={{ scale: 0.98 }}
            onClick={() => onViewResults?.(selectedType)}
            className="w-full flex items-center justify-center gap-2 rounded-xl bg-green-500/20 border border-green-500/30 text-green-300 px-5 py-2.5 text-sm font-medium transition-all hover:bg-green-500/30"
          >
            <CheckCircle2 className="h-4 w-4" />
            View Results
            {pipelineState.totalDuration !== null && (
              <span className="text-[10px] text-green-400/60 ml-1">({pipelineState.totalDuration.toFixed(1)}s)</span>
            )}
          </motion.button>
          <motion.button
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.05 }}
            whileHover={{ scale: 1.01 }}
            whileTap={{ scale: 0.98 }}
            onClick={handleRunAnother}
            className="w-full flex items-center justify-center gap-2 rounded-xl bg-white/5 border border-white/10 text-grey/70 px-5 py-2 text-xs font-medium transition-all hover:bg-white/10 hover:text-white"
          >
            <RotateCcw className="h-3.5 w-3.5" />
            Run Another Pipeline
          </motion.button>
        </div>
      )}

      {/* Agent Library */}
      <AgentLibrary
        isOpen={isLibraryOpen}
        onClose={() => setIsLibraryOpen(false)}
        onAddAgent={handleAddAgent}
      />
    </div>
  );
}
