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
 */
export function useHooksCatalog(): HooksCatalogResult {
  const reduxHooks = useAppSelector((state) => state.hooks.hooks);
  const events = useAppSelector((state) => state.hooks.hookEvents);

  const hooks: HookDef[] = reduxHooks.map((h) => ({
    id: h.id,
    name: h.display_name || h.name,
    description: h.description,
    event: h.event as HookDef["event"],
    trigger: h.trigger,
    compatible_agents: h.compatible_agents,
    tags: h.tags,
  }));

  return {
    hooks,
    events,
  };
}
