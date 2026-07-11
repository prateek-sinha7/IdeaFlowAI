"use client";

/**
 * ChatAttachments — the chat lane's composer attachment sub-surface (Phase 31,
 * CHATUI-03). Wraps `useChatAttachments`: a drop zone (with a visible
 * drag-active state), a clipboard paste handler, a hidden multi-file picker, and
 * removable preview chips (image thumbnail from the resized base64; file → name
 * + size chip).
 *
 * Two render modes:
 *  - LIVE intake (default): the composer's attachment tray. New files route
 *    through `useChatAttachments` (picker/paste/drag-drop → resize/passthrough).
 *  - REOPENED: pass a stored turn's `reopenedAttachments`. Because attachments
 *    are payload-transient (ND-10 / LOCK-E), a `retained:false` ref has NO bytes
 *    on reopen, so it renders the honest "image not kept on reopen" placeholder
 *    chip — the placeholder IS the disposition, not durable storage.
 *
 * Current skin (D-15), raw Tailwind + lucide icons.
 */
import { useEffect, useRef, useState } from "react";
import type { MutableRefObject } from "react";
import { FileText, ImageIcon, ImageOff, Paperclip, X } from "lucide-react";

import { useChatAttachments, type PendingAttachment } from "@/hooks/useChatAttachments";
import type { ChatAttachment } from "@/types/index";

const DEFAULT_ACCEPT =
  "image/png,image/jpeg,image/webp,image/gif,.pdf,.txt,.md,.docx";

interface ChatAttachmentsProps {
  /** Notify the lane of the current live intake so it can attach them to the
   *  next sent turn. Fires whenever the intake changes. */
  onChange?: (attachments: PendingAttachment[]) => void;
  /** Render a REOPENED/replayed turn's stored refs as placeholder chips. When
   *  set, the live intake is suppressed (this turn is history, not the composer). */
  reopenedAttachments?: ChatAttachment[];
  /** Accept list override for the hidden file input. */
  accept?: string;
  /**
   * Phase 39 (RUNUI-06): CHIPS-ONLY mode. Suppresses the dashed drop-zone/attach
   * button so the mock's composer bar can own the paperclip trigger (via
   * `openRef`) while this component still renders the removable preview chips +
   * keeps drag/paste wiring. Default OFF (the standalone chat keeps its tray).
   */
  compact?: boolean;
  /**
   * Populated with a function that opens the hidden file picker, so an external
   * trigger (the composer bar's paperclip in `compact` mode) can invoke it. */
  openRef?: MutableRefObject<(() => void) | null>;
}

function formatSize(bytes?: number): string {
  if (!bytes) return "";
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1_048_576) return `${(bytes / 1024).toFixed(1)}KB`;
  return `${(bytes / 1_048_576).toFixed(1)}MB`;
}

/** A read-only placeholder chip for a payload-transient ref on reopen (ND-10). */
function PlaceholderChip({ att }: { att: ChatAttachment }) {
  return (
    <span
      data-testid="chat-attach-chip"
      data-retained="false"
      className="inline-flex items-center gap-1 rounded-lg bg-gray-50 border border-dashed border-gray-300 px-2.5 py-1 text-[10px] text-gray-400 italic"
    >
      <ImageOff className="h-2.5 w-2.5 flex-shrink-0" />
      {att.name} — image not kept on reopen
    </span>
  );
}

