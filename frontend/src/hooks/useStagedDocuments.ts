"use client";

/**
 * Per-document staging state for the launch surfaces (LaunchWizard, and
 * IdeaInputPage/ComposerPage through `useBriefAttachments`).
 *
 * Each attached document is staged with `POST /api/runs/uploads/stage`; the
 * returned stage id rides the launch as `staged_upload_ids`, which is the ONLY
 * thing that fills the run's `.uploads/`. A failed stage used to be swallowed
 * (`.catch(() => false)`), so a run could launch with no files and the user was
 * never told. This hook records every outcome as a discriminated union, so the
 * chip can say what happened and the launch can be gated on it.
 */

import { useCallback, useMemo, useRef, useState } from "react";

import { stageRunFile } from "@/lib/api";
import {
  UPLOAD_TOO_LARGE_MESSAGE,
  describeUploadError,
  isOverUploadLimit,
} from "@/lib/uploadErrors";

export type StagedDocument =
  | { key: number; name: string; status: "staging" }
  | { key: number; name: string; status: "staged"; stageId: string }
  | { key: number; name: string; status: "failed"; reason: string };

export type UploadGate =
  | { kind: "ready" }
  | { kind: "staging"; count: number }
  | { kind: "failed"; names: string[] };

/** The `{name, stageId, attachIndex}` shape `orderedStagedUploadIds` takes. */
export interface StagedUpload {
  name: string;
  stageId: string;
  attachIndex: number;
}

/** Whether a launch may proceed: blocked while staging and after any failure. */
export function uploadGateFor(documents: readonly StagedDocument[]): UploadGate {
  const failed = documents.filter((d) => d.status === "failed").map((d) => d.name);
  if (failed.length > 0) return { kind: "failed", names: failed };
  const staging = documents.filter((d) => d.status === "staging").length;
  if (staging > 0) return { kind: "staging", count: staging };
  return { kind: "ready" };
}

/** The visible, accessible reason a launch is blocked — `null` when ready. */
export function uploadGateMessage(gate: UploadGate): string | null {
  switch (gate.kind) {
    case "staging":
      return `Uploading ${gate.count} document${gate.count === 1 ? "" : "s"}…`;
    case "failed":
      return `Upload failed for ${gate.names.join(", ")}. Remove or retry it to continue.`;
    default:
      return null;
  }
}

export interface StagedDocuments {
  /** Every tracked document (see `commit` for ordering). */
  documents: StagedDocument[];
  /** Successfully staged documents, in the shape the launch payload takes. */
  stagedUploads: StagedUpload[];
  gate: UploadGate;
  /** Start staging `file`; returns its key. The key is the attach index. */
  stage: (file: File, jwt: string) => number;
  /** Re-stage a failed document under the same key (attach order is kept). */
  retry: (key: number, jwt: string) => Promise<boolean>;
  remove: (key: number) => void;
  /** Resolve once `key`'s stage (or every in-flight stage) has settled. */
  settle: (key?: number) => Promise<StagedDocument[]>;
  /** True while any stage request is in flight. */
  hasPending: () => boolean;
  /** The latest documents, including updates not yet rendered. */
  snapshot: () => StagedDocument[];
}

export function useStagedDocuments(): StagedDocuments {
  const [documents, setDocuments] = useState<StagedDocument[]>([]);
  // Mirror of `documents` so async continuations and `settle()` read the latest
  // value without waiting for a render.
  const docsRef = useRef<StagedDocument[]>([]);
  // Monotonic attach-order counter (FIX-562): captured synchronously at attach
  // time, before the async stage call, because responses arrive in any order.
  const nextKeyRef = useRef(0);
  const filesRef = useRef(new Map<number, File>());
  const pendingRef = useRef(new Map<number, Promise<void>>());
  // Identifies the latest attempt per key, so a late response for a removed or
  // superseded attempt cannot overwrite newer state.
  const attemptRef = useRef(new Map<number, object>());

  const commit = useCallback((next: StagedDocument[]) => {
    docsRef.current = next;
    setDocuments(next);
  }, []);

  // A document moves to the END of the list whenever its status changes, so
  // `stagedUploads` lists stages in response-arrival order, exactly as the
  // pre-hook state did. Attach order travels separately as `attachIndex`.
  const replace = useCallback(
    (doc: StagedDocument) => {
      commit([...docsRef.current.filter((d) => d.key !== doc.key), doc]);
    },
    [commit],
  );

  const run = useCallback(
    (key: number, file: File, jwt: string): Promise<void> => {
      const attempt = {};
      attemptRef.current.set(key, attempt);
      const isCurrent = () => attemptRef.current.get(key) === attempt;
      const pending = stageRunFile(jwt, file)
        .then(
          (res) => {
            if (isCurrent()) replace({ key, name: file.name, status: "staged", stageId: res.stage_id });
          },
          (err: unknown) => {
            if (isCurrent()) replace({ key, name: file.name, status: "failed", reason: describeUploadError(err) });
          },
        )
        .finally(() => {
          if (pendingRef.current.get(key) === pending) pendingRef.current.delete(key);
        });
      pendingRef.current.set(key, pending);
      return pending;
    },
    [replace],
  );

  const stage = useCallback(
    (file: File, jwt: string): number => {
      const key = nextKeyRef.current++;
      filesRef.current.set(key, file);
      if (isOverUploadLimit(file.size)) {
        replace({ key, name: file.name, status: "failed", reason: UPLOAD_TOO_LARGE_MESSAGE });
        return key;
      }
      replace({ key, name: file.name, status: "staging" });
      void run(key, file, jwt);
      return key;
    },
    [replace, run],
  );

  const retry = useCallback(
    async (key: number, jwt: string): Promise<boolean> => {
      const file = filesRef.current.get(key);
      const current = docsRef.current.find((d) => d.key === key);
      if (!file || current?.status !== "failed" || isOverUploadLimit(file.size)) return false;
      replace({ key, name: file.name, status: "staging" });
      await run(key, file, jwt);
      return docsRef.current.find((d) => d.key === key)?.status === "staged";
    },
    [replace, run],
  );

  const remove = useCallback(
    (key: number) => {
      filesRef.current.delete(key);
      pendingRef.current.delete(key);
      attemptRef.current.delete(key);
      commit(docsRef.current.filter((d) => d.key !== key));
    },
    [commit],
  );

  const settle = useCallback(async (key?: number): Promise<StagedDocument[]> => {
    if (key !== undefined) {
      await pendingRef.current.get(key);
      return docsRef.current;
    }
    // Loop: a stage started while waiting must be waited for too.
    while (pendingRef.current.size > 0) {
      await Promise.allSettled([...pendingRef.current.values()]);
    }
    return docsRef.current;
  }, []);

  const hasPending = useCallback(() => pendingRef.current.size > 0, []);
  const snapshot = useCallback(() => docsRef.current, []);

  // Memoized for stable references: consumers list these in launch-callback deps.
  const stagedUploads = useMemo(() => stagedUploadsOf(documents), [documents]);
  const gate = useMemo(() => uploadGateFor(documents), [documents]);

  return { documents, stagedUploads, gate, stage, retry, remove, settle, hasPending, snapshot };
}

/** Staged documents in the `orderedStagedUploadIds` input shape. */
export function stagedUploadsOf(documents: readonly StagedDocument[]): StagedUpload[] {
  return documents.flatMap((d) =>
    d.status === "staged" ? [{ name: d.name, stageId: d.stageId, attachIndex: d.key }] : [],
  );
}
