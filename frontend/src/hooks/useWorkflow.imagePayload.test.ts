/**
 * Image-input Wave 2 — payload merge: `startPipeline`'s `context` arg
 * (`extraParams` from IdeaInputPage) is merged into the run_pipeline payload via
 * `Object.assign(payload, context)`, so `images` lands at the top level while
 * the brief `message` stays base64-free (D3). A no-context call sends no
 * `images` key (byte-identical, INV-3).
 */
import { describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { useWorkflow } from "./useWorkflow";

function lastPayload(send: ReturnType<typeof vi.fn>): Record<string, unknown> {
  const raw = send.mock.calls[send.mock.calls.length - 1][0] as string;
  return JSON.parse(raw);
}

describe("useWorkflow — image payload merge (Wave 2)", () => {
  it("merges context.images into the run_pipeline payload; message carries no base64", () => {
    const send = vi.fn(() => true);
    const { result } = renderHook(() => useWorkflow(send));

    const images = [{ name: "x.png", mime_type: "image/png", data: "AAAA" }];
    act(() =>
      result.current.startPipeline(
        "prototype",
        "brief",
        ["a"],
        undefined,
        undefined,
        { images },
      ),
    );

    const payload = lastPayload(send);
    expect(payload.type).toBe("run_pipeline");
    expect(payload.images).toEqual(images);
    // D3: the brief message is exactly the text — no base64 inlined.
    expect(payload.message).toBe("brief");
  });

  it("sends no images key when no context is supplied (INV-3)", () => {
    const send = vi.fn(() => true);
    const { result } = renderHook(() => useWorkflow(send));

    act(() => result.current.startPipeline("prototype", "brief", ["a"]));

    const payload = lastPayload(send);
    expect("images" in payload).toBe(false);
    expect(payload.message).toBe("brief");
  });
});
