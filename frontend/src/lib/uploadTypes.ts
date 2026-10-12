/**
 * The single client-side definition of which files can be attached.
 *
 * This existed as three independent hardcoded lists — an `accept` attribute per
 * upload surface plus a per-surface `isBinaryFile` regex — and they drifted. A
 * `.xlsx` was absent from every one of them: the picker filtered it out, and
 * once that was fixed the regex still skipped it, so the UI rendered an
 * attachment chip for a file it never uploaded. Silent, and invisible until an
 * agent downstream reported one document fewer than the user attached.
 *
 * `DOCUMENT_EXTS` must stay equal to the backend's `run_files._ALLOWED_EXTS`;
 * anything the picker offers but the backend rejects is a 415 the user cannot
 * explain, and anything the backend takes but the picker hides is unreachable.
 */

/** Mirrors backend `run_files._ALLOWED_EXTS`. Keep the two in sync. */
export const DOCUMENT_EXTS = [
  "pdf",
  "docx",
  "xlsx",
  "pptx",
  "txt",
  "md",
  "csv",
  "json",
  "html",
  "htm",
] as const;

/** Read client-side with FileReader; the rest are staged/extracted server-side. */
export const TEXT_EXTS = ["txt", "md", "json", "csv"] as const;

export const IMAGE_MIMES = ["image/png", "image/jpeg", "image/webp", "image/gif"] as const;

const extOf = (name: string) => (name.split(".").pop() ?? "").toLowerCase();

const has = (exts: readonly string[], name: string) => exts.includes(extOf(name));

/** Documents only — the value for a document-upload input's `accept`. */
export const DOCUMENT_ACCEPT = DOCUMENT_EXTS.map((e) => `.${e}`).join(",");

/** Documents plus the inline-image types, for surfaces that take both. */
export const DOCUMENT_AND_IMAGE_ACCEPT = `${DOCUMENT_ACCEPT},${IMAGE_MIMES.join(",")}`;

export const isImageUpload = (name: string, mime = "") =>
  (IMAGE_MIMES as readonly string[]).includes(mime) || /\.(png|jpe?g|webp|gif)$/i.test(name);

/** Text we can read in the browser. */
export const isTextUpload = (name: string) => has(TEXT_EXTS, name);

/** A document that must be staged + extracted server-side. */
export const isBinaryUpload = (name: string) =>
  has(DOCUMENT_EXTS, name) && !isTextUpload(name);

/** Remove ONE entry named `name` — the first — never every entry with that
 *  name. Attachment side-lists (staged uploads, extracted text) are keyed by
 *  filename, and the same file can be attached twice: filtering by name on
 *  removing one copy dropped the other copy's upload too, while its chip stayed
 *  on screen, so the run launched with no files and no warning. */
export function withoutOne<T extends { name: string }>(list: T[], name: string): T[] {
  const i = list.findIndex((x) => x.name === name);
  return i < 0 ? list : [...list.slice(0, i), ...list.slice(i + 1)];
}
