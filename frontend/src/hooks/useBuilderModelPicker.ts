"use client";

/**
 * useBuilderModelPicker: state of the Builder model picker (Req 6.1 to 6.9).
 *
 * Loads the user's model list from `GET /models` (the only source, Req 6.2),
 * and derives the chosen model and effort during render: the user's pick if
 * they made one, otherwise the `preselect` result. Nothing is synced with
 * effects, so a stored or preferred model that arrives later is picked up.
 * `retry` reloads the list after a failure.
 */

import { useCallback, useEffect, useState } from "react";

import {
  changeModel,
  preselect,
  type PickerChoice,
  type PickerNote,
} from "@/components/workflowBuilder/modelPicker";
import { getToken } from "@/lib/api";
import { getBuilderModels } from "@/lib/workflowBuilderApi";
import type { BuilderModelsResponse } from "@/types/workflowBuilder";

/** What the picker knows about the model list. */
export type BuilderModelsState =
  | { status: "loading" }
  | { status: "error" }
  | { status: "ready"; response: BuilderModelsResponse };

export interface UseBuilderModelPickerOptions {
  /** The Session's stored model and effort (Req 6.9); `null` for none. */
  stored?: { modelId: string | null; effort: string | null } | null;
  /** The user's Settings model preference (Req 6.8); `null` for none. */
  preferredModelId?: string | null;
  /**
   * When false the hook makes no request and stays in `loading`. The host passes
   * false for a user without the Custom_Entitlement, so `GET /models` is only
   * called for users who may see the builder (design 3.10.2). Default true.
   */
  enabled?: boolean;
}

export interface UseBuilderModelPickerResult {
  state: BuilderModelsState;
  /** `null` until the list is ready, and when it offers no model. */
  choice: PickerChoice | null;
  note: PickerNote | null;
  onModelChange: (modelId: string) => void;
  onEffortChange: (effort: string) => void;
  onRetry: () => void;
}

interface Loaded {
  attempt: number;
  result: { status: "error" } | { status: "ready"; response: BuilderModelsResponse };
}

export function useBuilderModelPicker({
  stored = null,
  preferredModelId = null,
  enabled = true,
}: UseBuilderModelPickerOptions = {}): UseBuilderModelPickerResult {
  const [attempt, setAttempt] = useState(0);
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [picked, setPicked] = useState<PickerChoice | null>(null);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    const token = getToken();
    const request = token
      ? getBuilderModels(token)
      : Promise.reject(new Error("Not authenticated"));
    request.then(
      (response) => {
        if (!cancelled) setLoaded({ attempt, result: { status: "ready", response } });
      },
      () => {
        if (!cancelled) setLoaded({ attempt, result: { status: "error" } });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [attempt, enabled]);

  // Loading is derived: a result from an older attempt does not count.
  const state: BuilderModelsState =
    enabled && loaded !== null && loaded.attempt === attempt
      ? loaded.result
      : { status: "loading" };
  const response = state.status === "ready" ? state.response : null;

  const preselected = response
    ? preselect({ response, stored, preferredModelId })
    : { choice: null, note: null };
  // A pick made on an earlier list only counts while that model is still offered.
  const pickStillOffered =
    picked !== null && (response?.models.some((m) => m.id === picked.modelId) ?? false);
  const choice = pickStillOffered ? picked : preselected.choice;
  const note = pickStillOffered ? null : preselected.note;

  const onModelChange = useCallback(
    (modelId: string) => {
      if (!response) return;
      setPicked(changeModel(modelId, choice?.effort ?? null, response));
    },
    [response, choice?.effort],
  );

  const onEffortChange = useCallback(
    (effort: string) => {
      if (!choice) return;
      setPicked({ modelId: choice.modelId, effort });
    },
    [choice],
  );

  const onRetry = useCallback(() => setAttempt((n) => n + 1), []);

  return { state, choice, note, onModelChange, onEffortChange, onRetry };
}
