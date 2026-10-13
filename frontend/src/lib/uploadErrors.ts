/**
 * User-facing text for document-upload failures (stage + extract-text) and the
 * launch-time `uploads_missing` rejection.
 *
 * Reads the `status` / `detail` that `ApiError` (lib/api.ts) carries, checked
 * structurally rather than with `instanceof`: this module must not import
 * `@/lib/api`, because component tests mock that module partially and an
 * `ApiError` binding would not exist there. Never echoes server detail or an
 * HTML error body back to the user.
 */

/** Mirrors backend `file_extract._MAX_FILE_BYTES` (10 MiB per document). */
export const UPLOAD_MAX_FILE_MB = 10;
const UPLOAD_MAX_FILE_BYTES = UPLOAD_MAX_FILE_MB * 1024 * 1024;

export const UPLOAD_TOO_LARGE_MESSAGE = `File is too large for this server (limit ${UPLOAD_MAX_FILE_MB} MB)`;
export const UPLOAD_TIMEOUT_MESSAGE = "Upload timed out. Try again.";
export const UPLOAD_RATE_LIMITED_MESSAGE =
  "Too many uploads at once. Wait a moment, then try again.";
export const UPLOAD_FAILED_MESSAGE = "Upload failed. Remove the file or try again.";
export const UPLOADS_MISSING_MESSAGE =
  "The attached documents did not reach the server. Re-attach them and launch again.";

interface StatusError {
  status: number;
  detail?: unknown;
}

function hasStatus(err: unknown): err is StatusError {
  return (
    typeof err === "object" &&
    err !== null &&
    typeof (err as { status?: unknown }).status === "number"
  );
}

/** True when a document is over the backend's per-file cap — fail before uploading. */
export function isOverUploadLimit(size: number): boolean {
  return size > UPLOAD_MAX_FILE_BYTES;
}

/** Map a failed upload call to the short reason shown on the file chip. */
export function describeUploadError(err: unknown): string {
  if (hasStatus(err)) {
    if (err.status === 413) return UPLOAD_TOO_LARGE_MESSAGE;
    // nginx `limit_req` on /api/ (shared zone): a bulk attach can exceed the burst.
    if (err.status === 429) return UPLOAD_RATE_LIMITED_MESSAGE;
    // ApiError(0, …) is the client-side abort after the request timeout.
    if (err.status === 0) return UPLOAD_TIMEOUT_MESSAGE;
  }
  return UPLOAD_FAILED_MESSAGE;
}

/** The backend's pre-mint 422 `uploads_missing` launch rejection. */
export function isUploadsMissingError(err: unknown): boolean {
  if (!hasStatus(err) || err.status !== 422) return false;
  const detail = err.detail;
  return (
    typeof detail === "object" &&
    detail !== null &&
    (detail as { code?: unknown }).code === "uploads_missing"
  );
}
