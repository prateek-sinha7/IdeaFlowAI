import { useMemo } from "react";
import { useAppSelector } from "@/store/hooks";
import type { HookDef } from "@/store/api/hooks";

export interface HooksCatalogFilterOption {
  id: string;
  label: string;
  icon?: string;
}

export interface HooksCatalogResult {
  hooks: HookDef[];
  events: readonly HooksCatalogFilterOption[];
}

/**
 * Returns the global Hooks catalog from Redux state. Populated by
 * GET /api/hooks/library when fetchHooks completes.
 *
 * ISS-336 — the hooks array was rebuilt inline on every render (new reference
 * each time), so HOOKS.find() inside LibraryPage's cold-mount/deep-link effect
 * always saw a referentially-new array and never matched. useMemo pins the
 * reference to the Redux slice's own reference, exactly as useSkillsCatalog does.
 */
export function useHooksCatalog(): HooksCatalogResult {
  const reduxHooks = useAppSelector((state) => state.hooks.hooks);
  const events = useAppSelector((state) => state.hooks.hookEvents);

  const hooks: HookDef[] = useMemo(
    () =>
      reduxHooks.map((h) => ({
        id: h.id,
        name: h.display_name || h.name,
        description: h.description,
        event: h.event as HookDef["event"],
        trigger: h.trigger,
        compatible_agents: h.compatible_agents,
        tags: h.tags,
      })),
    [reduxHooks],
  );

  return {
    hooks,
    events,
  };
}
