/**
 * ChatAttachments — composer attachment sub-surface (Phase 31, CHATUI-03).
 * `resizeImage` is mocked so a dropped image deterministically yields a chip.
 *
 * Proves:
 *   1. a dropped image renders a removable preview chip; remove drops it;
 *   2. the drop zone toggles its drag-active state on dragOver/dragLeave;
 *   3. REOPENED mode renders the ND-10 "image not kept" placeholder for a
 *      retained:false ref and NO <img> (payload-transient — no bytes on reopen).
 */
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ChatAttachments } from "./ChatAttachments";
import type { ChatAttachment } from "@/types/index";

vi.mock("@/lib/resizeImage", () => ({
  resizeImage: vi.fn(async () => ({
    mime_type: "image/png",
    data: "QUJD",
    width: 40,
    height: 40,
  })),
}));

function imageFile(name = "photo.png"): File {
  return new File(["img"], name, { type: "image/png" });
}

describe("ChatAttachments", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders a removable preview chip for a dropped image", async () => {
    render(<ChatAttachments />);
    const dropzone = screen.getByTestId("chat-attach-dropzone");

    await act(async () => {
      fireEvent.drop(dropzone, { dataTransfer: { files: [imageFile()] } });
    });

    const chip = await screen.findByTestId("chat-attach-chip");
    expect(chip).toBeInTheDocument();
    expect(screen.getByText("photo.png")).toBeInTheDocument();

    // Remove drops the chip.
    await act(async () => {
      fireEvent.click(screen.getByLabelText("Remove photo.png"));
    });
    await waitFor(() =>
      expect(screen.queryByTestId("chat-attach-chip")).not.toBeInTheDocument(),
    );
  });

  it("toggles drag-active on dragOver/dragLeave", () => {
    render(<ChatAttachments />);
    const surface = screen.getByTestId("chat-attachments");
    const dropzone = screen.getByTestId("chat-attach-dropzone");

    expect(surface).toHaveAttribute("data-drag-active", "false");
    fireEvent.dragOver(dropzone);
    expect(surface).toHaveAttribute("data-drag-active", "true");
    fireEvent.dragLeave(dropzone);
    expect(surface).toHaveAttribute("data-drag-active", "false");
  });

  it("renders the ND-10 placeholder (no <img>) for a non-retained ref on reopen", () => {
    const refs: ChatAttachment[] = [
      { kind: "image", name: "screenshot.png", retained: false },
    ];
    const { container } = render(<ChatAttachments reopenedAttachments={refs} />);

    const chip = screen.getByTestId("chat-attach-chip");
    expect(chip).toHaveAttribute("data-retained", "false");
    expect(screen.getByText(/image not kept on reopen/i)).toBeInTheDocument();
    // Payload-transient — no bytes on reopen, so no <img> is rendered.
    expect(container.querySelector("img")).toBeNull();
  });
});