export function ChatAttachments({ onChange, reopenedAttachments, accept, compact, openRef }: ChatAttachmentsProps) {
  const { attachments, addFiles, onPaste, onDrop, remove } = useChatAttachments();
  const [dragActive, setDragActive] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    onChange?.(attachments);
  }, [attachments, onChange]);

  // Expose an imperative "open picker" to an external trigger (compact mode).
  useEffect(() => {
    if (!openRef) return;
    openRef.current = () => inputRef.current?.click();
    return () => {
      openRef.current = null;
    };
  }, [openRef]);

  // ── REOPENED mode: render the stored refs as placeholders, no live intake. ──
  if (reopenedAttachments && reopenedAttachments.length > 0) {
    return (
      <div data-testid="chat-attachments" className="flex flex-wrap gap-1.5">
        {reopenedAttachments.map((att, i) =>
          att.retained ? (
            <span
              key={`${att.name}-${i}`}
              data-testid="chat-attach-chip"
              data-retained="true"
              className="inline-flex items-center gap-1 rounded-lg bg-gray-100 px-2.5 py-1 text-[10px] text-gray-600"
            >
              {att.kind === "image" ? (
                <ImageIcon className="h-2.5 w-2.5" />
              ) : (
                <FileText className="h-2.5 w-2.5" />
              )}
              {att.name}
            </span>
          ) : (
            <PlaceholderChip key={`${att.name}-${i}`} att={att} />
          ),
        )}
      </div>
    );
  }

  // ── LIVE intake mode. ──
  // Shared hidden picker (both variants keep drag/paste on the wrapper).
  const hiddenInput = (
    <input
      ref={inputRef}
      type="file"
      multiple
      accept={accept ?? DEFAULT_ACCEPT}
      className="hidden"
      onChange={(e) => {
        if (e.target.files) void addFiles(e.target.files);
        e.target.value = "";
      }}
    />
  );

  // The mock's white bordered chip (Manrope name · size · remove) — Phase 39.
  const chips =
    attachments.length > 0 ? (
      <div className={`flex flex-wrap gap-1.5 ${compact ? "mb-2" : "pt-2"}`}>
        {attachments.map((att) => (
          <span
            key={att.id}
            data-testid="chat-attach-chip"
            data-retained="false"
            className={
              compact
                ? "inline-flex items-center gap-[7px] rounded-[var(--radius-node)] border border-line-control bg-surface-white px-2 py-[5px] text-[11.5px] text-ink-800"
                : "inline-flex items-center gap-1 rounded-lg bg-gray-100 px-2.5 py-1 text-[10px] text-gray-600"
            }
          >
            {att.kind === "image" ? (
              <img
                src={`data:${att.mimeType ?? "image/png"};base64,${att.data}`}
                alt={att.name}
                className="h-4 w-4 rounded object-cover"
              />
            ) : (
              <FileText className={compact ? "h-3 w-3 text-ink-500" : "h-2.5 w-2.5"} />
            )}
            <span className="max-w-[10rem] truncate font-sans font-medium">{att.name}</span>
            {att.kind === "file" && att.sizeBytes ? (
              <span className={compact ? "text-ink-200 tabular-nums" : "text-gray-400"}>
                {formatSize(att.sizeBytes)}
              </span>
            ) : null}
            <button
              type="button"
              aria-label={`Remove ${att.name}`}
              onClick={() => remove(att.id)}
              className={
                compact
                  ? "ml-0.5 text-ink-200 hover:text-status-failed"
                  : "ml-0.5 text-gray-400 hover:text-red-500"
              }
            >
              <X className="h-2.5 w-2.5" />
            </button>
          </span>
        ))}
      </div>
    ) : null;

  // COMPACT: chips-only (the composer bar owns the paperclip trigger via openRef).
  if (compact) {
    return (
      <div
        data-testid="chat-attachments"
        data-drag-active={dragActive ? "true" : "false"}
        onPaste={(e) => void onPaste(e)}
        onDragOver={(e) => {
          e.preventDefault();
          setDragActive(true);
        }}
        onDragLeave={() => setDragActive(false)}
        onDrop={(e) => {
          setDragActive(false);
          void onDrop(e);
        }}
      >
        {chips}
        {hiddenInput}
      </div>
    );
  }

  return (
    <div
      data-testid="chat-attachments"
      data-drag-active={dragActive ? "true" : "false"}
      onPaste={(e) => void onPaste(e)}
    >
      <div
        data-testid="chat-attach-dropzone"
        onDragOver={(e) => {
          e.preventDefault();
          setDragActive(true);
        }}
        onDragLeave={() => setDragActive(false)}
        onDrop={(e) => {
          setDragActive(false);
          void onDrop(e);
        }}
        className={`rounded-lg border border-dashed px-3 py-2 transition-colors ${
          dragActive ? "border-blue-400 bg-blue-50" : "border-gray-200 bg-transparent"
        }`}
      >
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          className="inline-flex items-center gap-1 text-[11px] text-gray-500 hover:text-gray-700"
        >
          <Paperclip className="h-3 w-3" />
          Attach or drop files
        </button>
        {hiddenInput}
      </div>

      {chips}
    </div>
  );
}
