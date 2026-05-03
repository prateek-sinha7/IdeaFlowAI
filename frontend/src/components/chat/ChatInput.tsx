"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "motion/react";
import {
  SendHorizontal,
  Plus,
  Brain,
  FlaskConical,
  Globe,
  FileQuestion,
  Paperclip,
  Mic,
  MicOff,
  X,
} from "lucide-react";
import { useSpeechRecognition } from "@/hooks/useSpeechRecognition";

export type ChatMode = "default" | "thinking" | "deep_research" | "web_search" | "quiz";

interface ModeOption {
  id: ChatMode;
  icon: React.ElementType;
  label: string;
  description: string;
  emoji: string;
}

const MODE_OPTIONS: ModeOption[] = [
  { id: "thinking", icon: Brain, label: "Thinking", description: "Deep analytical reasoning", emoji: "🧠" },
  { id: "deep_research", icon: FlaskConical, label: "Deep Research", description: "Comprehensive research report", emoji: "🔬" },
  { id: "web_search", icon: Globe, label: "Web Search", description: "Search-style results", emoji: "🌐" },
  { id: "quiz", icon: FileQuestion, label: "Quizzes", description: "Interactive learning quiz", emoji: "📝" },
];

export interface ChatInputProps {
  onSendMessage: (content: string) => void;
  onSendMessageWithMode?: (content: string, mode: ChatMode) => void;
  isStreaming: boolean;
}

