/**
 * SURF-01 / SURF-03 / EMP-02 — the embedded capability palette render contract.
 *
 * The palette lives INSIDE `AgentsPopup` (D-01 / Pitfall 1: the standalone
 * `CapabilityPalette.tsx` was DELETED in P18/ISS-014 as an INV-12 dual-impl and
 * must NOT be recreated). It is exported as `CapabilityPaletteSection` so this
 * test can render it in isolation against a fixture `/api/capabilities` payload.
 *
 * These tests pin the SC-001 dividend at the UX layer:
 *   1. Grouped-by-kind rendering — one group header per `kind`, ≥1 row per kind,
 *      the header title-cased from the payload `kind` (NO hardcoded kind list).
 *   2. `user_allowed=false` caps render visible-but-LOCKED (Lock + engineer-only
 *      copy + `aria-disabled="true"`), never user-composable.
 *   3. A fixture-only capability (a name that appears NOWHERE in FE source)
 *      renders → proves there is no hardcoded capability-name array (SC-001).
 *   4. Loading / error / empty states match the AgentModelPicker copy contract.
 *
 * `getCapabilities` (the API fetcher from `lib/api.ts`) is mocked so the palette
 * renders without a real network fetch.
 */

import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { readFileSync } from "node:fs";
import path from "node:path";
import type { CapabilitiesPalette } from "@/lib/api";

const mockGetCapabilities = vi.fn();
vi.mock("@/lib/api", () => ({
  getToken: () => "test-token",
  getCapabilities: (token: string) => mockGetCapabilities(token),
}));

import { CapabilityPaletteSection } from "./AgentsPopup";

// A fixture payload spanning multiple kinds, including:
//  - a `user_allowed=false` cap (the locked-row affordance, EMP-02)
//  - a fixture-only cap name `zzz_fixture_only` that is NOT referenced anywhere
//    in FE source (the SC-001 "no hardcoded list" proof)
const FIXTURE: CapabilitiesPalette = {
  capabilities: [
    {
      kind: "validator",
      name: "code_test",
      user_allowed: true,
      description: "Runs the test suite as a validation gate.",
      security_gated: false,
      config_schema: { command: { type: "string" } },
    },
    {
      kind: "validator",
      name: "zzz_fixture_only",
      user_allowed: true,
      description: "A capability that exists ONLY in this test fixture.",
      security_gated: false,
      config_schema: {},
    },
    {
      kind: "gate",
      name: "security",
      user_allowed: false,
      description: "An engineer-only security gate.",
      security_gated: true,
      config_schema: {},
    },
    {
      kind: "context_provider",
      name: "repo_inventory",
      user_allowed: true,
      description: "Injects a repository inventory into the agent context.",
      security_gated: false,
      config_schema: {},
    },
  ],
  model_catalog: [],
};

describe("CapabilityPaletteSection — SURF-01/03 + EMP-02 render contract", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetCapabilities.mockResolvedValue(FIXTURE);
  });

  it("groups rows by kind with a title-cased header per kind (no hardcoded kind list)", async () => {
    render(<CapabilityPaletteSection />);

    // One group per distinct kind, header title-cased from the payload `kind`.
    await waitFor(() => {
      expect(screen.getByRole("group", { name: "validator" })).toBeInTheDocument();
    });
    expect(screen.getByRole("group", { name: "gate" })).toBeInTheDocument();
    expect(
      screen.getByRole("group", { name: "context_provider" }),
    ).toBeInTheDocument();

    // The header title-cases the kind (e.g. "Context providers" from
    // "context_provider") — derived, not a hardcoded label.
    expect(screen.getByText("Validators")).toBeInTheDocument();
    expect(screen.getByText("Gates")).toBeInTheDocument();
    expect(screen.getByText("Context providers")).toBeInTheDocument();
  });

  it("renders every capability row from the payload, including a fixture-only name (SC-001)", async () => {
    render(<CapabilityPaletteSection />);

    // The fixture-only cap name appears with NO FE source edit → proves the
    // palette renders entirely from the fetched payload (no hardcoded list).
    await waitFor(() => {
      expect(screen.getByText("zzz_fixture_only")).toBeInTheDocument();
    });
    expect(screen.getByText("code_test")).toBeInTheDocument();
    expect(screen.getByText("repo_inventory")).toBeInTheDocument();
    // The registry-sourced description renders as the row body.
    expect(
      screen.getByText("A capability that exists ONLY in this test fixture."),
    ).toBeInTheDocument();
  });

  it("renders a user_allowed=false cap visible-but-LOCKED (engineer-only, aria-disabled)", async () => {
    render(<CapabilityPaletteSection />);

    const lockedRow = await waitFor(() => {
      const row = screen.getByText("security").closest("[data-cap-row]");
      expect(row).not.toBeNull();
      return row as HTMLElement;
    });
    expect(lockedRow).toHaveAttribute("aria-disabled", "true");
    // Engineer-only microcopy per the UI-SPEC copywriting contract.
    expect(screen.getByText("Engineer-only")).toBeInTheDocument();
  });

  it("shows the loading copy while fetching", async () => {
    let resolveFetch: (v: CapabilitiesPalette) => void = () => {};
    mockGetCapabilities.mockReturnValue(
      new Promise<CapabilitiesPalette>((res) => {
        resolveFetch = res;
      }),
    );
    render(<CapabilityPaletteSection />);
    expect(screen.getByText("Loading capabilities…")).toBeInTheDocument();
    resolveFetch(FIXTURE);
    await waitFor(() =>
      expect(screen.queryByText("Loading capabilities…")).not.toBeInTheDocument(),
    );
  });

  it("shows the error copy when the fetch rejects", async () => {
    mockGetCapabilities.mockRejectedValue(new Error("boom"));
    render(<CapabilityPaletteSection />);
    await waitFor(() =>
      expect(screen.getByText("boom")).toBeInTheDocument(),
    );
  });

  it("shows the empty copy when the registry returns no capabilities", async () => {
    mockGetCapabilities.mockResolvedValue({ capabilities: [], model_catalog: [] });
    render(<CapabilityPaletteSection />);
    await waitFor(() =>
      expect(screen.getByText("No capabilities available")).toBeInTheDocument(),
    );
  });

  // SC-001 source-level guard: the palette source carries NO hardcoded
  // capability-name array. This greps the AgentsPopup source for the literal
  // capability-name-array shape the SC-001 gate forbids.
  it("carries no hardcoded capability-name array in the palette source (SC-001)", () => {
    const src = readFileSync(
      path.resolve(__dirname, "./AgentsPopup.tsx"),
      "utf8",
    );
    // The forbidden shape: an inline array literal pairing capability KIND
    // string literals (e.g. ['strategy', ..., 'validator', ...]).
    const hardcodedCapArray =
      /\[[^\]]*('strategy'|"strategy")[^\]]*('validator'|"validator")[^\]]*\]/;
    expect(hardcodedCapArray.test(src)).toBe(false);
  });
});
