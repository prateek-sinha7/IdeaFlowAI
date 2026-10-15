/**
 * ISS-1195 / ISS-1196 / ISS-1197 / ISS-1198 (QA-KB-117) — Deliverable access must be driven
 * by the same catalog list as the home catalog, not a hand-kept display map.
 *
 * Each case asserts the CORRECT behaviour and (the strict it.fails marker was removed after verification:
 * the fix landed).
 */
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "@/test/renderWithProviders";

const mockGetMe = vi.fn();

vi.mock("@/lib/api", () => ({
  getToken: () => "test-token",
  getMe: (t: string) => mockGetMe(t),
  getPreferences: vi.fn().mockResolvedValue({ preferred_model: null, available_models: [] }),
  getCapabilities: vi.fn().mockResolvedValue({ model_catalog: [] }),
  changePassword: vi.fn(),
  updatePreferences: vi.fn(),
  getMfaStatus: vi.fn().mockResolvedValue({
    supported: true, enabled: false, required: false, email_available: true, factors: [],
  }),
  enableEmailMfa: vi.fn(),
  disableEmailMfa: vi.fn(),
  ApiError: class ApiError extends Error {},
}));

const mockRouter = { push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() };
vi.mock("next/navigation", () => ({ useRouter: () => mockRouter }));

import { AccountSettings } from "./AccountSettings";
import { UpgradePlanModal } from "./UpgradePlanModal";

function wf(id: string, display_name: string, is_beta = false) {
  return {
    id, display_name, name: display_name, description: "", step_count: 1, steps: [],
    user_launchable: true, is_beta,
  };
}

const CATALOG = [
  wf("ex_A2_branch", "Branch on a decision"),
  wf("ppt_v2", "Pitch an idea (Depth)"),
  wf("prototype_v2", "Prototype from documents (Depth)"),
  wf("backlog", "Write backlog from prototype and documents"),
  wf("mulesoft_to_springboot", "MuleSoft to Spring Boot", true),
  wf("dotnet_to_azure", ".NET to Azure", true),
];

async function openUsage(tier: string) {
  mockGetMe.mockResolvedValue({ id: "u1", email: "u@example.com", tier });
  renderWithProviders(<AccountSettings onBack={() => {}} />, {
    preloadedState: {
      global: { workflows: CATALOG, workflowsStatus: "succeeded" } as never,
    },
  });
  await waitFor(() => expect(mockGetMe).toHaveBeenCalled());
  await userEvent.click(screen.getByTestId("tab-limits"));
  // Wait for the tier to load (enterprise-only base tile).
  await screen.findByText("Custom Workflow", {}, { timeout: 3000 }).catch(() => undefined);
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ content: "" }) }));
});
afterEach(() => vi.unstubAllGlobals());

describe("QA-KB-117 — Deliverable access agrees with the catalog", () => {
  it("ISS-1195: lists the entitled Engine example 'Branch on a decision' (enterprise)", async () => {
    await openUsage("enterprise");
    expect(await screen.findByText("Branch on a decision", {}, { timeout: 2000 })).toBeInTheDocument();
  });

  it("ISS-1196: lists the catalog's v2 product workflows (enterprise)", async () => {
    await openUsage("enterprise");
    for (const label of [
      "Pitch an idea (Depth)",
      "Prototype from documents (Depth)",
      "Write backlog from prototype and documents",
    ]) {
      expect(await screen.findByText(label, {}, { timeout: 2000 })).toBeInTheDocument();
    }
  });

  it("ISS-1197: does not list Coming Soon (is_beta) workflows as plan access (enterprise)", async () => {
    await openUsage("enterprise");
    // Positive anchor so the case cannot pass vacuously on an empty grid.
    expect(await screen.findByText("Branch on a decision", {}, { timeout: 2000 })).toBeInTheDocument();
    expect(screen.queryByText("Mulesoft Migration")).toBeNull();
    expect(screen.queryByText(".NET Migration")).toBeNull();
  });

  it("ISS-1198: plan modal's 'unlocks N more' counts catalog-enabled rows (pro to enterprise)", async () => {
    renderWithProviders(<UpgradePlanModal tier="pro" onClose={() => {}} />, {
      preloadedState: {
        global: { workflows: [wf("ex_A2_branch", "Branch on a decision")], workflowsStatus: "succeeded" } as never,
      },
    });
    // The only catalog row pro lacks is ex_A2_branch -> exactly 1 more.
    const copy = await screen.findByText(
      (_c, el) => el?.tagName === "P" && /unlocks\s+\d+\s+more deliverable/.test(el.textContent ?? ""),
    );
    expect(copy.textContent).toMatch(/unlocks\s+1\s+more deliverable type\b/);
  });
});
