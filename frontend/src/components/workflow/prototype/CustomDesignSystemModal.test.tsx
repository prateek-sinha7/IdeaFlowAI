import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  CustomDesignSystemModal,
  loadCustomDesignSystems,
  saveCustomDesignSystems,
  type CustomDesignSystem,
} from "./CustomDesignSystemModal";

const KEY = "flowin.custom_design_systems";
const LONG_BODY = "# Brand\n" + "x".repeat(60);

const sample: CustomDesignSystem = {
  id: "custom:acme",
  name: "Acme",
  body: LONG_BODY,
  createdAt: 123,
};

beforeEach(() => localStorage.clear());
afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe("custom design system storage helpers", () => {
  it("returns [] when nothing is stored", () => {
    expect(loadCustomDesignSystems()).toEqual([]);
  });

  it("round-trips saved systems", () => {
    saveCustomDesignSystems([sample]);
    expect(loadCustomDesignSystems()).toEqual([sample]);
  });

  it("returns [] when stored JSON is corrupt", () => {
    localStorage.setItem(KEY, "{not json");
    expect(loadCustomDesignSystems()).toEqual([]);
  });
});

describe("CustomDesignSystemModal", () => {
  function setup(props: Partial<React.ComponentProps<typeof CustomDesignSystemModal>> = {}) {
    const onSave = vi.fn();
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<CustomDesignSystemModal onSave={onSave} onClose={onClose} {...props} />);
    return { onSave, onClose, user };
  }

  it("renders add-mode labels", () => {
    setup();
    expect(screen.getByRole("dialog", { name: "Add custom design system" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add design system" })).toBeInTheDocument();
  });

  it("renders edit-mode labels and prefilled fields", () => {
    setup({ existing: sample });
    expect(screen.getByRole("heading", { name: "Edit custom design system" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save changes" })).toBeInTheDocument();
    expect(screen.getByLabelText(/Name/)).toHaveValue("Acme");
    expect(screen.queryByRole("button", { name: "Load example" })).not.toBeInTheDocument();
  });

  it("loads the example and hides the button once content exists", async () => {
    const { user } = setup();
    await user.click(screen.getByRole("button", { name: "Load example" }));
    expect((screen.getByLabelText(/DESIGN\.md content/) as HTMLTextAreaElement).value).toContain(
      "# My Brand Design System",
    );
    expect(screen.queryByRole("button", { name: "Load example" })).not.toBeInTheDocument();
  });

  it("validates each field and clears the error on edit", async () => {
    const { user, onSave } = setup();
    const save = screen.getByRole("button", { name: "Add design system" });

    await user.click(save);
    expect(screen.getByText("Give your design system a name.")).toBeInTheDocument();

    await user.type(screen.getByLabelText(/Name/), "Acme");
    expect(screen.queryByText("Give your design system a name.")).not.toBeInTheDocument();

    await user.click(save);
    expect(screen.getByText("Paste your DESIGN.md content.")).toBeInTheDocument();

    await user.type(screen.getByLabelText(/DESIGN\.md content/), "short");
    await user.click(save);
    expect(screen.getByText(/Content is too short/)).toBeInTheDocument();
    expect(onSave).not.toHaveBeenCalled();
  });

  it("rejects an over-long body", async () => {
    const { user, onSave } = setup({
      existing: { ...sample, body: "y".repeat(80_001) },
    });
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    expect(screen.getByText(/Content is too long/)).toBeInTheDocument();
    expect(onSave).not.toHaveBeenCalled();
  });

  it("rejects an over-long name (when prefilled past maxLength)", async () => {
    const { user, onSave } = setup({
      existing: { ...sample, name: "n".repeat(61) },
    });
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    expect(screen.getByText("Name must be 60 characters or fewer.")).toBeInTheDocument();
    expect(onSave).not.toHaveBeenCalled();
  });

  it("saves a new system with a slugged id and current timestamp", async () => {
    vi.spyOn(Date, "now").mockReturnValue(999);
    const { user, onSave } = setup();
    await user.type(screen.getByLabelText(/Name/), "  My Cool Brand! ");
    await user.click(screen.getByRole("button", { name: "Load example" }));
    await user.click(screen.getByRole("button", { name: "Add design system" }));
    expect(onSave).toHaveBeenCalledTimes(1);
    const saved = onSave.mock.calls[0][0] as CustomDesignSystem;
    expect(saved).toMatchObject({ id: "custom:my-cool-brand", name: "My Cool Brand!", createdAt: 999 });
    expect(saved.body).toContain("# My Brand Design System");
  });

  it("preserves createdAt when editing", async () => {
    const { user, onSave } = setup({ existing: sample });
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    expect(onSave).toHaveBeenCalledWith(sample);
  });

  it("closes via Cancel, X button, Escape and backdrop click", async () => {
    const { user, onClose } = setup();
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onClose).toHaveBeenCalledTimes(1);

    const buttons = screen.getAllByRole("button");
    await user.click(buttons[0]);
    expect(onClose).toHaveBeenCalledTimes(2);

    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledTimes(3);

    await user.keyboard("a");
    expect(onClose).toHaveBeenCalledTimes(3);

    await user.click(screen.getByRole("dialog"));
    expect(onClose).toHaveBeenCalledTimes(4);

    await user.click(screen.getByLabelText(/Name/));
    expect(onClose).toHaveBeenCalledTimes(4);
  });

  it("locks body scroll while mounted and restores it on unmount", () => {
    document.body.style.overflow = "auto";
    const onClose = vi.fn();
    const { unmount } = render(<CustomDesignSystemModal onSave={vi.fn()} onClose={onClose} />);
    expect(document.body.style.overflow).toBe("hidden");
    unmount();
    expect(document.body.style.overflow).toBe("auto");
    document.body.style.overflow = "";
  });

  it("removes the Escape listener on unmount", async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    const { unmount } = render(<CustomDesignSystemModal onSave={vi.fn()} onClose={onClose} />);
    unmount();
    await user.keyboard("{Escape}");
    expect(onClose).not.toHaveBeenCalled();
  });
});
