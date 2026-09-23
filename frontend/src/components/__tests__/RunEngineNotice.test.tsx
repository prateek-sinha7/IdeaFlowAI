/**
 * RunEngineNotice — Requirement 20 AC 5 accessibility contract and reason-code
 * matrix (Task 11.9, sandbox-git-versioning-v2).
 *
 * Covers:
 *  - Both event types (chain_unavailable + finalization_failed)
 *  - All 5 chain-unavailable reason codes + 2 mixed-deploy codes
 *  - Unknown / undefined reason code falls back to generic message ("contact support")
 *  - Accessible pattern: role="status" aria-live="polite", non-color-only icon,
 *    keyboard-reachable detail toggle with aria-expanded, programmatically
 *    associated panel (aria-controls)
 *  - Correct next-action per reason code (Req 20 AC 4)
 *  - Never renders an internal ref string or raw reason code in visible copy
 */

import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { RunEngineNotice } from "../RunEngineNotice";

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────

function setup(props: React.ComponentProps<typeof RunEngineNotice>) {
  render(<RunEngineNotice {...props} />);
}

function openDetail() {
  const btn = screen.getByRole("button", { name: /show details|hide details/i });
  fireEvent.click(btn);
  return btn;
}

// ─────────────────────────────────────────────────────────────────────────────
// A11y contract (Req 20 AC 5)
// ─────────────────────────────────────────────────────────────────────────────

