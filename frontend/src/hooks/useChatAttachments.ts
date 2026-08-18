/**
 * useChatAttachments — the chat lane's attachment intake (Phase 31, CHATUI-03 +
 * the UPLD-04 residue: paste + drag-drop + client resize).
 *
 * FIX-218 (KAN-170): extended to extract text from non-image file attachments so
 * the Concierge and running pipeline agents can read the file content. Text formats
 * (txt/md/csv/json) are read client-side via FileReader text mode. Binary formats
 * (pdf/docx/pptx) are extracted server-side via GET /api/files/extract-text — the
 * same endpoint the launch composer uses. Extracted text is stored as `fileContents`
 * state alongside `attachments`. On send, both are included in the POST body so the
 * backend can thread the content to the Concierge prompt and ectx.steering_notes.
 * Extraction errors are surfaced per-file (never block the send — the attachment
 * chip shows and the Concierge informs the user of the failure).
 *
 * The launch composer (`IdeaInputPage.tsx`) already has a file picker + base64 +
 * preview chips for the image waves. This hook builds the chat lane's OWN intake
 * on the same pattern but ADDS the two intakes flagged in evidence 04 §5
 * CORRECTIONS #5: clipboard `onPaste` (extract image items) and `onDrop`
 * (dataTransfer files). Images route THROUGH Phase-30's `resizeImage` (UPLD-04)
 * so an oversized photo is downscaled BEFORE base64; non-image files pass
 * through untouched.
 *
 * Produced records extend the pinned plan-03 `ChatAttachment` type. Every record
 * is `retained:false` (ND-10 / LOCK-E payload-transient — images/files ride the
 * message payload out-of-band and are NEVER persisted, so a reopened turn shows
 * the "image not kept" placeholder rather than a stale byte reference).
 *
 * A client-side allow-list + size cap MIRROR the server `_validate_images` caps
 * (T-31-06-D / T-31-06-T): the reject is UX-only defense-in-depth; the
 * authoritative validation stays server-side (Phase 30 caps).
 */
import { useCallback, useState } from "react";

import { resizeImage } from "@/lib/resizeImage";
import { extractFileText, getToken } from "@/lib/api";
import type { ChatAttachment } from "@/types/index";

/** A live attachment draft: the pinned `ChatAttachment` ref PLUS the payload
 *  (`data` base64) the composer needs to preview a thumbnail and hand the
 *  transport. The `data` never persists (ND-10) — it rides the outbound message
 *  payload only. */
export interface PendingAttachment extends ChatAttachment {
  /** Stable client id — the key for preview chips and `remove(id)`. */
  id: string;
  /** Raw base64 (prefix-stripped) — image thumbnail source + send payload. */
  data: string;
  /** Final pixel width for images (0 when unknown / degraded). */
  width?: number;
  /** Final pixel height for images (0 when unknown / degraded). */
  height?: number;
}

/**
 * FIX-218 (KAN-170): pre-extracted file content entry sent in body.file_contents.
 * name — original filename. text — extracted plain text (empty on error).
 * error — extraction error message shown to user (absent when successful).
 * truncated — true when the server capped the text.
 */
export interface FileContentEntry {
  name: string;
  text: string;
  error?: string;
  truncated?: boolean;
}

// Client allow-list mirroring the server `_validate_images` ingress caps.
const IMAGE_MIMES = ["image/png", "image/jpeg", "image/webp", "image/gif"];
const IMAGE_EXT = /\.(png|jpe?g|webp|gif)$/i;
// Non-image document types the lane accepts (the launch-composer accept list).
const DOC_MIMES = [
  "application/pdf",
  "application/msword",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "application/vnd.openxmlformats-officedocument.presentationml.presentation",
  "text/plain",
  "text/markdown",
  "text/csv",
  "application/json",
];
const DOC_EXT = /\.(pdf|docx?|pptx|txt|md|json|csv)$/i;
// FIX-218: binary formats that need server-side extraction via /api/files/extract-text
const BINARY_EXT = /\.(pdf|docx?|pptx)$/i;
// FIX-218: text-readable formats that can be decoded client-side
const TEXT_EXT = /\.(txt|md|json|csv)$/i;
// FIX-218: client-side cap for text files (~6 000 chars mirrors backend _ATTACHED_FILE_TEXT_CAP)
const TEXT_CLIENT_CAP = 6_000;

// Per-image cap (~3.75 MB) mirroring the server per-image byte cap, checked
// POST-resize. Documents cap at the 10 MB server per-file ceiling (30-01).
const MAX_IMAGE_BYTES = 3_750_000;
const MAX_FILE_BYTES = 10 * 1024 * 1024;

