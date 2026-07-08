/**
 * useChatAttachments — the chat lane's attachment intake (Phase 31, CHATUI-03 +
 * the UPLD-04 residue: paste + drag-drop + client resize).
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

export interface UseChatAttachments {
  attachments: PendingAttachment[];
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
      const next: PendingAttachment = {
        id: mintId(),
        kind: "file",
        name: file.name,
        mimeType: file.type || undefined,
        sizeBytes: file.size,
        retained: false,
        data,
      };
      setAttachments((prev) => [...prev, next]);
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
    setAttachments((prev) => prev.filter((a) => a.id !== id));
  }, []);

  const clear = useCallback(() => setAttachments([]), []);

  return { attachments, addFiles, onPaste, onDrop, remove, clear };
}
