import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FigmaExportModal } from "./FigmaExportModal";

function setup(props: Partial<React.ComponentProps<typeof FigmaExportModal>> = {}) {
  const onClose = vi.fn();
  const onConfirm = vi.fn();
  const utils = render(
    <FigmaExportModal open onClose={onClose} onConfirm={onConfirm} {...props} />,
  );
  return { onClose, onConfirm, ...utils };
}

describe("FigmaExportModal", () => {
  it("renders nothing when closed", () => {
    setup({ open: false });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("renders an accessible dialog on step 1 with the ZIP contents", () => {
    setup();
    const dialog = screen.getByRole("dialog", { name: "Export to Figma" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(screen.getByText("Step 1 of 5")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Download the ZIP" })).toBeInTheDocument();
    expect(screen.getByText("prototype-figma.json")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Back/ })).not.toBeInTheDocument();
  });

  it("advances with Next, shows Back, and shows the note on step 3", async () => {
    const user = userEvent.setup();
    setup();
    await user.click(screen.getByRole("button", { name: /Next/ }));
    expect(screen.getByText("Step 2 of 5")).toBeInTheDocument();
    expect(screen.queryByText("prototype-figma.json")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Back/ })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Next/ }));
    expect(screen.getByText("Step 3 of 5")).toBeInTheDocument();
    expect(screen.getByText(/Requires Figma Desktop/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Back/ }));
    expect(screen.getByText("Step 2 of 5")).toBeInTheDocument();
  });

  it("jumps to a step via the step pills", async () => {
    const user = userEvent.setup();
    setup();
    await user.click(screen.getByRole("button", { name: /Import your prototype/ }));
    expect(screen.getByText("Step 4 of 5")).toBeInTheDocument();
    // Earlier steps are marked done; clicking back to the first works.
    await user.click(screen.getByRole("button", { name: /Download the ZIP/ }));
    expect(screen.getByText("Step 1 of 5")).toBeInTheDocument();
  });

  it("confirms and closes from the last step", async () => {
    const user = userEvent.setup();
    const { onConfirm, onClose } = setup();
    await user.click(screen.getByRole("button", { name: /Done — frames ready/ }));
    expect(screen.queryByRole("button", { name: /Next/ })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Download ZIP/ }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("disables the download button and shows progress while loading", async () => {
    const user = userEvent.setup();
    const { onConfirm } = setup({ loading: true });
    await user.click(screen.getByRole("button", { name: /Done — frames ready/ }));
    const btn = screen.getByRole("button", { name: /Generating/ });
    expect(btn).toBeDisabled();
    await user.click(btn);
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("closes via Close button, Cancel, backdrop, and Escape but not on dialog click", async () => {
    const user = userEvent.setup();
    const { onClose } = setup();

    await user.click(screen.getByRole("dialog"));
    expect(onClose).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Close" }));
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onClose).toHaveBeenCalledTimes(2);

    await user.click(screen.getByRole("presentation"));
    expect(onClose).toHaveBeenCalledTimes(3);

    await user.keyboard("{Enter}");
    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledTimes(4);
  });

  it("resets to step 1 when reopened and removes the key listener when closed", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    const onConfirm = vi.fn();
    const { rerender } = render(<FigmaExportModal open onClose={onClose} onConfirm={onConfirm} />);
    await user.click(screen.getByRole("button", { name: /Next/ }));
    expect(screen.getByText("Step 2 of 5")).toBeInTheDocument();

    rerender(<FigmaExportModal open={false} onClose={onClose} onConfirm={onConfirm} />);
    await user.keyboard("{Escape}");
    expect(onClose).not.toHaveBeenCalled();

    rerender(<FigmaExportModal open onClose={onClose} onConfirm={onConfirm} />);
    expect(screen.getByText("Step 1 of 5")).toBeInTheDocument();
  });
});
