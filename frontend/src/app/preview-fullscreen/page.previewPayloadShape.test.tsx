import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, act } from "@testing-library/react";

// ISS-915 (QA-KB-082) — a wrong-shape __app_preview__ payload must take the
// giveUp() exit (router.replace to run history), not crash AppBuilderPreview.
const replace = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace }),
}));

import PreviewFullscreenPage from "./page";

const BAD_PAYLOADS: Record<string, unknown> = {
  "files string": { files: "abc", projectName: "x" },
  "files [null]": { files: [null], projectName: "x" },
  "files [{}]": { files: [{}], projectName: "x" },
  "files {length:1}": { files: { length: 1 }, projectName: "x" },
  "files [1]": { files: [1], projectName: "x" },
};

describe("preview-fullscreen payload shape — ISS-915", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    replace.mockClear();
    sessionStorage.clear();
    vi.spyOn(console, "error").mockImplementation(() => {});
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it.each(Object.entries(BAD_PAYLOADS))(
    "ISS-915 %s exits via giveUp() instead of crashing",
    (_name, payload) => {
      sessionStorage.setItem("__app_preview__", JSON.stringify(payload));
      render(<PreviewFullscreenPage />);
      act(() => {
        vi.advanceTimersByTime(150);
      });
      expect(replace).toHaveBeenCalledTimes(1);
      expect(replace).toHaveBeenCalledWith("/runs");
    },
  );
});
