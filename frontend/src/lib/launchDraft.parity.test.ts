/**
 * ⭐ THE BINDING LAUNCH-CONTRACT PARITY GATE (plan 37-07).
 *
 * The retired route-split flow (prototype/templates + ppt/templates pages) is
 * the ORACLE. Its exact sessionStorage hand-off is frozen in the golden
 * fixtures (launchContract.ts), captured from the real pages by the transitional
 * launchContract.oracle test. This suite proves the unified LaunchWizard's
 * serialization — `buildLaunchDraft` / `buildDiscoveryValue` — reproduces those
 * goldens BYTE-FOR-BYTE, per mode. If this is green, the unified page writes the
 * identical draft/pending/discovery contract the dashboard already consumes.
 */

import { describe, it, expect } from "vitest";
import { buildLaunchDraft, buildDiscoveryValue } from "./launchDraft";
import { DRAFT_SCENARIOS, DISCOVERY_SCENARIOS } from "@/components/workflow/__fixtures__/launchContract";

describe("launch-contract parity — buildLaunchDraft is byte-identical to the retired flow (per mode)", () => {
  for (const scenario of DRAFT_SCENARIOS) {
    it(scenario.name, () => {
      const out = buildLaunchDraft(scenario.mode, scenario.inputs);
      expect(out.draftKey).toBe(scenario.expected.draftKey);
      expect(out.pendingKey).toBe(scenario.expected.pendingKey);
      // Byte-identity of the serialized draft — the load-bearing assertion.
      expect(out.draftJson).toBe(scenario.expected.draftJson);
    });
  }

  it("keys the ONLY mode-difference on the storage-key pair (SC-001)", () => {
    const proto = buildLaunchDraft("prototype", { templateId: "t", designSystemId: "d", brief: "b", agentIds: [] });
    const ppt = buildLaunchDraft("ppt", { templateId: "t", designSystemId: "d", brief: "b", agentIds: [] });
    // Same inputs → identical serialized SHAPE; only the keys differ by mode.
    expect(proto.draftJson).toBe(ppt.draftJson);
    expect(proto.draftKey).toBe("prototype.draft");
    expect(ppt.draftKey).toBe("ppt.draft");
    expect(proto.pendingKey).toBe("od_prototype.pending");
    expect(ppt.pendingKey).toBe("od_ppt.pending");
  });
});

describe("launch-contract parity — prototype discovery hand-off is byte-identical", () => {
  for (const scenario of DISCOVERY_SCENARIOS) {
    it(scenario.name, () => {
      expect(buildDiscoveryValue(scenario.answers)).toBe(scenario.expected);
    });
  }
});
