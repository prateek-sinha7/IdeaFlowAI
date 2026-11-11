/**
 * The text to show when saving a workflow fails.
 *
 * Most save errors reach the UI as an `ApiError` whose `message` is already
 * readable. A refusal such as `connector_grants_not_allowed` (422) carries the
 * run envelope `{error, code, recoverable}` in `detail`, and `ApiError.message`
 * is then the raw JSON of that object, so the readable text is `detail.error`.
 * Duck-typed on `detail` so this module does not depend on `@/lib/api`.
 */
export function saveErrorMessage(err: unknown, fallback: string): string {
  const detail = (err as { detail?: unknown } | null | undefined)?.detail;
  if (typeof detail === "object" && detail !== null && !Array.isArray(detail)) {
    const text = (detail as { error?: unknown }).error;
    if (typeof text === "string" && text.trim()) return text;
  }
  const message = (err as { message?: unknown } | null | undefined)?.message;
  return typeof message === "string" && message ? message : fallback;
}
