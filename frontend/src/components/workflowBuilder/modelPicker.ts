/**
 * Pure logic of the Builder model picker (Req 6.3 to 6.6, 6.8, 6.9; design 3.10).
 *
 * The component renders a Model select and a Thinking select from these
 * functions. No model list lives here: everything comes from the
 * `BuilderModelsResponse` the server returns for the user (SC-001, INV-12).
 * The effort rules are the existing ones: `effortLevelsFor`, `effortLabel`
 * and `modelChangePatch` are reused, not copied.
 *
 * Pending G-27: the preselected effort is the model's `default_effort` from
 * `default_efforts`, and a model without levels sends `effort: null`.
 */

import {
  effortLabel,
  effortLevelsFor,
  modelChangePatch,
} from "@/components/workflow/AgentsPopup";
import type { CapabilityModelEntry } from "@/lib/api";
import type { BuilderModelsResponse } from "@/types/workflowBuilder";

/** The picker's value: what a message carries as `model_id` and `effort`. */
export interface PickerChoice {
  modelId: string;
  /** `null` when the model has no thinking levels (nothing to choose). */
  effort: string | null;
}

/** One entry of the Thinking select. */
export interface ThinkingOption {
  value: string;
  label: string;
}

/** The one-line notice shown under the picker, or `null` for none. */
export type PickerNote =
  | { kind: "stored_model_unavailable"; storedModelId: string }
  | { kind: "default_unavailable"; defaultModelId: string };

export interface Preselection {
  /** `null` only when the user is offered no model at all. */
  choice: PickerChoice | null;
  note: PickerNote | null;
}

/** The model's entry in the offered list, if it is offered. */
function findModel(
  modelId: string,
  models: CapabilityModelEntry[],
): CapabilityModelEntry | undefined {
  return models.find((m) => m.id === modelId);
}

/** Levels the Thinking select offers; none for `reasoning_mode: none`. */
function offeredLevels(modelId: string, models: CapabilityModelEntry[]): string[] {
  if (findModel(modelId, models)?.reasoning_mode === "none") return [];
  return effortLevelsFor(modelId, models);
}

/**
 * The Thinking select's options for a model: its `reasoning_levels`, labelled
 * with `effortLabel`. Empty (select hidden) for `reasoning_mode: none`, for a
 * model with no levels, and for a model that is not offered (Req 6.3, 6.4).
 */
export function thinkingOptions(
  modelId: string,
  models: CapabilityModelEntry[],
): ThinkingOption[] {
  const mode = findModel(modelId, models)?.reasoning_mode;
  return offeredLevels(modelId, models).map((value) => ({
    value,
    label: effortLabel(value, mode),
  }));
}

/**
 * The effort a model starts with: its `default_effort` when that is one of its
 * levels, otherwise its first level. `null` for a model with no levels.
 */
export function defaultEffortFor(
  modelId: string,
  response: Pick<BuilderModelsResponse, "models" | "default_efforts">,
): string | null {
  const levels = offeredLevels(modelId, response.models);
  if (levels.length === 0) return null;
  const preferred = response.default_efforts[modelId];
  return preferred != null && levels.includes(preferred) ? preferred : levels[0];
}

/**
 * The choice after the user picks another model (Req 6.6). The effort follows
 * `modelChangePatch`: kept when the new model accepts it, otherwise the new
 * model's default effort. A model without levels gets `null`.
 */
export function changeModel(
  nextModelId: string,
  currentEffort: string | null,
  response: Pick<BuilderModelsResponse, "models" | "default_efforts">,
): PickerChoice {
  const levels = offeredLevels(nextModelId, response.models);
  if (levels.length === 0) return { modelId: nextModelId, effort: null };
  const patch = modelChangePatch(
    nextModelId,
    currentEffort ?? undefined,
    response.models,
  );
  return {
    modelId: patch.model,
    effort: patch.effort !== "" ? patch.effort : defaultEffortFor(nextModelId, response),
  };
}

/** The user's chosen effort on `modelId`, or the model's default. */
function effortOrDefault(
  modelId: string,
  effort: string | null | undefined,
  response: Pick<BuilderModelsResponse, "models" | "default_efforts">,
): string | null {
  if (effort != null && offeredLevels(modelId, response.models).includes(effort)) {
    return effort;
  }
  return defaultEffortFor(modelId, response);
}

export interface PreselectionInput {
  response: Pick<
    BuilderModelsResponse,
    "models" | "default_model_id" | "default_efforts"
  >;
  /** The Session's stored model and effort (Req 6.9); `null` for none. */
  stored?: { modelId: string | null; effort: string | null } | null;
  /** The user's Settings model preference; `null` or absent for none. */
  preferredModelId?: string | null;
}

/**
 * The model and effort to preselect when the picker opens (Req 6.8, 6.9):
 * the stored model if offered, else the Settings preference if offered, else
 * the default model, else the first offered model. The stored effort is kept
 * only when the stored model accepts it. A stored model that is no longer
 * offered gives a `stored_model_unavailable` note; a default model that is not
 * offered gives `default_unavailable` (design 3.9.2).
 */
export function preselect({
  response,
  stored,
  preferredModelId,
}: PreselectionInput): Preselection {
  const { models, default_model_id: defaultModelId } = response;
  if (models.length === 0) return { choice: null, note: null };

  const storedId = stored?.modelId ?? null;
  if (storedId !== null && findModel(storedId, models)) {
    return {
      choice: {
        modelId: storedId,
        effort: effortOrDefault(storedId, stored?.effort, response),
      },
      note: null,
    };
  }

  const storedGone: PickerNote | null =
    storedId !== null ? { kind: "stored_model_unavailable", storedModelId: storedId } : null;

  if (preferredModelId != null && findModel(preferredModelId, models)) {
    return {
      choice: {
        modelId: preferredModelId,
        effort: defaultEffortFor(preferredModelId, response),
      },
      note: storedGone,
    };
  }

  if (findModel(defaultModelId, models)) {
    return {
      choice: {
        modelId: defaultModelId,
        effort: defaultEffortFor(defaultModelId, response),
      },
      note: storedGone,
    };
  }

  const first = models[0].id;
  return {
    choice: { modelId: first, effort: defaultEffortFor(first, response) },
    note: storedGone ?? { kind: "default_unavailable", defaultModelId },
  };
}
