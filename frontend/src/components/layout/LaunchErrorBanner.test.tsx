import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { LaunchErrorBanner } from "./LaunchErrorBanner";

describe("LaunchErrorBanner", () => {
  it("announces the message as an alert", () => {
    render(<LaunchErrorBanner message="The attached documents did not reach the server." onDismiss={vi.fn()} />);

    expect(screen.getByRole("alert")).toHaveTextContent("The attached documents did not reach the server.");
  });

  it("calls onDismiss from the labelled dismiss button", async () => {
    const onDismiss = vi.fn();
    const user = userEvent.setup();
    render(<LaunchErrorBanner message="x" onDismiss={onDismiss} />);

    await user.click(screen.getByRole("button", { name: "Dismiss" }));

    expect(onDismiss).toHaveBeenCalledTimes(1);
  });
});
