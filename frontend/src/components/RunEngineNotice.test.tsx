/**
 * RunEngineNotice — gap-closing tests (IMPROVE COVERAGE).
 * Complements the legacy suite in `__tests__/RunEngineNotice.test.tsx`:
 * keyboard + close toggling, region reachability, icon variant, support vs
 * non-support action rendering, className passthrough, default export.
 */

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import DefaultRunEngineNotice, { RunEngineNotice } from "./RunEngineNotice";

describe("RunEngineNotice details toggle", () => {
  it("opens and closes the detail region on click, flipping aria-expanded and label", async () => {
    const user = userEvent.setup();
    render(<RunEngineNotice type="chain_unavailable" reasonCode="source_running" />);

    const toggle = screen.getByRole("button", { name: "Show details" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("region")).not.toBeInTheDocument();

    await user.click(toggle);
    const openToggle = screen.getByRole("button", { name: "Hide details" });
    expect(openToggle).toHaveAttribute("aria-expanded", "true");
    const region = screen.getByRole("region", { name: "Hide details" });
    expect(region).toHaveAttribute("id", openToggle.getAttribute("aria-controls")!);
    expect(region).toHaveTextContent(/must finish before its output can be used as context/i);

    await user.click(openToggle);
    expect(screen.getByRole("button", { name: "Show details" })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
    expect(screen.queryByRole("region")).not.toBeInTheDocument();
  });

  it.each([
    ["Enter", "{Enter}"],
    ["Space", " "],
  ])("toggles via keyboard %s after tabbing to the button", async (_label, key) => {
    const user = userEvent.setup();
    render(<RunEngineNotice type="chain_unavailable" reasonCode="source_not_finalized" />);

    await user.tab();
    const toggle = screen.getByRole("button", { name: "Show details" });
    expect(toggle).toHaveFocus();

    await user.keyboard(key);
    expect(screen.getByRole("button", { name: "Hide details" })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
    expect(screen.getByRole("region")).toBeVisible();

    await user.keyboard(key);
    expect(screen.getByRole("button", { name: "Show details" })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
    expect(screen.queryByRole("region")).not.toBeInTheDocument();
  });
});

describe("RunEngineNotice unknown reason code", () => {
  it("shows the generic headline and keeps the raw code out of the collapsed copy", () => {
    render(<RunEngineNotice type="chain_unavailable" reasonCode="zz_future_code" />);
    expect(screen.getByText("Source context is unavailable")).toBeInTheDocument();
    expect(screen.getByRole("status")).not.toHaveTextContent("zz_future_code");
  });

  it("renders the contact-support action without exposing the raw code when expanded", async () => {
    const user = userEvent.setup();
    render(<RunEngineNotice type="chain_unavailable" reasonCode="zz_future_code" />);
    await user.click(screen.getByRole("button", { name: "Show details" }));
    const region = screen.getByRole("region");
    expect(region).toHaveTextContent("Contact support");
    expect(region).not.toHaveTextContent("zz_future_code");
  });
});

describe("RunEngineNotice finalization_failed", () => {
  it("keeps the reason code out of the collapsed copy", () => {
    render(<RunEngineNotice type="finalization_failed" reasonCode="db_write_failure" />);
    expect(screen.getByText("Run finalization encountered an issue")).toBeInTheDocument();
    expect(screen.getByRole("status")).not.toHaveTextContent("db_write_failure");
  });

  it("surfaces the reason code only inside the expanded contact-support label", async () => {
    const user = userEvent.setup();
    render(<RunEngineNotice type="finalization_failed" reasonCode="db_write_failure" />);
    await user.click(screen.getByRole("button", { name: "Show details" }));
    expect(screen.getByText("Contact support (db_write_failure)")).toBeInTheDocument();
  });

  it("falls back to 'unknown' in the action label when reasonCode is omitted", async () => {
    const user = userEvent.setup();
    render(<RunEngineNotice type="finalization_failed" />);
    await user.click(screen.getByRole("button", { name: "Show details" }));
    expect(screen.getByText("Contact support (unknown)")).toBeInTheDocument();
  });

  it("falls back to 'unknown' in the action label when reasonCode is empty", async () => {
    const user = userEvent.setup();
    render(<RunEngineNotice type="finalization_failed" reasonCode="" />);
    await user.click(screen.getByRole("button", { name: "Show details" }));
    expect(screen.getByText("Contact support (unknown)")).toBeInTheDocument();
  });
});

describe("RunEngineNotice icon signal", () => {
  it("uses the warning triangle icon for finalization_failed, hidden from assistive tech", () => {
    render(<RunEngineNotice type="finalization_failed" reasonCode="x" />);
    const icon = screen
      .getByTestId("run-engine-notice-finalization_failed")
      .querySelector('span[aria-hidden="true"] svg');
    expect(icon).not.toBeNull();
    expect(icon).toHaveClass("lucide-triangle-alert");
  });

  it("uses the info icon for chain_unavailable", () => {
    render(<RunEngineNotice type="chain_unavailable" reasonCode="source_running" />);
    const icon = screen
      .getByTestId("run-engine-notice-chain_unavailable")
      .querySelector('span[aria-hidden="true"] svg');
    expect(icon).not.toBeNull();
    expect(icon).toHaveClass("lucide-info");
  });
});

describe("RunEngineNotice action rendering", () => {
  it("renders a non-support action label in the detail region for choose-source codes", async () => {
    const user = userEvent.setup();
    render(<RunEngineNotice type="chain_unavailable" reasonCode="source_payload_missing" />);
    await user.click(screen.getByRole("button", { name: "Show details" }));
    expect(screen.getByText("Choose a different source")).toBeInTheDocument();
  });

  it("renders the support action label for unsupported_version_combination", async () => {
    const user = userEvent.setup();
    render(
      <RunEngineNotice type="chain_unavailable" reasonCode="unsupported_version_combination" />,
    );
    await user.click(screen.getByRole("button", { name: "Show details" }));
    expect(screen.getByText("Contact support")).toBeInTheDocument();
  });

  it("renders the non-support action as brand-emphasised and support as muted copy", async () => {
    const user = userEvent.setup();
    const { unmount } = render(
      <RunEngineNotice type="chain_unavailable" reasonCode="source_not_finalized" />,
    );
    await user.click(screen.getByRole("button", { name: "Show details" }));
    const retry = screen.getByText("Retry");
    expect(retry).toHaveClass("font-medium");
    unmount();

    render(<RunEngineNotice type="chain_unavailable" reasonCode="zz_unknown" />);
    await user.click(screen.getByRole("button", { name: "Show details" }));
    expect(screen.getByText("Contact support")).not.toHaveClass("font-medium");
  });
});

describe("RunEngineNotice className", () => {
  it("appends a custom className to the status container", () => {
    render(
      <RunEngineNotice type="chain_unavailable" reasonCode="source_running" className="custom-x" />,
    );
    expect(screen.getByRole("status")).toHaveClass("custom-x");
  });

  it("renders without a custom className by default", () => {
    render(<RunEngineNotice type="chain_unavailable" reasonCode="source_running" />);
    expect(screen.getByRole("status")).not.toHaveClass("custom-x");
  });
});

describe("RunEngineNotice default export", () => {
  it("is the same component as the named export", () => {
    expect(DefaultRunEngineNotice).toBe(RunEngineNotice);
  });
});
