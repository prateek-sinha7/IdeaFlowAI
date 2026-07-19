/**
 * sseFrame — the ONE shared SSE block parser (m0o, INV-12). Extracted verbatim
 * from `useRunStream.dispatchBlock` so both the down-channel (useRunStream) and
 * the streamed POST up-channel (RunConnectionProvider.sendCommand) parse frames
 * through a SINGLE code path (no dual parse).
 *
 * Proves the extraction is behavior-identical to the pre-extraction dispatchBlock
 * parse: the real backend nested `{type,data}` envelope is unwrapped; the
 * legacy/mock flat shape passes through; empty/malformed blocks → null.
 */
import { describe, expect, it } from "vitest";
import { parseSseBlock } from "./sseFrame";

describe("parseSseBlock — the single shared SSE block parser", () => {
  it("unwraps the real backend nested {type,data} envelope on the data: line", () => {
    const block =
      'data: {"type":"chat_reply_chunk","data":{"pipeline_run_id":"run-9","message_id":"m1","delta":"He"}}';
    expect(parseSseBlock(block)).toEqual({
      type: "chat_reply_chunk",
      data: { pipeline_run_id: "run-9", message_id: "m1", delta: "He" },
    });
  });

  it("carries the terminal chat_reply envelope through unchanged", () => {
    const block =
      'data: {"type":"chat_reply","data":{"event_id":"chat-reply:m1","message_id":"m1","text":"Hello","seq":5}}';
    expect(parseSseBlock(block)).toEqual({
      type: "chat_reply",
      data: { event_id: "chat-reply:m1", message_id: "m1", text: "Hello", seq: 5 },
    });
  });

  it("stays tolerant of the legacy/mock flat shape (event: line + flat data)", () => {
    const block = 'event: chat_message\ndata: {"message_id":"m2","text":"hi"}';
    expect(parseSseBlock(block)).toEqual({
      type: "chat_message",
      data: { message_id: "m2", text: "hi" },
    });
  });

  it("returns null for an empty block", () => {
    expect(parseSseBlock("")).toBeNull();
    expect(parseSseBlock("   \n  ")).toBeNull();
  });

  it("returns null for a malformed data: line (unparseable JSON)", () => {
    expect(parseSseBlock("data: {not json}")).toBeNull();
  });
});
