"use client";

/**
 * RequirementsStep — the PDF upload + optional context step for the
 * `prototype_from_template` wizard.
 *
 * Design.md §2: the wizard step that collects the primary requirements
 * document (PDF, mandatory) and an optional text textarea for additional
 * context. The component is presentational — state management (staged
 * documents, file input ref) lives in the parent LaunchWizard so the launch
 * payload can read the same staged documents array.
 *
 * Validity rule: isValid === at least one successfully staged document exists.
 * The parent wires this to the Launch button gate (hasStagedPDF).
 */

import { useEffect, useRef } from "react";
import { Paperclip, X, File } from "lucide-react";
import type { StagedDocument } from "@/hooks/useStagedDocuments";
import { UploadChipStatus } from "@/components/workflow/UploadChipStatus";
import { UPLOAD_TOO_LARGE_MESSAGE } from "@/lib/uploadErrors";

export interface RequirementsStepProps {
  /**
   * True when at least one PDF has been successfully staged (status "staged").
   * The parent computes this from `stagedUploadsOf(stagedDocuments).length > 0`.
   * This component calls `onValidityChange` whenever the value changes.
   */
  isValid: boolean;
  /** Fired every time `isValid` changes — wires to the wizard's Launch gate. */
  onValidityChange: (valid: boolean) => void;

  /** All tracked staged documents from the parent's `useStagedDocuments()` hook. */
  stagedDocuments: StagedDocument[];
  /**
   * Parallel array of attached-file metadata (name, size, stageKey) maintained
   * by the parent alongside `stagedDocuments`.
   */
  attachedFiles: { name: string; size: string; stageKey?: number }[];
  /** Stage keys that had an in-browser preview failure (informational only). */
  previewFailedKeys: number[];

  /** Triggers the hidden `<input type="file" accept=".pdf">` in the parent. */
  onPickFiles: () => void;
  /** Removes the file at `idx` from `attachedFiles` and removes its stage. */
  onRemoveFile: (idx: number) => void;
  /** Retries staging the file identified by `key`. */
  onRetryFile: (key: number, name: string) => void;

  /** Optional additional context text (brief textarea). */
  additionalContext: string;
  onAdditionalContextChange: (text: string) => void;
}

export function RequirementsStep({
  isValid,
  onValidityChange,
  stagedDocuments,
  attachedFiles,
  previewFailedKeys,
  onPickFiles,
  onRemoveFile,
  onRetryFile,
  additionalContext,
  onAdditionalContextChange,
}: RequirementsStepProps) {
  // Propagate validity changes to parent.
  const prevValid = useRef<boolean | null>(null);
  useEffect(() => {
    if (prevValid.current !== isValid) {
      prevValid.current = isValid;
      onValidityChange(isValid);
    }
  }, [isValid, onValidityChange]);

  return (
    <div className="flex flex-col gap-4">
      {/* ── Upload zone ──────────────────────────────────────────────── */}
      <div className="rounded-[var(--radius-card)] border border-line-border bg-surface-white">
        <div className="px-5 py-4">
          <p className="mb-1 text-[13px] font-semibold text-ink-900">
            Requirements document
            <span className="ml-2 rounded-[var(--radius-tag)] bg-[var(--status-failed-fill)] px-1.5 py-0.5 text-[10px] font-semibold text-status-failed">
              Required
            </span>
          </p>
          <p className="mb-3 text-[12px] text-ink-400">
            Attach a PDF containing your screens, fields, flows, and business
            rules. The workflow reads it to adapt the template.
          </p>

          {/* Staged file chips */}
          {attachedFiles.length > 0 && (
            <div
              className="mb-3 flex flex-wrap gap-1.5"
              aria-live="polite"
              data-testid="requirements-chips"
            >
              {attachedFiles.map((file, idx) => {
                const key = file.stageKey;
                const doc =
                  key === undefined
                    ? undefined
                    : stagedDocuments.find((d) => d.key === key);
                const canRetry =
                  key !== undefined &&
                  doc?.status === "failed" &&
                  doc.reason !== UPLOAD_TOO_LARGE_MESSAGE;
                return (
                  <span
                    key={`${file.name}-${idx}`}
                    className="inline-flex items-center gap-1 rounded-[var(--radius-button)] bg-surface-warm px-2.5 py-1 text-[10px] text-ink-600"
                  >
                    <File className="h-2.5 w-2.5 flex-shrink-0" />
                    {file.name}
                    <UploadChipStatus
                      name={file.name}
                      document={doc}
                      previewFailed={
                        key !== undefined && previewFailedKeys.includes(key)
                      }
                      onRetry={
                        canRetry ? () => onRetryFile(key!, file.name) : undefined
                      }
                    />
                    <button
                      type="button"
                      onClick={() => onRemoveFile(idx)}
                      aria-label={`Remove ${file.name}`}
                      className="ml-1 text-ink-400 hover:text-status-failed"
                    >
                      <X className="h-2.5 w-2.5" />
                    </button>
                  </span>
                );
              })}
            </div>
          )}

          {/* Attach button — always visible so the user can add more files */}
          <button
            type="button"
            onClick={onPickFiles}
            data-testid="attach-pdf-button"
            className="inline-flex items-center gap-1.5 rounded-[var(--radius-button)] border border-brand bg-brand-fill px-3 py-1.5 text-[11px] font-medium text-brand transition-all hover:bg-brand hover:text-white"
          >
            <Paperclip className="h-3.5 w-3.5" />
            {attachedFiles.length === 0 ? "Attach requirements PDF" : "Attach another PDF"}
          </button>

          {/* Warning when user has interacted but no valid PDF staged */}
          {attachedFiles.length > 0 && !isValid && (
            <p
              role="alert"
              className="mt-2 text-[11px] text-status-failed"
              data-testid="requirements-warning"
            >
              Attach at least one PDF requirements document to continue.
            </p>
          )}
        </div>
      </div>

      {/* ── Optional additional context ──────────────────────────────── */}
      <div className="rounded-[var(--radius-card)] border border-line-border bg-surface-white">
        <textarea
          value={additionalContext}
          onChange={(e) => onAdditionalContextChange(e.target.value)}
          aria-label="Additional context (optional)"
          placeholder="Additional context (optional) — add clarifications, brand name, or specific data values here."
          rows={4}
          data-testid="additional-context"
          className="w-full resize-none rounded-[var(--radius-card)] bg-transparent px-5 py-4 text-[14px] leading-relaxed text-ink-900 placeholder:text-ink-400 focus:outline-none"
        />
      </div>
    </div>
  );
}
