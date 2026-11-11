import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { CONNECTOR_STATUSES } from "@/types/connectors";
import { ConnectorStatusBadge } from "./ConnectorStatusBadge";

describe("ConnectorStatusBadge", () => {
  it.each([
    ["connected", "Connected"],
    ["not_connected", "Not connected"],
    ["expired", "Expired"],
    ["not_configured", "Not configured"],
  ] as const)("shows the text %s -> %s", (status, text) => {
    render(<ConnectorStatusBadge status={status} />);
    expect(screen.getByText(text)).toBeInTheDocument();
  });

  it("hides the decorative icon from assistive technology for every status", () => {
    for (const status of CONNECTOR_STATUSES) {
      const { container, unmount } = render(<ConnectorStatusBadge status={status} />);
      expect(container.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
      unmount();
    }
  });
});
