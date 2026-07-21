/**
 * sseFrame — the ONE shared SSE block parser (m0o, INV-12). Lifted verbatim from
 * `useRunStream.dispatchBlock` (the id/event/data line-split + `{type,data}`
 * envelope-unwrap) so the SSE down-channel (`useRunStream`) and the streamed POST
 * up-channel (`RunConnectionProvider.sendCommand`) parse frames through a SINGLE
 * code path — no dual parse.
 *
 * Wire shapes (tolerant of both, WS-path parity):
 *   - Real backend: the `{type, data}` envelope nested in the `data:` line (no
 *     `event:` line) — unwrapped (BUG-014-B).
 *   - Legacy/mock: the `event:` line carries the type and the whole parsed object
 *     is the payload.
 * Returns null for an empty block or a malformed (`JSON.parse`-throwing) `data:`
 * line — discard, WS-path parity.
 *
 * The cursor advance (from `data.seq` / the `id:` line), keepalive drop,
 * `stream_attached` liveness and `onMessage` sink stay HOOK-LOCAL in
 * `dispatchBlock` around this parser — this helper owns only the envelope parse.
 */
export function parseSseBlock(
  rawBlock: string,
): { type: string; data: Record<string, unknown> } | null {
  if (!rawBlock.trim()) return null;
  let typeLine: string | undefined;
  let dataLine: string | undefined;
  for (const line of rawBlock.split("\n")) {
    if (line.startsWith("event:")) typeLine = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLine = line.slice(5).trim();
  }
  let type = typeLine ?? "";
  let data: Record<string, unknown> = {};
  if (dataLine) {
    try {
      const parsed = JSON.parse(dataLine) as Record<string, unknown>;
      if (typeof parsed.type === "string") {
        // Real backend wire: the `{type, data}` envelope nested in the `data:`
        // line (no `event:` line). Unwrap it (BUG-014-B).
        type = parsed.type;
        data = (parsed.data as Record<string, unknown>) ?? {};
      } else {
        // Legacy/mock flat shape: the `event:` line carries the type and the
        // whole parsed object is the payload — tolerant of both wires.
        data = parsed;
      }
    } catch {
      return null; // malformed — discard (WS-path parity)
    }
  }
  return { type, data };
}
