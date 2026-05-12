import { describe, expect, it } from "vitest";
import {
  availableChainTargets,
  baseWorkflowType,
  canChainFrom,
  CHAIN_OPTIONS,
  CHAINABLE_FROM_TYPES,
} from "./workflowChaining";
import type { WorkflowType } from "@/types/index";

// ─────────────────────────────────────────────────────────────────
// baseWorkflowType
// ─────────────────────────────────────────────────────────────────

describe("baseWorkflowType", () => {
  it("strips the _revision suffix", () => {
    expect(baseWorkflowType("ppt_revision")).toBe("ppt");
    expect(baseWorkflowType("user_stories_revision")).toBe("user_stories");
    expect(baseWorkflowType("prototype_revision")).toBe("prototype");
    expect(baseWorkflowType("app_builder_revision")).toBe("app_builder");
  });

  it("leaves base types untouched", () => {
    expect(baseWorkflowType("ppt")).toBe("ppt");
    expect(baseWorkflowType("user_stories")).toBe("user_stories");
    expect(baseWorkflowType("custom")).toBe("custom");
    expect(baseWorkflowType("migration")).toBe("migration");
    expect(baseWorkflowType("mulesoft_to_springboot")).toBe("mulesoft_to_springboot");
    expect(baseWorkflowType("dotnet_to_azure")).toBe("dotnet_to_azure");
  });

  it("does not match `_revision` in the middle of a string", () => {
    // Defensive — keeps a future type like `revision_request_foo` safe.
    expect(baseWorkflowType("user_stories_revision" as WorkflowType)).toBe("user_stories");
    // Sanity check: a hypothetical future name with `revision` embedded
    // mid-string would not be stripped.
    expect(baseWorkflowType("revision_workflow" as unknown as WorkflowType)).toBe(
      "revision_workflow",
    );
  });
});

// ─────────────────────────────────────────────────────────────────
// canChainFrom
// ─────────────────────────────────────────────────────────────────

describe("canChainFrom", () => {
  it("accepts every base deliverable", () => {
    expect(canChainFrom("ppt")).toBe(true);
    expect(canChainFrom("user_stories")).toBe(true);
    expect(canChainFrom("prototype")).toBe(true);
    expect(canChainFrom("app_builder")).toBe(true);
  });

  it("accepts every revision form (the refine bug fix)", () => {
    expect(canChainFrom("ppt_revision")).toBe(true);
    expect(canChainFrom("user_stories_revision")).toBe(true);
    expect(canChainFrom("prototype_revision")).toBe(true);
    expect(canChainFrom("app_builder_revision")).toBe(true);
  });

  it("rejects migration meta-type and its sub-types", () => {
    expect(canChainFrom("migration")).toBe(false);
    expect(canChainFrom("mulesoft_to_springboot")).toBe(false);
    expect(canChainFrom("dotnet_to_azure")).toBe(false);
  });

  it("rejects custom", () => {
    expect(canChainFrom("custom")).toBe(false);
  });
});

// ─────────────────────────────────────────────────────────────────
// availableChainTargets
// ─────────────────────────────────────────────────────────────────

describe("availableChainTargets", () => {
  it("removes the current workflow type from the options", () => {
    const targets = availableChainTargets("ppt");
    expect(targets.map((t) => t.type)).toEqual(["user_stories", "prototype"]);
  });

  it("removes the base form when given a revision (refine -> chain bug)", () => {
    // The chief bug this guards: a ppt_revision completing should not
    // offer "Presentation" as a next step.
    const targets = availableChainTargets("ppt_revision");
    expect(targets.map((t) => t.type)).not.toContain("ppt");
    expect(targets.map((t) => t.type)).toEqual(["user_stories", "prototype"]);
  });

  it("removes everything in completedTypes too", () => {
    const targets = availableChainTargets("ppt", ["user_stories"]);
    expect(targets.map((t) => t.type)).toEqual(["prototype"]);
  });

  it("collapses revision and base completions when computing exclusions", () => {
    // The user already ran a PPT, then opened it and did a revision.
    // Both should count as "PPT done" and the chain should offer the
    // remaining two, not double-list PPT once and skip it once.
    const targets = availableChainTargets("user_stories", [
      "ppt",
      "ppt_revision",
    ]);
    expect(targets.map((t) => t.type)).toEqual(["prototype"]);
  });

  it("returns an empty list when every base has been done", () => {
    const targets = availableChainTargets("ppt", ["user_stories", "prototype"]);
    expect(targets).toEqual([]);
  });

  it("works when called with a non-chainable workflow type", () => {
    // canChainFrom() gates this in the UI, but the function itself
    // shouldn't blow up — it should just return CHAIN_OPTIONS minus
    // any base-form match. Migration's base is "migration" which is
    // never in CHAIN_OPTIONS, so we get all three.
    const targets = availableChainTargets("migration");
    expect(targets.map((t) => t.type)).toEqual(["ppt", "user_stories", "prototype"]);
  });

  it("preserves the canonical option order", () => {
    // Order matters for UX consistency — the panel should show targets
    // in the same order every time.
    const targets = availableChainTargets("app_builder");
    expect(targets.map((t) => t.type)).toEqual(["ppt", "user_stories", "prototype"]);
  });

  it("returns ChainOption objects with label and description", () => {
    const [first] = availableChainTargets("user_stories");
    expect(first).toMatchObject({
      type: "ppt",
      label: "Presentation",
      description: expect.any(String),
    });
  });
});

// ─────────────────────────────────────────────────────────────────
// Constants integrity (pin shape)
// ─────────────────────────────────────────────────────────────────

describe("CHAIN_OPTIONS / CHAINABLE_FROM_TYPES integrity", () => {
  it("CHAIN_OPTIONS only contains base (non-revision) types", () => {
    for (const opt of CHAIN_OPTIONS) {
      expect(opt.type).not.toMatch(/_revision$/);
    }
  });

  it("every CHAIN_OPTIONS entry has its base form in CHAINABLE_FROM_TYPES", () => {
    // Any target you can chain TO must also be chainable FROM (its base
    // form is in the from-set). Catches the case where someone adds a
    // new option but forgets to allow chaining back out of it.
    for (const opt of CHAIN_OPTIONS) {
      expect(CHAINABLE_FROM_TYPES.has(opt.type)).toBe(true);
    }
  });
});
