"use client";

import { AlertCircle, Loader2 } from "lucide-react";

import type { StagedDocument } from "@/hooks/useStagedDocuments";

interface UploadChipStatusProps {
  /** File name, used in the Retry button's accessible name. */
  name: string;
  /** This file's staging entry; absent when the file is not staged. */
  document?: StagedDocument;
  /** The in-browser text preview failed (informational — the stage is what the run reads). */
  previewFailed?: boolean;
  onRetry?: () => void;
}

/**
 * The upload status shown inside a document chip. Status is carried by text
 * and an icon, never by color alone; the icons are decorative (`aria-hidden`).
 * Renders nothing once a document is staged and its preview worked.
 */
export function UploadChipStatus({ name, document, previewFailed, onRetry }: UploadChipStatusProps) {
  if (document?.status === "staging") {
    return (
      <span className="inline-flex items-center gap-1 text-ink-400">
        <Loader2 aria-hidden="true" className="h-2.5 w-2.5 animate-spin motion-reduce:animate-none" />
        Uploading…
      </span>
    );
  }
  if (document?.status === "failed") {
    return (
      <span className="inline-flex items-center gap-1 text-status-failed">
        <AlertCircle aria-hidden="true" className="h-2.5 w-2.5" />
        <span>{document.reason}</span>
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            aria-label={`Retry upload of ${name}`}
            className="ml-1 rounded-sm font-semibold underline underline-offset-2 hover:text-status-failed-strong focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1"
          >
            Retry
          </button>
        )}
      </span>
    );
  }
  if (previewFailed) {
    return <span className="text-ink-400">Text preview unavailable</span>;
  }
  return null;
}
