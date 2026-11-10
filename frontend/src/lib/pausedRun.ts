// Shared parser for a paused run's persisted `error` field. The backend stores the
// pause as "paused:<kind>: <reason>" (kind: credentials | poison | budget). Shared by
// the run lane (RunChatLane) and the reopen path (page.tsx) so both read it identically.
export interface PausedRunInfo {
  kind: string;
  reason: string;
}

export function parsePausedRunError(error: string | null | undefined): PausedRunInfo | undefined {
  const match = /^paused:([a-z_]+): ([\s\S]*)$/.exec(error?.trim() ?? "");
  return match ? { kind: match[1], reason: match[2].trim() } : undefined;
}
