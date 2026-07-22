// Shared frontend constants.

// Maximum characters of an attached/pasted document sliced into the workflow
// brief before it is sent to the backend. Mirrors the backend
// `settings.BRIEF_MAX_CHARS` (~150k tokens, safe under Haiku's 200k window) so
// an attached brief can actually reach the raised planner/clarify ingest cap.
export const ATTACH_MAX_CHARS = 450000;
