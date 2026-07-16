/**
 * Image-input Wave 2 — payload merge: `startPipeline`'s `context` arg
 * (`extraParams` from IdeaInputPage) is merged into the run_pipeline payload via
 * `Object.assign(payload, context)`, so `images` lands at the top level while
 * the brief `message` stays base64-free (D3). A no-context call sends no
 * `images` key (byte-identical, INV-3).
 *
 * 44-06: SSE + REST is the sole transport, so `startPipeline` now launches via
 * `runConnection.sendCommand(null, payload)`. We mock `useRunConnection` to
 * capture the payload object handed to `sendCommand` (previously the JSON string
 * passed to the retired `websocketSend`).
 */
import { describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { useWorkflow } from "./useWorkflow";
import { useRunConnection } from "@/providers/RunConnectionProvider";

vi.mock("@/providers/RunConnectionProvider", () => ({
  useRunConnection: vi.fn(),
}));

function makeSendCommand() {
  return vi.fn(
    async (
      _runId: string | null,
      _payload: Record<string, unknown>,
    ): Promise<string | null> => null,
  );
}

function mockConnection(sendCommand: ReturnType<typeof makeSendCommand>): void {
  vi.mocked(useRunConnection).mockReturnValue({
    enabled: true,
    phase: "idle",
    liveRunIds: [],
    reattach: vi.fn(),
    attachRun: vi.fn(),
    detachRun: vi.fn(),
    subscribe: vi.fn(() => () => {}),
    sendCommand,
  });
}

function lastPayload(
  sendCommand: ReturnType<typeof makeSendCommand>,
): Record<string, unknown> {
  const calls = sendCommand.mock.calls;
  return calls[calls.length - 1][1] as Record<string, unknown>;
}

describe("useWorkflow — image payload merge (Wave 2)", () => {
  it("merges context.images into the run_pipeline payload; message carries no base64", () => {
    const sendCommand = makeSendCommand();
    mockConnection(sendCommand);
    const { result } = renderHook(() => useWorkflow());

    const images = [{ name: "x.png", mime_type: "image/png", data: "AAAA" }];
    act(() => {
      void result.current.startPipeline(
        "prototype",
        "brief",
        ["a"],
        undefined,
        undefined,
        { images },
      );
    });

    const payload = lastPayload(sendCommand);
    expect(payload.type).toBe("run_pipeline");
    expect(payload.images).toEqual(images);
    // D3: the brief message is exactly the text — no base64 inlined.
    expect(payload.message).toBe("brief");
  });

  it("sends no images key when no context is supplied (INV-3)", () => {
    const sendCommand = makeSendCommand();
    mockConnection(sendCommand);
    const { result } = renderHook(() => useWorkflow());

    act(() => {
      void result.current.startPipeline("prototype", "brief", ["a"]);
    });

    const payload = lastPayload(sendCommand);
    expect("images" in payload).toBe(false);
    expect(payload.message).toBe("brief");
  });
});
