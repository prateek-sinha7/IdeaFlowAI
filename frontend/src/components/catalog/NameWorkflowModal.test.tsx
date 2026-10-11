import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { NameWorkflowModal } from "./NameWorkflowModal";

function setup(props: Partial<React.ComponentProps<typeof NameWorkflowModal>> = {}) {
  const onSave = vi.fn();
  const onCancel = vi.fn();
  render(<NameWorkflowModal onSave={onSave} onCancel={onCancel} {...props} />);
  return { onSave, onCancel };
}

describe("NameWorkflowModal", () => {
  it("renders default title, empty fields and focuses the name input", () => {
    setup();
    expect(screen.getByRole("heading", { name: "Save workflow" })).toBeInTheDocument();
    const name = screen.getByLabelText("Workflow name");
    expect(name).toHaveValue("");
    expect(name).toHaveFocus();
    expect(screen.getByLabelText(/Description/)).toHaveValue("");
  });

  it("renders custom title and initial values", () => {
    setup({ title: "Rename workflow", initialName: "Alpha", initialDescription: "Desc" });
    expect(screen.getByRole("heading", { name: "Rename workflow" })).toBeInTheDocument();
    expect(screen.getByLabelText("Workflow name")).toHaveValue("Alpha");
    expect(screen.getByLabelText(/Description/)).toHaveValue("Desc");
  });

  it("disables Save when the name is empty", () => {
    setup();
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  });

  it("disables Save when the name is whitespace only", async () => {
    const user = userEvent.setup();
    setup();
    await user.type(screen.getByLabelText("Workflow name"), "   ");
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  });

  it("enables Save once a name is typed", async () => {
    const user = userEvent.setup();
    setup();
    await user.type(screen.getByLabelText("Workflow name"), "x");
    expect(screen.getByRole("button", { name: "Save" })).toBeEnabled();
  });

  it("calls onSave with trimmed name and description", async () => {
    const user = userEvent.setup();
    const { onSave } = setup();
    await user.type(screen.getByLabelText("Workflow name"), "  My flow  ");
    await user.type(screen.getByLabelText(/Description/), "  does things ");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(onSave).toHaveBeenCalledTimes(1);
    expect(onSave).toHaveBeenCalledWith("My flow", "does things");
  });

  it("does not call onSave when Save is clicked while name is blank", async () => {
    const user = userEvent.setup();
    const { onSave } = setup();
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(onSave).not.toHaveBeenCalled();
  });

  it("calls onCancel when Cancel is clicked", async () => {
    const user = userEvent.setup();
    const { onCancel, onSave } = setup({ initialName: "A" });
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(onSave).not.toHaveBeenCalled();
  });

  it("calls onCancel when the backdrop is clicked but not when the card is clicked", async () => {
    const user = userEvent.setup();
    const { onCancel } = setup();
    await user.click(screen.getByRole("heading", { name: "Save workflow" }));
    expect(onCancel).not.toHaveBeenCalled();
    const backdrop = screen.getByRole("heading").closest(".fixed") as HTMLElement;
    await user.click(backdrop);
    expect(onCancel).toHaveBeenCalledTimes(1);
  });
});
