import type { StreamMessage } from "@/types";

const VALID_TYPES = ["stream", "complete", "error", "phase_start", "phase_end"];

/**
 * Parse a JSON string into a StreamMessage.
 * Returns null on malformed input (logs and discards).
 */
export function parseStreamMessage(json: string): StreamMessage | null {
  let parsed: unknown;
  try {
    parsed = JSON.parse(json);
  } catch (e) {
    console.warn(
      "Failed to parse stream message JSON:",
      e instanceof Error ? e.message : "Invalid JSON"
    );
    return null;
  }

  if (!parsed || typeof parsed !== "object") {
    console.warn("Invalid stream message: expected an object");
    return null;
  }

  const obj = parsed as Record<string, unknown>;

  if (typeof obj.type !== "string" || !VALID_TYPES.includes(obj.type)) {
    console.warn(
      `Invalid stream message: invalid or missing "type" field, got: ${String(obj.type)}`
    );
    return null;
  }

  return obj as unknown as StreamMessage;
}

/**
 * Serialize a StreamMessage to a JSON string.
 */
export function serializeStreamMessage(msg: StreamMessage): string {
  return JSON.stringify(msg);
}
