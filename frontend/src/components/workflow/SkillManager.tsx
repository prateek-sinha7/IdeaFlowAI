"use client";

import { useState, useCallback } from "react";
import { motion, AnimatePresence } from "motion/react";
import {
  X,
  FileText,
  Upload,
  Trash2,
  Eye,
  Save,
  Plus,
  BookMarked,
} from "lucide-react";
import { getToken } from "@/lib/api";

interface SkillManagerProps {
  isOpen: boolean;
  onClose: () => void;
  agentId?: string;
  agentName?: string;
}

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/**
 * Skill Manager — View, create, and attach skill files to agents.
 * Inspired by Anthropic's SKILL.md format.
 */
export function SkillManager({ isOpen, onClose, agentId, agentName }: SkillManagerProps) {
  const [skillContent, setSkillContent] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState(false);

  // Load skill content when opened
  const loadSkill = useCallback(async () => {
    if (!agentId) return;
    const token = getToken();
    if (!token) return;

    setIsLoading(true);
    setLoadError(null);

    try {
      const response = await fetch(`${BASE_URL}/api/agents/skills/${agentId}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (response.ok) {
        const data = await response.json();
        setSkillContent(data.content || "");
      } else {
        setSkillContent("");
      }
    } catch (err) {
      setLoadError("Failed to load skill");
      console.error("Failed to load skill:", err);
    } finally {
      setIsLoading(false);
    }
  }, [agentId]);

  // Save skill content
  const saveSkill = useCallback(async () => {
    if (!agentId) return;
    const token = getToken();
    if (!token) return;

    setIsSaving(true);
    setSaveSuccess(false);

    try {
      const response = await fetch(`${BASE_URL}/api/agents/skills`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ agent_id: agentId, content: skillContent }),
      });

      if (response.ok) {
        setSaveSuccess(true);
        setIsEditing(false);
        setTimeout(() => setSaveSuccess(false), 2000);
      }
    } catch (err) {
      console.error("Failed to save skill:", err);
    } finally {
      setIsSaving(false);
    }
  }, [agentId, skillContent]);

  // Delete skill
  const deleteSkill = useCallback(async () => {
    if (!agentId) return;
    const token = getToken();
    if (!token) return;

    try {
      await fetch(`${BASE_URL}/api/agents/skills/${agentId}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      setSkillContent("");
      setIsEditing(false);
    } catch (err) {
      console.error("Failed to delete skill:", err);
    }
  }, [agentId]);

  // Handle file upload
  const handleFileUpload = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (event) => {
      const content = event.target?.result as string;
      setSkillContent(content);
      setIsEditing(true);
    };
    reader.readAsText(file);
  }, []);

  // Load skill when panel opens
  useState(() => {
    if (isOpen && agentId) {
      loadSkill();
    }
  });

  if (!isOpen) return null;

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      >
        <motion.div
          initial={{ opacity: 0, scale: 0.95, y: 20 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95, y: 20 }}
          transition={{ duration: 0.25, ease: "easeOut" }}
          className="w-full max-w-2xl max-h-[80vh] flex flex-col rounded-2xl border shadow-2xl overflow-hidden"
          style={{ backgroundColor: "var(--theme-bg)", borderColor: "var(--theme-border)" }}
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="flex items-center justify-between px-6 py-4 border-b border-grey/10">
            <div className="flex items-center gap-3">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-400/10 border border-blue-400/20">
                <BookMarked className="h-4 w-4 text-blue-400" />
              </div>
              <div>
                <h2 className="text-sm font-semibold text-white">Skill Editor</h2>
                <p className="text-[10px] text-grey/50">
                  {agentName ? `Skill for: ${agentName}` : "Agent Skill (SKILL.md)"}
                </p>
              </div>
            </div>
            <button
              onClick={onClose}
              className="flex items-center justify-center rounded-lg p-2 text-grey/50 hover:text-white hover:bg-white/5 transition-all"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          {/* Toolbar */}
          <div className="flex items-center justify-between px-6 py-2.5 border-b border-grey/10 bg-white/[0.02]">
            <div className="flex items-center gap-2">
              <label className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[11px] font-medium text-grey/70 hover:text-white bg-white/5 hover:bg-white/10 border border-white/10 cursor-pointer transition-all">
                <Upload className="h-3 w-3" />
                Upload .md
                <input
                  type="file"
                  accept=".md,.txt"
                  onChange={handleFileUpload}
                  className="hidden"
                />
              </label>

              {!isEditing && skillContent && (
                <button
                  onClick={() => setIsEditing(true)}
                  className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[11px] font-medium text-grey/70 hover:text-white bg-white/5 hover:bg-white/10 border border-white/10 transition-all"
                >
                  <FileText className="h-3 w-3" />
                  Edit
                </button>
              )}

              {!skillContent && !isEditing && (
                <button
                  onClick={() => { setIsEditing(true); setSkillContent(SKILL_TEMPLATE); }}
                  className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[11px] font-medium text-grey/70 hover:text-white bg-white/5 hover:bg-white/10 border border-white/10 transition-all"
                >
                  <Plus className="h-3 w-3" />
                  Create New
                </button>
              )}
            </div>

            <div className="flex items-center gap-2">
              {skillContent && (
                <button
                  onClick={deleteSkill}
                  className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[11px] font-medium text-red-400/70 hover:text-red-300 bg-red-500/5 hover:bg-red-500/10 border border-red-500/10 transition-all"
                >
                  <Trash2 className="h-3 w-3" />
                  Delete
                </button>
              )}

              {isEditing && (
                <button
                  onClick={saveSkill}
                  disabled={isSaving}
                  className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[11px] font-medium text-white bg-blue-500/20 hover:bg-blue-500/30 border border-blue-500/30 transition-all disabled:opacity-50"
                >
                  <Save className="h-3 w-3" />
                  {isSaving ? "Saving..." : "Save Skill"}
                </button>
              )}

              {saveSuccess && (
                <span className="text-[10px] text-green-400 font-medium">✓ Saved</span>
              )}
            </div>
          </div>

          {/* Content */}
          <div className="flex-1 min-h-0 overflow-hidden">
            {isLoading ? (
              <div className="flex items-center justify-center h-full">
                <p className="text-xs text-grey/50 animate-pulse">Loading skill...</p>
              </div>
            ) : loadError ? (
              <div className="flex items-center justify-center h-full">
                <p className="text-xs text-red-400">{loadError}</p>
              </div>
            ) : isEditing ? (
              <textarea
                value={skillContent}
                onChange={(e) => setSkillContent(e.target.value)}
                className="w-full h-full resize-none bg-transparent text-xs text-white/90 font-mono leading-relaxed p-6 focus:outline-none"
                placeholder="# Skill Name&#10;&#10;## Instructions&#10;Write your skill instructions here..."
                spellCheck={false}
              />
            ) : skillContent ? (
              <div className="p-6 overflow-y-auto h-full">
                <pre className="text-xs text-grey/80 font-mono whitespace-pre-wrap leading-relaxed">
                  {skillContent}
                </pre>
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center h-full px-8 text-center">
                <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-white/5 border border-white/10 mb-3">
                  <Eye className="h-5 w-5 text-grey/40" />
                </div>
                <p className="text-xs text-grey/60 mb-1">No skill attached</p>
                <p className="text-[10px] text-grey/40 max-w-[200px]">
                  Upload a .md file or create a new skill to enhance this agent&apos;s capabilities.
                </p>
              </div>
            )}
          </div>

          {/* Footer info */}
          <div className="border-t border-grey/10 px-6 py-2.5">
            <p className="text-[10px] text-grey/40">
              Skills follow the SKILL.md format — instructions that guide the agent&apos;s behavior.
              {skillContent && ` (${skillContent.length} characters)`}
            </p>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}

const SKILL_TEMPLATE = `# Skill Name

## Description
Brief description of what this skill does.

## Instructions
1. Step one of the skill instructions
2. Step two
3. Step three

## Output Format
Describe the expected output format.

## Examples
Provide examples of good output.

## Constraints
- Constraint 1
- Constraint 2
`;
