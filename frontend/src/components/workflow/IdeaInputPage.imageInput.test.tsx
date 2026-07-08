/**
 * Image-input Wave 2 — FE capture wiring: uploading an image to the picker
 * captures it into `attachedImages` and ships it OUT-OF-BAND as
 * `onRun(..., extraParams.images)`. The brief `message` NEVER contains base64
 * (Phase 25 D3). An image-less run emits a byte-identical payload (INV-3).
 *
 * Mirrors IdeaInputPage.modelOverrides.test.tsx (mocked AgentsPopup /
 * ReviewGatesSection / useSpeechRecognition, SkillsHooksProvider render).
 */

import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { IdeaInputPage } from "./IdeaInputPage";
import { SkillsHooksProvider } from "@/context/SkillsHooksContext";

// UPLD-04: the attach handler now routes image Files through resizeImage, which
// decodes via createImageBitmap. jsdom lacks it — mock a small bitmap that is
// already within the bound so resizeImage passes the ORIGINAL base64 through
// unchanged (no-upscale passthrough). This keeps the D3 out-of-band assertions
// exact while proving the attach flow routes through the resize helper.
beforeEach(() => {
  vi.stubGlobal(
    "createImageBitmap",
    vi.fn(async () => ({ width: 12, height: 12, close: vi.fn() })),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

vi.mock("@/hooks/useSpeechRecognition", () => ({
  useSpeechRecognition: () => ({
    isListening: false,
    transcript: "",
    startListening: vi.fn(),
    stopListening: vi.fn(),
    isSupported: false,
  }),
}));

vi.mock("./AgentsPopup", () => ({
  AgentsPopup: () => null,
}));

vi.mock("./ReviewGatesSection", () => ({
  ReviewGatesSection: () => null,
}));

function renderPage(onRun = vi.fn()) {
  const { container } = render(
    <SkillsHooksProvider>
      <IdeaInputPage workflowType="user_stories" onBack={vi.fn()} onRun={onRun} />
    </SkillsHooksProvider>,
  );
  return { onRun, container };
}

const BASE64_MARKER = "aW1hZ2VfYnl0ZXNfbm90X2luX2JyaWVm"; // "image_bytes_not_in_brief"

describe("IdeaInputPage — image capture wiring (Wave 2)", () => {
  it("captures an uploaded image into extraParams.images; brief has no base64 (D3)", async () => {
    const user = userEvent.setup();
    const { onRun, container } = renderPage();

    await user.type(screen.getByRole("textbox"), "Design a login screen.");

    // Upload a small PNG to the hidden file input.
    const fileInput = container.querySelector(
      'input[type="file"]',
    ) as HTMLInputElement;
    const bytes = atob(BASE64_MARKER);
    const arr = new Uint8Array(bytes.length);
    for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i);
    const file = new File([arr], "login.png", { type: "image/png" });
    await user.upload(fileInput, file);

    // The FileReader is async — wait for the image chip to appear.
    await waitFor(() => expect(screen.getByText("login.png")).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: /run workflow/i }));

    expect(onRun).toHaveBeenCalledTimes(1);
    const [message, , , extraParams] = onRun.mock.calls[0];
    // D3: the brief text is exactly the typed brief — no base64 anywhere.
    expect(message).toBe("Design a login screen.");
    expect(message).not.toContain(BASE64_MARKER);
    // The image rides out-of-band as extraParams.images.
    expect(extraParams.images).toHaveLength(1);
    expect(extraParams.images[0].name).toBe("login.png");
    expect(extraParams.images[0].mime_type).toBe("image/png");
    expect(extraParams.images[0].data).toBe(BASE64_MARKER);
  });

  it("omits images (extraParams undefined) when no image is attached (INV-3)", async () => {
    const user = userEvent.setup();
    const { onRun } = renderPage();

    await user.type(screen.getByRole("textbox"), "Design a login screen.");
    await user.click(screen.getByRole("button", { name: /run workflow/i }));

    expect(onRun).toHaveBeenCalledTimes(1);
    const [, , , extraParams] = onRun.mock.calls[0];
    expect(extraParams).toBeUndefined();
  });
});