export function ChatInput({ onSendMessage, onSendMessageWithMode, isStreaming }: ChatInputProps) {
  const [value, setValue] = useState("");
  const [activeMode, setActiveMode] = useState<ChatMode>("default");
  const [menuOpen, setMenuOpen] = useState(false);
  const [showComingSoon, setShowComingSoon] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  const { isListening, transcript, startListening, stopListening, isSupported: speechSupported } = useSpeechRecognition();

  useEffect(() => { if (transcript) setValue(transcript); }, [transcript]);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false);
    };
    if (menuOpen) document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [menuOpen]);

  useEffect(() => {
    if (showComingSoon) { const t = setTimeout(() => setShowComingSoon(false), 2500); return () => clearTimeout(t); }
  }, [showComingSoon]);

  const handleSend = useCallback(() => {
    const trimmed = value.trim();
    if (trimmed && !isStreaming) {
      if (activeMode !== "default" && onSendMessageWithMode) onSendMessageWithMode(trimmed, activeMode);
      else onSendMessage(trimmed);
      setValue("");
      setActiveMode("default");
      if (textareaRef.current) textareaRef.current.style.height = "auto";
    }
  }, [value, isStreaming, onSendMessage, onSendMessageWithMode, activeMode]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); }
  };

  useEffect(() => {
    const ta = textareaRef.current;
    if (ta) { ta.style.height = "auto"; ta.style.height = `${Math.min(ta.scrollHeight, 240)}px`; }
  }, [value]);

  const handleModeSelect = (mode: ChatMode) => { setActiveMode(mode); setMenuOpen(false); textareaRef.current?.focus(); };
  const handleMicClick = () => { if (isListening) stopListening(); else startListening(); };
  const canSend = value.trim().length > 0 && !isStreaming;

  return (
    <div className="p-4 pb-3 bg-gradient-to-t from-black via-black/95 to-transparent">
      <div className="mx-auto max-w-4xl">
        {/* Active mode badge */}
        <AnimatePresence>
          {activeMode !== "default" && (
            <motion.div
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 6 }}
              transition={{ duration: 0.2 }}
              className="mb-2.5"
            >
              <span className="inline-flex items-center gap-1.5 rounded-full bg-navy/60 border border-grey/20 px-3.5 py-1.5 text-xs text-white/90 shadow-lg shadow-navy/20">
                <span>{MODE_OPTIONS.find((m) => m.id === activeMode)?.emoji}</span>
                <span className="font-medium">{MODE_OPTIONS.find((m) => m.id === activeMode)?.label}</span>
                <button onClick={() => setActiveMode("default")} className="ml-1 rounded-full p-0.5 hover:bg-white/15 transition-colors" aria-label="Remove mode">
                  <X className="h-3 w-3 text-grey/70" />
                </button>
              </span>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Coming soon toast */}
        <AnimatePresence>
          {showComingSoon && (
            <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 6 }} className="mb-2.5 flex justify-center">
              <span className="rounded-lg bg-navy/80 border border-grey/20 px-4 py-2 text-xs text-grey shadow-lg">📎 File uploads coming soon</span>
            </motion.div>
          )}
        </AnimatePresence>

        {/* ===== MAIN INPUT CONTAINER ===== */}
        <div className="input-glow rounded-2xl border border-grey/20 shadow-xl shadow-black/40 transition-all duration-300 focus-within:border-grey/35 focus-within:shadow-navy/20" style={{ backgroundColor: 'var(--theme-input-bg)' }}>
          {/* Textarea area — tall and prominent */}
          <div className="px-4 pt-3 pb-1.5">
            <textarea
              ref={textareaRef}
              value={value}
              onChange={(e) => setValue(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={isListening ? "🎙️ Listening..." : "Message IdeaFlow AI..."}
              disabled={isStreaming}
              rows={2}
              className="w-full resize-none bg-transparent text-white text-[15px] placeholder-grey/35 focus:outline-none disabled:opacity-50 leading-relaxed min-h-[52px] max-h-[240px] overflow-y-auto"
              aria-label="Chat message input"
            />
          </div>

          {/* Bottom toolbar — icons row */}
          <div className="flex items-center justify-between px-3 pb-3 pt-1">
            {/* Left side — mode menu + file */}
            <div className="flex items-center gap-1">
              {/* Plus / Mode menu */}
              <div className="relative" ref={menuRef}>
                <motion.button
                  whileHover={{ scale: 1.08 }}
                  whileTap={{ scale: 0.92 }}
                  onClick={() => setMenuOpen(!menuOpen)}
                  className={`flex items-center justify-center rounded-lg p-2 transition-all duration-200 ${
                    menuOpen ? "bg-white/10 text-white" : "text-grey/50 hover:text-white hover:bg-white/5"
                  }`}
                  aria-label="Open mode menu"
                >
                  <Plus className={`h-5 w-5 transition-transform duration-200 ${menuOpen ? "rotate-45" : ""}`} />
                </motion.button>

                {/* Mode menu popup */}
                <AnimatePresence>
                  {menuOpen && (
                    <motion.div
                      initial={{ opacity: 0, y: 8, scale: 0.95 }}
                      animate={{ opacity: 1, y: 0, scale: 1 }}
                      exit={{ opacity: 0, y: 8, scale: 0.95 }}
                      transition={{ duration: 0.15 }}
                      className="absolute bottom-full left-0 mb-2 w-64 rounded-xl overflow-hidden z-50 glass-action-bar"
                    >
                      <div className="p-1.5">
                        {MODE_OPTIONS.map((option) => (
                          <button
                            key={option.id}
                            onClick={() => handleModeSelect(option.id)}
                            className={`flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left transition-colors duration-150 ${
                              activeMode === option.id ? "bg-white/10 text-white" : "text-grey/80 hover:text-white hover:bg-white/5"
                            }`}
                          >
                            <span className="text-base">{option.emoji}</span>
                            <div className="flex-1 min-w-0">
                              <div className="text-sm font-medium">{option.label}</div>
                              <div className="text-[11px] text-grey/50 truncate">{option.description}</div>
                            </div>
                          </button>
                        ))}
                        <button
                          onClick={() => { setShowComingSoon(true); setMenuOpen(false); }}
                          className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-grey/80 hover:text-white hover:bg-white/5 transition-colors duration-150"
                        >
                          <Paperclip className="h-4 w-4 text-grey/50" />
                          <div className="flex-1 min-w-0">
                            <div className="text-sm font-medium">Add Files</div>
                            <div className="text-[11px] text-grey/50">Upload documents</div>
                          </div>
                        </button>
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>

              {/* Mic button */}
              <motion.button
                whileHover={{ scale: 1.08 }}
                whileTap={{ scale: 0.92 }}
                onClick={handleMicClick}
                disabled={!speechSupported || isStreaming}
                className={`flex items-center justify-center rounded-lg p-2 transition-all duration-200 ${
                  isListening
                    ? "bg-red-500/20 text-red-400 animate-pulse"
                    : speechSupported
                    ? "text-grey/50 hover:text-white hover:bg-white/5"
                    : "text-grey/25 cursor-not-allowed"
                }`}
                aria-label={isListening ? "Stop listening" : "Start voice input"}
                title={!speechSupported ? "Speech recognition not supported" : isListening ? "Stop listening" : "Voice input"}
              >
                {isListening ? <MicOff className="h-5 w-5" /> : <Mic className="h-5 w-5" />}
              </motion.button>
            </div>

            {/* Right side — send button */}
            <motion.button
              whileHover={canSend ? { scale: 1.05 } : {}}
              whileTap={canSend ? { scale: 0.95 } : {}}
              onClick={handleSend}
              disabled={!canSend}
              className={`flex items-center justify-center rounded-xl px-4 py-2 transition-all duration-200 ${
                canSend
                  ? "bg-white text-black font-medium hover:bg-white/90 shadow-lg shadow-white/10"
                  : "bg-grey/10 text-grey/25 cursor-not-allowed"
              }`}
              aria-label="Send message"
            >
              <SendHorizontal className="h-4 w-4" />
            </motion.button>
          </div>
        </div>

        <p className="mt-2 text-center text-[10px] text-grey/25">
          Enter to send · Shift+Enter for new line
        </p>
      </div>
    </div>
  );
}
