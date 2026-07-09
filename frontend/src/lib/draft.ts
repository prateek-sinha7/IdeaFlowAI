/**
 * Configure run-draft — CLIENT-SIDE ONLY (ND-1 / LOCK-E).
 *
 * The Configure screen's Save-draft persists the in-progress run setup as ONE
 * keyed JSON blob in `sessionStorage`, read on mount and cleared once at launch.
 * This is deliberately a peer of `prototype.draft` (the wizard→dashboard hand-off
 * idiom, `components/workflow/LaunchWizard.tsx`) — NOT of the `chain.*`
 * run-chaining keys — and it has **no** server surface: no DB, no draft rows, no
 * migration, no fetch/`/api` call. A per-tab client store only (STRIDE
 * T-37-02-01: accepted — never leaves the browser).
 *
 * The payload is a superset of the generic launch inputs (template/DS ids,
 * custom bodies, brief, agent composition, per-step selections, model overrides,
 * gate selection, discovery answers) so a saved draft re-hydrates every accordion
 * and composes the generic LaunchCommand at launch.
 */

const STORAGE_KEY = "configure.draft";

/**
 * The persisted run-draft shape — a superset of the generic launch inputs the
 * Configure accordions compose. Every field is optional: a draft may be saved
 * mid-setup with only the fields the user has touched.
 */
export interface ConfigureDraft {
  /** Selected built-in template id (null/undefined ⇒ none / blank canvas). */
  templateId?: string | null;
  /** Selected built-in design-system id. */
  designSystemId?: string | null;
  /** The free-text brief. */
  brief?: string;
  /** The composed agent lineup (ids). */
  agentIds?: string[];
  /** Per-step Advanced-lever selections (validators/gates/model/retry). */
  selections?: Record<string, Record<string, unknown>>;
  /** Per-agent model overrides. */
  modelOverrides?: Record<string, string>;
  /** Body of a custom design system when one is selected. */
  customDsBody?: string | null;
  /** Body of a custom template when one is selected. */
  customTemplateBody?: string | null;
  /** The per-run human-review gate selection (agent ids). */
  gateAgentIds?: string[];
  /** Discovery answers (surface/audience/tone/scale/constraints + template inputs). */
  discovery?: unknown;
}

/** SSR/no-DOM guard — sessionStorage is undefined outside the browser. */
function store(): Storage | null {
  if (typeof window === "undefined") return null;
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

/** Persist the run-draft as the single keyed JSON blob (overwrites any prior). */
export function saveDraft(payload: ConfigureDraft): void {
  const s = store();
  if (!s) return;
  try {
    s.setItem(STORAGE_KEY, JSON.stringify(payload));
  } catch {
    /* quota / serialization failure — a draft is best-effort, never fatal */
  }
}

/**
 * Read the run-draft, or null when absent/corrupt. A malformed blob returns null
 * (never throws) so a corrupt tab-store can never crash the Configure screen.
 */
export function readDraft(): ConfigureDraft | null {
  const s = store();
  if (!s) return null;
  const raw = s.getItem(STORAGE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as ConfigureDraft;
  } catch {
    return null;
  }
}

/** Remove the run-draft (called once after the launch hand-off). */
export function clearDraft(): void {
  const s = store();
  if (!s) return;
  s.removeItem(STORAGE_KEY);
}
