/**
 * Pure helpers of `BuilderComposerHost` (design 3.10.2, 3.10.5, 3.10.6).
 *
 * No React, no I/O, no clock. The host keeps the effects (REST calls, the URL,
 * the prompts) and asks these functions what to do, so each rule has one
 * definition and a plain unit test.
 */

import { canonicalJson } from "@/lib/canonicalManifest";
import type { SessionLoad } from "./builderReducer";
import type { TranscriptMessage } from "@/types/workflowBuilder";

const EDIT_ROUTE = /^\/workflows\/([^/]+)\/edit\/?$/;
const NEW_ROUTE = /^\/workflows\/new\/?$/;

/** The saved workflow id of a `/workflows/{id}/edit` path, or `null` for any other path. */
export function parseEditWorkflowId(pathname: string | null): string | null {
  if (pathname === null) return null;
  const match = EDIT_ROUTE.exec(pathname);
  if (match === null || match[1] === "new") return null;
  try {
    return decodeURIComponent(match[1]);
  } catch {
    return match[1];
  }
}

/** True on `/workflows/new` and `/workflows/{id}/edit`, the only routes with the AI button (Req 1.2). */
export function isBuilderRoute(pathname: string | null): boolean {
  if (pathname === null) return false;
  return NEW_ROUTE.test(pathname) || parseEditWorkflowId(pathname) !== null;
}

/** The session id a `SessionLoad` refers to, or `null` for none. */
export function sessionIdOf(load: SessionLoad): string | null {
  switch (load.kind) {
    case "none":
      return null;
    case "ready":
      return load.session.id;
    default:
      return load.sessionId;
  }
}

/** The Composer route of a session: its linked row's edit route, or `/workflows/new`. */
export function sessionRoutePath(workflowId: string | null): string {
  return workflowId === null ? "/workflows/new" : `/workflows/${encodeURIComponent(workflowId)}/edit`;
}

/**
 * `search` with the `ai` parameter set to `sessionId`, or removed when it is
 * `null`. Other parameters are kept. Returns "" or a string starting with "?".
 */
export function searchWithAi(search: string, sessionId: string | null): string {
  const params = new URLSearchParams(search);
  if (sessionId === null) params.delete("ai");
  else params.set("ai", sessionId);
  const text = params.toString();
  return text === "" ? "" : `?${text}`;
}

/** What to do with a draft that reached the reducer. */
export type DraftDecision = "skip" | "apply" | "prompt";

/**
 * Decide how a new draft reaches the canvas.
 *
 *   - `skip`: the revision is one the canvas must not take, namely the latest
 *     draft of a linked session that was just opened, where the saved row is
 *     shown instead (Req 12.4);
 *   - `apply`: take it now. That is the case when this tab asked for it (its
 *     `canvas_state` already carried the manual edits, Req 9.2) or when the
 *     canvas has no unsaved work;
 *   - `prompt`: another tab's draft over unsaved work, so ask first (Req 17.11).
 */
export function decideDraft(input: {
  revision: number;
  skipUpToRevision: number;
  silent: boolean;
  dirty: boolean;
}): DraftDecision {
  if (input.revision <= input.skipUpToRevision) return "skip";
  if (input.silent || !input.dirty) return "apply";
  return "prompt";
}

/**
 * The turn Retry re-runs: the newest assistant message, when its turn failed
 * (Req 13.1). `null` when the newest assistant message did not fail, so a
 * stale error row never offers Retry.
 */
export function retryTurnId(messages: readonly TranscriptMessage[]): string | null {
  let newest: TranscriptMessage | null = null;
  for (const message of messages) {
    if (message.role === "assistant" && (newest === null || message.seq > newest.seq)) {
      newest = message;
    }
  }
  return newest !== null && newest.status === "failed" ? newest.turn_id : null;
}

/** Canonical JSON of a manifest; equal strings mean equal workflows (design 3.10.8). */
export function manifestFingerprint(manifest: unknown): string {
  try {
    return canonicalJson(manifest as Record<string, unknown>);
  } catch {
    return JSON.stringify(manifest);
  }
}

/**
 * Whether the saved row a session is linked to has a base other than `custom`
 * (Req 10.10). `undefined` when the base is not known yet, which the Composer
 * reads as "custom".
 */
export function linkedBaseIsCustom(base: string | null | undefined): boolean | undefined {
  if (base === null || base === undefined) return undefined;
  return base === "custom";
}
