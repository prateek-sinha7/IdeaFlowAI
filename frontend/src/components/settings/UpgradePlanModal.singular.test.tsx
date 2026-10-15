/**
 * UpgradePlanModal — singular "type" wording.
 *
 * The real entitlement tables never differ by exactly one deliverable, so the
 * "1 more deliverable type" branch needs controlled tier data. Only the static
 * entitlement tables are replaced; the component's counting logic runs for real.
 */

import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "@/test/renderWithProviders";

vi.mock("@/lib/entitlements", () => ({
  TIER_LABELS: { basic: "Basic", pro: "Pro", enterprise: "Enterprise", hexaware: "Hexaware" },
  UPGRADE_PATH: { basic: "pro", pro: "enterprise", enterprise: null, hexaware: "enterprise" },
  TIER_PIPELINES: {
    basic: new Set(["user_stories", "user_stories_revision"]),
    // One new base deliverable (ppt) plus a revision variant that must not count.
    pro: new Set(["user_stories", "user_stories_revision", "ppt", "ppt_revision"]),
    // Three new base deliverables over pro.
    enterprise: new Set(["user_stories", "ppt", "prototype", "app_builder", "custom"]),
    hexaware: new Set(["user_stories"]),
  },
}));

import { UpgradePlanModal } from "./UpgradePlanModal";

describe("UpgradePlanModal — deliverable count wording", () => {
  it("uses the singular 'type' and ignores revision variants when exactly one deliverable is unlocked", () => {
    renderWithProviders(<UpgradePlanModal tier="basic" onClose={() => {}} />);

    expect(screen.getByRole("dialog", { name: "Upgrade your plan" })).toHaveTextContent(
      "The Pro plan unlocks 1 more deliverable type.",
    );
  });

  it("uses the plural 'types' when several deliverables are unlocked", () => {
    renderWithProviders(<UpgradePlanModal tier="pro" onClose={() => {}} />);

    expect(screen.getByRole("dialog", { name: "Upgrade your plan" })).toHaveTextContent(
      "The Enterprise plan unlocks 3 more deliverable types.",
    );
  });
});
