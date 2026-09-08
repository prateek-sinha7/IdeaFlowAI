import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { parseStreamMessage, serializeStreamMessage } from "./streamParser";

describe("parseStreamMessage", () => {
  // Suppress console.warn during tests
  beforeEach(() => {
    vi.spyOn(console, "warn").mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("should parse valid stream message with stream type", () => {
    const json = JSON.stringify({ type: "stream", data: "hello" });
    const result = parseStreamMessage(json);
    expect(result).not.toBeNull();
    expect(result?.type).toBe("stream");
  });

  it("should parse valid message with complete type", () => {
    const json = JSON.stringify({ type: "complete", result: { status: "ok" } });
    const result = parseStreamMessage(json);
    expect(result?.type).toBe("complete");
  });

  it("should parse valid message with error type", () => {
    const json = JSON.stringify({ type: "error", message: "Something failed" });
    const result = parseStreamMessage(json);
    expect(result?.type).toBe("error");
  });

  it("should parse valid message with phase_start type", () => {
    const json = JSON.stringify({ type: "phase_start", phase: "planning" });
    const result = parseStreamMessage(json);
    expect(result?.type).toBe("phase_start");
  });

  it("should parse valid message with phase_end type", () => {
    const json = JSON.stringify({ type: "phase_end", phase: "planning" });
    const result = parseStreamMessage(json);
    expect(result?.type).toBe("phase_end");
  });

  it("should return null for invalid JSON", () => {
    const result = parseStreamMessage("not valid json");
    expect(result).toBeNull();
  });

  it("should return null for non-object JSON", () => {
    const result = parseStreamMessage(JSON.stringify("string"));
    expect(result).toBeNull();
  });

  it("should return null for null value", () => {
    const result = parseStreamMessage(JSON.stringify(null));
    expect(result).toBeNull();
  });

  it("should return null for missing type field", () => {
    const json = JSON.stringify({ data: "hello" });
    const result = parseStreamMessage(json);
    expect(result).toBeNull();
  });

  it("should return null for invalid type value", () => {
    const json = JSON.stringify({ type: "invalid_type", data: "hello" });
    const result = parseStreamMessage(json);
    expect(result).toBeNull();
  });

  it("should return null for non-string type value", () => {
    const json = JSON.stringify({ type: 123, data: "hello" });
    const result = parseStreamMessage(json);
    expect(result).toBeNull();
  });

  it("should preserve all fields from valid message", () => {
    const json = JSON.stringify({
      type: "stream",
      data: "content",
      timestamp: 1234567890,
      id: "msg-123",
    });
    const result = parseStreamMessage(json);
    expect(result).toEqual({
      type: "stream",
      data: "content",
      timestamp: 1234567890,
      id: "msg-123",
    });
  });

  it("should handle empty object with missing required fields", () => {
    const json = JSON.stringify({});
    const result = parseStreamMessage(json);
    expect(result).toBeNull();
  });

  it("should log warning for invalid JSON", () => {
    const consoleSpy = vi.spyOn(console, "warn");
    parseStreamMessage("bad json");
    expect(consoleSpy).toHaveBeenCalled();
  });

  it("should log warning for missing type", () => {
    const consoleSpy = vi.spyOn(console, "warn");
    parseStreamMessage(JSON.stringify({ data: "hello" }));
    expect(consoleSpy).toHaveBeenCalled();
  });

  it("should log warning for invalid type", () => {
    const consoleSpy = vi.spyOn(console, "warn");
    parseStreamMessage(JSON.stringify({ type: "unknown" }));
    expect(consoleSpy).toHaveBeenCalled();
  });
});

describe("serializeStreamMessage", () => {
  it("should serialize message with stream type", () => {
    const msg = { type: "stream", data: "test" } as never;
    const result = serializeStreamMessage(msg);
    expect(result).toBe(JSON.stringify(msg));
  });

  it("should serialize message with complex data structure", () => {
    const msg = {
      type: "complete",
      result: {
        status: "success",
        data: [1, 2, 3],
        nested: { key: "value" },
      },
    } as never;
    const result = serializeStreamMessage(msg);
    expect(result).toBe(JSON.stringify(msg));
  });

  it("should serialize and deserialize roundtrip correctly", () => {
    const original = {
      type: "phase_start",
      phase: "planning",
      metadata: { version: 1 },
    } as never;
    const serialized = serializeStreamMessage(original);
    const deserialized = parseStreamMessage(serialized);
    expect(deserialized?.type).toBe("phase_start");
  });

  it("should handle all valid message types", () => {
    const types = ["stream", "complete", "error", "phase_start", "phase_end"];
    for (const type of types) {
      const msg = { type, data: "" } as never;
      const serialized = serializeStreamMessage(msg);
      const deserialized = parseStreamMessage(serialized);
      expect(deserialized?.type).toBe(type);
    }
  });

  it("should preserve null and undefined fields", () => {
    const msg = {
      type: "stream",
      data: null,
    } as never;
    const serialized = serializeStreamMessage(msg);
    const result = JSON.parse(serialized);
    expect(result.type).toBe("stream");
    expect(result.data).toBeNull();
  });
});
