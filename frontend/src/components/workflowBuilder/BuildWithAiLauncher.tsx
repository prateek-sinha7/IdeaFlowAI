"use client";

/**
 * BuildWithAiLauncher: the AI Workflow Builder's entry on `/workflows`
 * (Req 1.1, 1.4, 2.1, 2.2; design 3.10.2 and 3.10.6).
 *
 * No workflow is open on the Saved Workflows page, so the entry opens a new
 * canvas: it asks the next `BuilderComposerHost` to open its panel with no
 * conversation (`markNewConversationPending`), then calls `onOpenComposer`,
 * which navigates to `/workflows/new`. The conversation starts when the user
 * sends the first message from the panel. Nothing is created on the click, so
 * an abandoned click leaves no empty session.
 *
 * Availability follows the host: `canRunPipeline(tier, "custom")` first, then
 * `GET /models` answering 200. Until both hold, `children` receives `undefined`
 * and the page draws no button. The probe is not made for a user without the
 * Custom_Entitlement.
 */

import { useCallback, type ReactNode } from "react";

import { useBuilderModelPicker } from "@/hooks/useBuilderModelPicker";
import { canRunPipeline, type Tier } from "@/lib/entitlements";

import { markNewConversationPending } from "./builderHandoff";

export interface BuildWithAiLauncherProps {
  /** The user's plan; `null` until the profile loads. */
  tier: Tier | null;
  /** Open the Composer on a new canvas (`/workflows/new`). */
  onOpenComposer: () => void;
  /** Receives the click handler for the entry button, or `undefined` while it is unavailable. */
  children: (onBuildWithAi: (() => void) | undefined) => ReactNode;
}

export function BuildWithAiLauncher({ tier, onOpenComposer, children }: BuildWithAiLauncherProps) {
  const entitled = tier !== null && canRunPipeline(tier, "custom");
  const picker = useBuilderModelPicker({ enabled: entitled, stored: null });
  const available = entitled && picker.state.status === "ready";

  const openBuilder = useCallback(() => {
    markNewConversationPending();
    onOpenComposer();
  }, [onOpenComposer]);

  return <>{children(available ? openBuilder : undefined)}</>;
}

export default BuildWithAiLauncher;