let _seq = 0;
function mintId(): string {
  _seq += 1;
  return `att-${Date.now()}-${_seq}`;
}

function isImageFile(file: File): boolean {
  return IMAGE_MIMES.includes(file.type) || IMAGE_EXT.test(file.name);
}

function isAllowedDoc(file: File): boolean {
  return DOC_MIMES.includes(file.type) || DOC_EXT.test(file.name);
}

/** Approx decoded byte size of a base64 payload (4 chars ≈ 3 bytes). */
function approxBase64Bytes(data: string): number {
  return Math.floor((data.length * 3) / 4);
}

/** Read a File to raw (prefix-stripped) base64 — the file passthrough path.
 *  Degrades to an empty payload rather than throwing (never blocks the attach). */
function fileToBase64(file: File): Promise<string> {
  return new Promise<string>((resolve) => {
    try {
      const reader = new FileReader();
      reader.onload = () =>
        resolve(String(reader.result ?? "").replace(/^data:[^;]+;base64,/, ""));
      reader.onerror = () => resolve("");
      reader.readAsDataURL(file);
    } catch {
      resolve("");
    }
  });
}

/** FIX-218 (KAN-170): Read a text file as plain text (client-side, no network).
 *  Used for .txt / .md / .csv / .json files. Degrades to "" on read error. */
function fileToText(file: File): Promise<string> {
  return new Promise<string>((resolve) => {
    try {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result ?? ""));
      reader.onerror = () => resolve("");
      reader.readAsText(file, "utf-8");
    } catch {
      resolve("");
    }
  });
}

export interface UseChatAttachments {
  attachments: PendingAttachment[];
  /**
   * FIX-218 (KAN-170): pre-extracted file text entries — [{name, text, error?, truncated?}].
   * Populated alongside `attachments` for file-kind entries. Sent in body.file_contents
   * so the backend can thread the content to the Concierge and pipeline agents.
   * Empty for image-only sends.
   */
  fileContents: FileContentEntry[];
  /**
   * True while a binary file (pdf/docx/pptx) is being extracted server-side.
   * The chip renders a "reading…" label while this is true so the user knows
   * VelocityAI is processing the file before they send.
   */
  isExtracting: boolean;
  /**
   * The set of attachment ids currently being extracted (for per-chip indicators).
   * Populated when a binary file starts extraction, cleared when done/errored.
   */
  extractingIds: Set<string>;
  /** Route picker/paste/drop files through resize (images) / passthrough (files)
   *  with the client allow-list + cap. Resolves once all files are processed. */
  addFiles: (files: File[] | FileList) => Promise<void>;
  /** Clipboard paste — extract image (file-kind) items and route them. */
  onPaste: (event: ClipboardEventLike) => Promise<void>;
  /** Drag-drop — route `dataTransfer.files`. */
  onDrop: (event: DragEventLike) => Promise<void>;
  /** Drop one preview chip. */
  remove: (id: string) => void;
  /** Empty the intake (after a send). */
  clear: () => void;
}

// Minimal structural shapes so the handlers accept both React synthetic events
// and native DOM events without a DOM-lib coupling.
export interface ClipboardEventLike {
  clipboardData?: { items?: ArrayLike<DataTransferItemLike> | null } | null;
  preventDefault?: () => void;
}
export interface DataTransferItemLike {
  kind: string;
  getAsFile: () => File | null;
}
export interface DragEventLike {
  dataTransfer?: { files?: ArrayLike<File> | null } | null;
  preventDefault?: () => void;
}

