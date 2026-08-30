// Shared frontend constants.

// Maximum characters of an attached/pasted document sliced into the workflow
// brief before it is sent to the backend. Mirrors the backend
// `settings.BRIEF_MAX_CHARS` (~150k tokens, safe under Haiku's 200k window) so
// an attached brief can actually reach the raised planner/clarify ingest cap.
export const ATTACH_MAX_CHARS = 450000;

// ISS-312: a text attachment (.txt/.md/.json/.csv) is read client-side and cut
// to ATTACH_MAX_CHARS. Append the same visible note the server-side extract
// path (.pdf/.docx/.pptx) already adds on `res.truncated`, so a cut is never
// silent on either branch. Shared so the two isTextFile call sites cannot drift.
export function truncateAttachmentText(content: string): string {
  if (content.length <= ATTACH_MAX_CHARS) return content;
  return `${content.slice(0, ATTACH_MAX_CHARS)}\n[Content truncated to ${ATTACH_MAX_CHARS.toLocaleString()} chars]`;
}
