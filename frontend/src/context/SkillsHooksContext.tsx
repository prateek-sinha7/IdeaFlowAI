"use client";

import { createContext, useContext, useState, useCallback, type ReactNode } from "react";
import type { AttachedSkill, AttachedHook } from "@/types/index";

interface SkillsHooksContextValue {
  attachedSkills: AttachedSkill[];
  attachedHooks: AttachedHook[];
  attachSkill: (skill: AttachedSkill) => void;
  detachSkill: (id: string) => void;
  attachHook: (hook: AttachedHook) => void;
  detachHook: (id: string) => void;
  clearAll: () => void;
}

const SkillsHooksContext = createContext<SkillsHooksContextValue | null>(null);

export function SkillsHooksProvider({ children }: { children: ReactNode }) {
  const [attachedSkills, setAttachedSkills] = useState<AttachedSkill[]>([]);
  const [attachedHooks, setAttachedHooks] = useState<AttachedHook[]>([]);

  const attachSkill = useCallback((skill: AttachedSkill) => {
    setAttachedSkills(prev => prev.find(s => s.id === skill.id) ? prev : [...prev, skill]);
  }, []);

  const detachSkill = useCallback((id: string) => {
    setAttachedSkills(prev => prev.filter(s => s.id !== id));
  }, []);

  const attachHook = useCallback((hook: AttachedHook) => {
    setAttachedHooks(prev => prev.find(h => h.id === hook.id) ? prev : [...prev, hook]);
  }, []);

  const detachHook = useCallback((id: string) => {
    setAttachedHooks(prev => prev.filter(h => h.id !== id));
  }, []);

  const clearAll = useCallback(() => {
    setAttachedSkills([]);
    setAttachedHooks([]);
  }, []);

  return (
    <SkillsHooksContext.Provider value={{
      attachedSkills, attachedHooks,
      attachSkill, detachSkill,
      attachHook, detachHook,
      clearAll,
    }}>
      {children}
    </SkillsHooksContext.Provider>
  );
}

export function useSkillsHooks(): SkillsHooksContextValue {
  const ctx = useContext(SkillsHooksContext);
  if (!ctx) throw new Error("useSkillsHooks must be used within SkillsHooksProvider");
  return ctx;
}
