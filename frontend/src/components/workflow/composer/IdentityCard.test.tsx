import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { IdentityCard } from "./IdentityCard";

function renderCard(overrides: Partial<React.ComponentProps<typeof IdentityCard>> = {}) {
  const props = {
    name: "My Workflow",
    description: "Produces a report",
    deliverableLabel: "Prototype",
    onNameChange: vi.fn(),
    onDescriptionChange: vi.fn(),
    ...overrides,
  };
  render(<IdentityCard {...props} />);
  return props;
}

describe("IdentityCard", () => {
  it("shows the current name and description in labelled fields", () => {
    renderCard();

    expect(screen.getByLabelText("Name")).toHaveValue("My Workflow");
    expect(screen.getByLabelText("Description")).toHaveValue("Produces a report");
  });

  it("shows placeholders when name and description are empty", () => {
    renderCard({ name: "", description: "" });

    expect(screen.getByPlaceholderText("Name your workflow")).toHaveValue("");
    expect(screen.getByPlaceholderText("What does this workflow produce?")).toHaveValue("");
  });

  it("reports each keystroke in the name field", async () => {
    const user = userEvent.setup();
    const { onNameChange } = renderCard({ name: "" });

    await user.type(screen.getByLabelText("Name"), "Ab");

    expect(onNameChange).toHaveBeenNthCalledWith(1, "A");
    expect(onNameChange).toHaveBeenNthCalledWith(2, "b");
  });

  it("reports each keystroke in the description field", async () => {
    const user = userEvent.setup();
    const { onDescriptionChange } = renderCard({ description: "" });

    await user.type(screen.getByLabelText("Description"), "Hi");

    expect(onDescriptionChange).toHaveBeenNthCalledWith(1, "H");
    expect(onDescriptionChange).toHaveBeenNthCalledWith(2, "i");
  });

  it("shows the deliverable type as a read-only field that has no input", () => {
    const { onNameChange, onDescriptionChange } = renderCard({ deliverableLabel: "Slide deck" });

    const deliverable = screen.getByTestId("composer-deliverable-type");
    expect(deliverable).toHaveTextContent("Slide deck");
    expect(deliverable).toHaveAttribute("aria-readonly", "true");
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(onNameChange).not.toHaveBeenCalled();
    expect(onDescriptionChange).not.toHaveBeenCalled();
  });
});
