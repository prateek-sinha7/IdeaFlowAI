import { describe, expect, it } from "vitest";
import { baseWorkflowType } from "./workflowChaining";
import type { WorkflowType } from "@/types/index";

// ─────────────────────────────────────────────────────────────────
// baseWorkflowType
//
// The ACTUAL chaining eligibility/target logic (formerly CHAIN_OPTIONS /
// CHAINABLE_FROM_TYPES / canChainFrom / availableChainTargets, tested in this
// file) is now backend-owned (Plan 34-01) — every workflow authors its own
// `chained_from` consent list, exposed via GET /api/workflows and consumed
// through `useWorkflowChaining()` / `selectChainIntoIndex`
// (store/slices/globalSlice.ts). That logic is a Redux selector now, not a
// pure function this file can unit-test in isolation — its coverage lives
// with the selector/hook tests instead. This file only tests what's still
// genuinely static/frontend-only.
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

  it("leaves a retired label alone — there is nothing left to map", () => {
    // Was "maps od_prototype to prototype". The label was collapsed onto
    // prototype everywhere (registry alias table, manifests, entitlements, and
    // the persisted rows), so this normaliser has no special case to apply and
    // the generic _revision strip is its whole job.
    expect(baseWorkflowType("od_prototype")).toBe("od_prototype");
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
