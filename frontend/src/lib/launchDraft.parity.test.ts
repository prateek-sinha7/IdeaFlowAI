/**
 * ⭐ THE BINDING LAUNCH-CONTRACT PARITY GATE (plan 37-07).
 *
 * The retired route-split flow (prototype/templates + ppt/templates pages) was
 * the ORACLE. Its exact sessionStorage hand-off is frozen in the golden
 * fixtures (launchContract.ts), captured from the real pages by a transitional
 * render-oracle test that was retired together with those pages (preserved in
 * git history). This suite proves the unified LaunchWizard's
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
    expect(proto.pendingKey).toBe("prototype.pending");
    expect(ppt.pendingKey).toBe("ppt.pending");
  });
});

describe("ppt_v2 rides the ppt launch pipe without disturbing it (spec 017)", () => {
  const inputs = { templateId: "t", designSystemId: "d", brief: "b", agentIds: [] };

  it("shares ppt's storage-key pair, so the staging effects need no twin", () => {
    const v2 = buildLaunchDraft("ppt_v2", inputs);
    expect(v2.draftKey).toBe("ppt.draft");
    expect(v2.pendingKey).toBe("ppt.pending");
  });

  it("names its pipeline in the draft — the only thing telling the two apart", () => {
    const v2 = JSON.parse(buildLaunchDraft("ppt_v2", inputs).draftJson);
    expect(v2.pipelineType).toBe("ppt_v2");
  });

  it("leaves the ppt and prototype drafts byte-identical (no new key)", () => {
    // The parity goldens above already pin these; this states the reason the
    // pipelineType spread is CONDITIONAL rather than always-present.
    expect(buildLaunchDraft("ppt", inputs).draftJson).not.toContain("pipelineType");
    expect(buildLaunchDraft("prototype", inputs).draftJson).not.toContain("pipelineType");
  });

  it("appends pipelineType LAST, after agentIds", () => {
    const keys = Object.keys(JSON.parse(buildLaunchDraft("ppt_v2", inputs).draftJson));
    expect(keys[keys.length - 1]).toBe("pipelineType");
    expect(keys[keys.length - 2]).toBe("agentIds");
  });
});

describe("launch-contract parity — prototype discovery hand-off is byte-identical", () => {
  for (const scenario of DISCOVERY_SCENARIOS) {
    it(scenario.name, () => {
      expect(buildDiscoveryValue(scenario.answers)).toBe(scenario.expected);
    });
  }
});