describe("RunEngineNotice — accessibility contract", () => {
  it("renders with role=status and aria-live=polite", () => {
    setup({ type: "chain_unavailable", reasonCode: "source_running" });
    const notice = screen.getByRole("status");
    expect(notice).toBeInTheDocument();
    expect(notice).toHaveAttribute("aria-live", "polite");
    expect(notice).toHaveAttribute("aria-atomic", "true");
  });

  it("carries data-testid driven by type for targeted assertions", () => {
    setup({ type: "chain_unavailable", reasonCode: "source_running" });
    expect(screen.getByTestId("run-engine-notice-chain_unavailable")).toBeInTheDocument();
  });

  it("detail toggle is keyboard-reachable (has role=button)", () => {
    setup({ type: "chain_unavailable", reasonCode: "source_running" });
    expect(screen.getByRole("button", { name: /show details/i })).toBeInTheDocument();
  });

  it("detail toggle starts collapsed (aria-expanded=false)", () => {
    setup({ type: "chain_unavailable", reasonCode: "source_running" });
    const btn = screen.getByRole("button", { name: /show details/i });
    expect(btn).toHaveAttribute("aria-expanded", "false");
  });

  it("detail toggle expands the panel (aria-expanded=true)", () => {
    setup({ type: "chain_unavailable", reasonCode: "source_running" });
    const btn = openDetail();
    expect(btn).toHaveAttribute("aria-expanded", "true");
  });

  it("detail panel is programmatically associated via aria-controls", () => {
    setup({ type: "chain_unavailable", reasonCode: "source_running" });
    const btn = openDetail();
    const panelId = btn.getAttribute("aria-controls");
    expect(panelId).toBeTruthy();
    expect(document.getElementById(panelId!)).toBeInTheDocument();
  });

  it("headline is always visible — non-color-only signal", () => {
    setup({ type: "chain_unavailable", reasonCode: "source_running" });
    // Headline renders without opening detail panel
    expect(screen.getByText(/source run is still in progress/i)).toBeInTheDocument();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// chain_context_unavailable — all 5 bounded reason codes
// ─────────────────────────────────────────────────────────────────────────────

describe("RunEngineNotice type=chain_unavailable", () => {
  it("source_running — headline + retry-later action", () => {
    setup({ type: "chain_unavailable", reasonCode: "source_running" });
    expect(screen.getByText(/source run is still in progress/i)).toBeInTheDocument();
    openDetail();
    expect(screen.getAllByText(/retry later/i).length).toBeGreaterThanOrEqual(1);
  });

  it("source_not_finalized — headline + retry action", () => {
    setup({ type: "chain_unavailable", reasonCode: "source_not_finalized" });
    expect(screen.getByText(/source run output is not yet ready/i)).toBeInTheDocument();
    openDetail();
    // The action label is exactly "Retry" — use exact match to avoid matching "Retry in a moment" in the detail text
    expect(screen.getByText(/^retry$/i)).toBeInTheDocument();
  });

  it("source_non_chainable — headline + choose-different-source action", () => {
    setup({ type: "chain_unavailable", reasonCode: "source_non_chainable" });
    expect(screen.getByText(/source run cannot be used as context/i)).toBeInTheDocument();
    openDetail();
    // Exact label text (appears as the action, vs partial match in detail text)
    expect(screen.getAllByText(/choose a different source/i).length).toBeGreaterThanOrEqual(1);
  });

  it("source_payload_missing — headline + choose-different-source action", () => {
    setup({ type: "chain_unavailable", reasonCode: "source_payload_missing" });
    expect(screen.getByText(/source run output is unavailable/i)).toBeInTheDocument();
    openDetail();
    expect(screen.getAllByText(/choose a different source/i).length).toBeGreaterThanOrEqual(1);
  });

  it("source_provenance_conflict — headline + choose-different-source action", () => {
    setup({ type: "chain_unavailable", reasonCode: "source_provenance_conflict" });
    expect(screen.getByText(/provenance could not be verified/i)).toBeInTheDocument();
    openDetail();
    expect(screen.getAllByText(/choose a different source/i).length).toBeGreaterThanOrEqual(1);
  });

  it("incompatible_backend (mixed-deploy) — retry-later action", () => {
    setup({ type: "chain_unavailable", reasonCode: "incompatible_backend" });
    expect(screen.getByText(/backend version mismatch/i)).toBeInTheDocument();
    openDetail();
    expect(screen.getAllByText(/wait for backend upgrade/i).length).toBeGreaterThanOrEqual(1);
  });

  it("unsupported_version_combination — contact-support action", () => {
    setup({ type: "chain_unavailable", reasonCode: "unsupported_version_combination" });
    expect(screen.getByText(/unsupported version combination/i)).toBeInTheDocument();
    openDetail();
    expect(screen.getAllByText(/contact support/i).length).toBeGreaterThanOrEqual(1);
  });

  it("unknown reason code falls back to generic — never renders raw code", () => {
    const unknownCode = "some_future_backend_code_xyz";
    setup({ type: "chain_unavailable", reasonCode: unknownCode });
    // Generic headline — not the raw code
    expect(screen.getByText(/source context is unavailable/i)).toBeInTheDocument();
    // Raw code must NOT appear in user-facing copy (may appear in detail panel for support)
    // — the component's contract is that the headline is generic
    const notice = screen.getByRole("status");
    // Headline text does not contain the raw unknown code
    const headline = notice.querySelector("p");
    expect(headline?.textContent).not.toContain(unknownCode);
  });

  it("undefined reason code falls back to generic message", () => {
    setup({ type: "chain_unavailable" });
    expect(screen.getByText(/source context is unavailable/i)).toBeInTheDocument();
  });

  it("never offers an action the server refuses — retry action is not present for source_non_chainable", () => {
    setup({ type: "chain_unavailable", reasonCode: "source_non_chainable" });
    openDetail();
    // Should NOT offer standalone "Retry" button — the server will refuse it
    // The action label is "Choose a different source", not "Retry"
    // Verify there's no standalone "Retry" label (only action text, not partial matches in detail)
    const retryActionLabels = screen.queryAllByText(/^retry$/i);
    expect(retryActionLabels.length).toBe(0);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// run_finalization_failed
// ─────────────────────────────────────────────────────────────────────────────

describe("RunEngineNotice type=finalization_failed", () => {
  it("renders the finalization-failure headline", () => {
    setup({ type: "finalization_failed", reasonCode: "db_write_failure" });
    expect(screen.getByText(/run finalization encountered an issue/i)).toBeInTheDocument();
  });

  it("exposes the reason code in the detail panel for support — not in headline", () => {
    const code = "db_write_failure";
    setup({ type: "finalization_failed", reasonCode: code });
    // Headline should be the generic message
    expect(screen.getByText(/run finalization encountered an issue/i)).toBeInTheDocument();
    openDetail();
    // Reason code surfaces inside the detail panel (action label) for support
    expect(screen.getByText(new RegExp(code, "i"))).toBeInTheDocument();
  });

  it("finalization_failed has distinct data-testid from chain_unavailable", () => {
    const { rerender } = render(
      <RunEngineNotice type="finalization_failed" reasonCode="x" />,
    );
    expect(screen.getByTestId("run-engine-notice-finalization_failed")).toBeInTheDocument();
    rerender(<RunEngineNotice type="chain_unavailable" reasonCode="source_running" />);
    expect(screen.getByTestId("run-engine-notice-chain_unavailable")).toBeInTheDocument();
  });

  it("contact-support action is rendered for finalization_failed", () => {
    setup({ type: "finalization_failed", reasonCode: "unknown" });
    openDetail();
    // "Contact support" appears in both detail text and action label — verify at least one
    expect(screen.getAllByText(/contact support/i).length).toBeGreaterThanOrEqual(1);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Reconnect rendering (Req 20 AC 9 frontend half — component survives remount)
// ─────────────────────────────────────────────────────────────────────────────

describe("RunEngineNotice — reconnect visibility", () => {
  it("remains visible after remount (simulates reconnect re-render)", () => {
    const { unmount } = render(
      <RunEngineNotice type="chain_unavailable" reasonCode="source_not_finalized" />,
    );
    unmount();
    // Re-mount simulates a reconnect re-render from the durable projection
    render(<RunEngineNotice type="chain_unavailable" reasonCode="source_not_finalized" />);
    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(screen.getByText(/source run output is not yet ready/i)).toBeInTheDocument();
  });

  it("both event types render after remount", () => {
    const { unmount: u1 } = render(
      <RunEngineNotice type="chain_unavailable" reasonCode="source_non_chainable" />,
    );
    u1();
    render(<RunEngineNotice type="finalization_failed" reasonCode="db" />);
    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(screen.getByText(/run finalization encountered an issue/i)).toBeInTheDocument();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Five distinct reason codes round-trip (Req 20 AC 3)
// ─────────────────────────────────────────────────────────────────────────────

describe("RunEngineNotice — five reason codes are distinct", () => {
  const CODES = [
    "source_running",
    "source_not_finalized",
    "source_non_chainable",
    "source_payload_missing",
    "source_provenance_conflict",
  ] as const;

  it("each code produces a distinct headline", () => {
    const headlines = CODES.map((code) => {
      const { container, unmount } = render(
        <RunEngineNotice type="chain_unavailable" reasonCode={code} />,
      );
      const h = container.querySelector("p")?.textContent ?? "";
      unmount();
      return h;
    });
    const unique = new Set(headlines);
    expect(unique.size).toBe(CODES.length);
  });
});
