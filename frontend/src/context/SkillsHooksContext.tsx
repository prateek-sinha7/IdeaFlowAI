"use client";

import { createContext, useContext, useState, useCallback, type ReactNode } from "react";
import type { AttachedHook } from "@/types/index";

/**
 * ── SKILLS RETIRED FROM THIS CONTEXT (ADR-0010) ───────────────────────────────
 *
 * This context used to hold `attachedSkills` alongside `attachedHooks`: a single
 * RUN-LEVEL skill bag that every agent in a launch received identically. Spec 012
 * replaced that with PER-AGENT skills (`Step.skills`, authored via
 * `composer/AgentSkillsPicker`), so a run-level bag is now a second, coarser
 * source of truth for the same thing — and the two silently disagreed whenever
 * both were populated.
 *
 * The skills half is therefore gone: no `attachedSkills`, no `attachSkill`, no
 * `detachSkill`, and `startPipeline` no longer sends `attached_skills`. Skills
 * are attached to an AGENT, in one place, by one component.
 *
 * HOOKS ARE DELIBERATELY UNCHANGED and remain run-level. There is no per-step
 * hooks field (nothing analogous to `Step.skills` exists in the manifest), so
 * moving hooks would require a new compiler surface first. The provider keeps
 * its `SkillsHooks` name only to avoid churning ~15 test files that wrap
 * components in it; read it as "the run-level attachment context".
 *
 * The BACKEND still accepts `attached_skills` on both the launch and save paths.
 * That is intentional, not an oversight: saved workflows written before this
 * change still carry the column, and `user_workflows._migrate_attached_skills_to_steps`
 * fans those legacy values out into per-step `skills` on first read. Nothing in
 * the UI writes the field any more.
 */
interface SkillsHooksContextValue {
  attachedHooks: AttachedHook[];
  attachHook: (hook: AttachedHook) => void;
  detachHook: (id: string) => void;
  clearAll: () => void;
}

const SkillsHooksContext = createContext<SkillsHooksContextValue | null>(null);

export function SkillsHooksProvider({ children }: { children: ReactNode }) {
  const [attachedHooks, setAttachedHooks] = useState<AttachedHook[]>([]);

  const attachHook = useCallback((hook: AttachedHook) => {
    setAttachedHooks(prev => prev.find(h => h.id === hook.id) ? prev : [...prev, hook]);
  }, []);

  const detachHook = useCallback((id: string) => {
    setAttachedHooks(prev => prev.filter(h => h.id !== id));
  }, []);

  const clearAll = useCallback(() => {
    setAttachedHooks([]);
  }, []);

  return (
    <SkillsHooksContext.Provider value={{
      attachedHooks,
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