export function useChatAttachments(): UseChatAttachments {
  const [attachments, setAttachments] = useState<PendingAttachment[]>([]);
  // FIX-218 (KAN-170): parallel state for extracted file text entries.
  const [fileContents, setFileContents] = useState<FileContentEntry[]>([]);
  // Tracks which attachment ids are currently being extracted server-side,
  // so the chip can show a "reading…" indicator while the API call is in flight.
  const [extractingIds, setExtractingIds] = useState<Set<string>>(new Set());

  const isExtracting = extractingIds.size > 0;

  const addFiles = useCallback(async (files: File[] | FileList) => {
    const list = Array.from(files);
    for (const file of list) {
      if (isImageFile(file)) {
        // UPLD-04: downscale oversized images client-side BEFORE base64.
        // resizeImage is aspect-preserving, no-upscale, degrade-not-block.
        const resized = await resizeImage(file);
        const bytes = approxBase64Bytes(resized.data);
        // Client cap (post-resize) — reject rather than send an over-cap image.
        if (!resized.data || bytes > MAX_IMAGE_BYTES) continue;
        const next: PendingAttachment = {
          id: mintId(),
          kind: "image",
          name: file.name,
          mimeType: resized.mime_type,
          sizeBytes: bytes,
          retained: false,
          data: resized.data,
          width: resized.width,
          height: resized.height,
        };
        setAttachments((prev) => [...prev, next]);
        continue;
      }
      // Non-image: reject anything outside the doc allow-list BEFORE base64.
      if (!isAllowedDoc(file) || file.size > MAX_FILE_BYTES) continue;
      const data = await fileToBase64(file);
      const attachId = mintId();
      const next: PendingAttachment = {
        id: attachId,
        kind: "file",
        name: file.name,
        mimeType: file.type || undefined,
        sizeBytes: file.size,
        retained: false,
        data,
      };
      setAttachments((prev) => [...prev, next]);

      // FIX-218 (KAN-170): extract plain text from the file so the backend can
      // thread it to the Concierge and pipeline agents via body.file_contents.
      // Text formats: client-side read (fast, no network).
      // Binary formats: server-side via /api/files/extract-text (needs auth token).
      // Extraction is best-effort — errors are surfaced per-file, never block send.
      if (TEXT_EXT.test(file.name)) {
        // Client-side text extraction (txt, md, csv, json) — fast, no loading state.
        const rawText = await fileToText(file);
        const truncated = rawText.length > TEXT_CLIENT_CAP;
        const text = truncated ? rawText.slice(0, TEXT_CLIENT_CAP) : rawText;
        const entry: FileContentEntry = {
          name: file.name,
          text,
          truncated,
        };
        if (!text.trim()) {
          entry.error = "File appears to be empty or could not be read as text.";
          entry.text = "";
        }
        setFileContents((prev) => [...prev, entry]);
      } else if (BINARY_EXT.test(file.name)) {
        // Server-side binary extraction (pdf, docx, pptx) — show "reading…" on chip.
        const token = getToken();
        if (!token) {
          setFileContents((prev) => [...prev, {
            name: file.name,
            text: "",
            error: "Not authenticated — please reload and try again.",
          }]);
          continue;
        }
        // Mark this attachment as being extracted so the chip shows the loading state.
        setExtractingIds((prev) => new Set([...prev, attachId]));
        try {
          const result = await extractFileText(token, file);
          setFileContents((prev) => [...prev, {
            name: result.filename || file.name,
            text: result.text || "",
            truncated: result.truncated,
            error: result.text?.trim()
              ? undefined
              : "File was parsed but no text could be extracted. It may be image-based or encrypted.",
          }]);
        } catch (err: unknown) {
          const msg = err instanceof Error ? err.message : String(err);
          setFileContents((prev) => [...prev, {
            name: file.name,
            text: "",
            error: `Could not extract text: ${msg}`,
          }]);
        } finally {
          // Extraction done (success or error) — clear the loading indicator.
          setExtractingIds((prev) => {
            const next = new Set(prev);
            next.delete(attachId);
            return next;
          });
        }
      }
      // Non-extractable formats (e.g. raw binary not in BINARY_EXT or TEXT_EXT):
      // attachment chip is shown but no text entry is added — the Concierge
      // will not see content for those files (by design — unsupported format).
    }
  }, []);

  const onPaste = useCallback(
    async (event: ClipboardEventLike) => {
      const items = event.clipboardData?.items;
      if (!items) return;
      const files: File[] = [];
      for (const item of Array.from(items)) {
        if (item.kind === "file") {
          const f = item.getAsFile();
          if (f) files.push(f);
        }
      }
      if (files.length) {
        event.preventDefault?.();
        await addFiles(files);
      }
    },
    [addFiles],
  );

  const onDrop = useCallback(
    async (event: DragEventLike) => {
      const files = event.dataTransfer?.files;
      if (!files || files.length === 0) return;
      event.preventDefault?.();
      await addFiles(Array.from(files));
    },
    [addFiles],
  );

  const remove = useCallback((id: string) => {
    // FIX-218: remove the attachment chip AND its matching fileContents entry.
    // Find the name before removing so we can clean up fileContents by name.
    setAttachments((prev) => {
      const removed = prev.find((a) => a.id === id);
      if (removed) {
        setFileContents((fc) => fc.filter((f) => f.name !== removed.name));
      }
      return prev.filter((a) => a.id !== id);
    });
    // Also clear any in-progress extraction for this id.
    setExtractingIds((prev) => {
      const next = new Set(prev);
      next.delete(id);
      return next;
    });
  }, []);

  const clear = useCallback(() => {
    setAttachments([]);
    // FIX-218: clear extracted text entries and extraction tracking on send.
    setFileContents([]);
    setExtractingIds(new Set());
  }, []);

  return { attachments, fileContents, isExtracting, extractingIds, addFiles, onPaste, onDrop, remove, clear };
}
