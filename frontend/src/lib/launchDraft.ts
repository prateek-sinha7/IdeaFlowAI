/**
 * Launch-contract serialization — the SINGLE source of truth for the wizard →
 * dashboard hand-off blob (plan 37-07).
 *
 * Before 37-07 this serialization was INLINED, byte-for-byte identical, in the
 * two route-split template pages (`app/workflow/prototype/templates/page.tsx`
 * and `app/workflow/ppt/templates/page.tsx`). Plan 37-07 unifies both flows into
 * one WizardStepper-hosted page and extracts the serialization here so there is
 * exactly ONE implementation (INV-12: no dual impl). The pages are retired.
 *
 * SC-001 / INV-1: this module is keyed on a GENERIC `mode` value
 * ("prototype" | "ppt") — the deliverable family — NEVER a per-workflow branch.
 * The only mode-driven difference is the storage-key pair; every field is a
 * plain input the caller resolves (e.g. the caller applies the ppt
 * `dsRequired ? selectedDsId : null` rule before calling), so the serialized
 * SHAPE + KEY ORDER are identical across modes.
 *
 * The KEY ORDER of the serialized draft is load-bearing: the launch-contract
 * parity gate asserts the output is byte-identical to the retired flow's
 * `JSON.stringify`, so the object-literal insertion order below MUST match the
 * old `handleContinue` exactly:
 *   templateId, designSystemId, brief, [customDsBody], [customTemplateBody],
 *   [sourceRunId], [gateAgentIds], [modelOverrides], [selections], [images],
 *   agentIds
 */

import type { DiscoveryAnswers } from "@/components/workflow/prototype/DiscoveryForm";
import { EMPTY_ANSWERS } from "@/components/workflow/prototype/DiscoveryForm";

/** The deliverable family the launch targets. NOT a workflow-name branch. */
export type LaunchMode = "prototype" | "ppt";

/** An out-of-band image ride-along (D3): SEPARATE from brief-inlined file text. */
export interface LaunchImage {
  name: string;
  mime_type: string;
  data: string;
}

/**
 * The resolved launch inputs the wizard hands off. The caller resolves every
 * mode-specific value BEFORE calling (notably `designSystemId`, to which the
 * ppt `dsRequired ? selectedDsId : null` rule is already applied, and `brief`,
 * which is already composed with chain context + attached-file blocks).
 */
export interface LaunchDraftInputs {
  templateId: string | null;
  designSystemId: string | null;
  /** The composed final brief (chain context + attached file blocks applied). */
  brief: string;
  customDsBody?: string | null;
  customTemplateBody?: string | null;
  sourceRunId?: string | null;
  /** The per-run gate selection — serialized ONLY when `gatesTouched`. */
  gateAgentIds?: string[];
  gatesTouched?: boolean;
  modelOverrides?: Record<string, string>;
  selections?: Record<string, Record<string, unknown>>;
  images?: LaunchImage[];
  agentIds: string[];
}

export interface LaunchDraft {
  /** sessionStorage key for the draft blob the dashboard reads on connect. */
  draftKey: string;
  /** The `JSON.stringify`d draft — byte-identical to the retired flow. */
  draftJson: string;
  /** sessionStorage flag that tells the dashboard to auto-fire the pipeline. */
  pendingKey: string;
}

/** The per-mode storage-key pair — the ONLY mode-driven difference. */
const MODE_KEYS: Record<LaunchMode, { draftKey: string; pendingKey: string }> = {
  prototype: { draftKey: "prototype.draft", pendingKey: "prototype.pending" },
  ppt: { draftKey: "ppt.draft", pendingKey: "ppt.pending" },
};

/**
 * Build the wizard → dashboard hand-off draft for a deliverable family. The
 * object-literal below reproduces the retired flow's `handleContinue` exactly —
 * same key order, same truthy/length-guarded optional spreads — so the parity
 * gate proves the launch contract is unchanged.
 */
export function buildLaunchDraft(mode: LaunchMode, inputs: LaunchDraftInputs): LaunchDraft {
  const {
    templateId,
    designSystemId,
    brief,
    customDsBody,
    customTemplateBody,
    sourceRunId,
    gateAgentIds,
    gatesTouched,
    modelOverrides,
    selections,
    images,
    agentIds,
  } = inputs;

  const draftJson = JSON.stringify({
    templateId,
    designSystemId,
    brief,
    ...(customDsBody ? { customDsBody } : {}),
    ...(customTemplateBody ? { customTemplateBody } : {}),
    ...(sourceRunId ? { sourceRunId } : {}),
    ...(gatesTouched ? { gateAgentIds } : {}),
    ...(modelOverrides && Object.keys(modelOverrides).length > 0 ? { modelOverrides } : {}),
    ...(selections && Object.keys(selections).length > 0 ? { selections } : {}),
    ...(images && images.length > 0 ? { images } : {}),
    agentIds,
  });

  return { ...MODE_KEYS[mode], draftJson };
}

/** sessionStorage key for the prototype discovery answers the dashboard reads. */
export const DISCOVERY_KEY = "prototype.discovery";

/** True when no discovery field has been filled (every answer still empty). */
export function isDiscoveryEmpty(answers: DiscoveryAnswers): boolean {
  return (
    !answers.surface &&
    !answers.audience &&
    !answers.tone &&
    !answers.scale &&
    !answers.constraints &&
    Object.keys(answers.template ?? {}).length === 0
  );
}

/**
 * The prototype discovery hand-off. Returns the `JSON.stringify`d answers when
 * the user engaged the Discovery step (byte-identical to the retired discovery
 * route's `goToRun(answers)` write), or null when nothing was filled — in which
 * case the caller REMOVES the key so no stale answers leak into the run (the
 * retired discovery route's Skip path). ppt has no discovery.
 */
export function buildDiscoveryValue(answers: DiscoveryAnswers): string | null {
  if (isDiscoveryEmpty(answers)) return null;
  return JSON.stringify(answers);
}

export { EMPTY_ANSWERS };
