import { describe, expect, it } from "vitest";
import globalReducer, { globalCleared, selectChainIntoIndex } from "./globalSlice";
import type { WorkflowSummary } from "@/store/api/workflows";
import type { RootState } from "@/store";
import type { WorkflowRun } from "@/types/index";

// ─────────────────────────────────────────────────────────────────
// selectChainIntoIndex (Plan 34-01)
//
// The backend authors ONLY `chained_from` per workflow (a target's own
// consent list). This selector inverts that once, memoized, into "what can
// workflow X chain INTO" — the reverse view `useWorkflowChaining()` reads.
// Tested directly against a minimal state shape rather than through a live
// store, since the selector's whole job is a pure function of
// `state.global.workflows`.
// ─────────────────────────────────────────────────────────────────

function makeState(workflows: WorkflowSummary[]): RootState {
  return { global: { workflows } } as unknown as RootState;
}

function makeWorkflow(overrides: Partial<WorkflowSummary> & { id: string }): WorkflowSummary {
  return {
    name: overrides.id,
    description: "",
    step_count: 0,
    steps: [],
    user_launchable: true,
    chained_from: [],
    ...overrides,
  } as WorkflowSummary;
}

describe("selectChainIntoIndex", () => {
  it("inverts chained_from into chain-into entries on the source", () => {
    const state = makeState([
      makeWorkflow({ id: "prototype", name: "Prototype", chained_from: [{ id: "user_stories", beta: false, text: "Build prototype" }, { id: "ppt", beta: false, text: "Build prototype" }] }),
      makeWorkflow({ id: "user_stories", name: "User Stories", chained_from: [{ id: "prototype", beta: false, text: "Refine stories" }, { id: "ppt", beta: false, text: "Refine stories" }] }),
      makeWorkflow({ id: "ppt", name: "Presentation", chained_from: [{ id: "prototype", beta: false, text: "Ship the deck" }, { id: "user_stories", beta: false, text: "Ship the deck" }] }),
    ]);
    const index = selectChainIntoIndex(state);

    // index.prototype: workflows that can chain INTO prototype
    // user_stories lists prototype in its chained_from with text "Refine stories"
    // ppt lists prototype in its chained_from with text "Ship the deck"
    expect(index.prototype).toEqual(
      expect.arrayContaining([
        { id: "user_stories", label: "User Stories", beta: false, text: "Refine stories" },
        { id: "ppt", label: "Presentation", beta: false, text: "Ship the deck", wizard_path: "/workflow/create?mode=ppt" },
      ]),
    );
    // index.user_stories: workflows that can chain INTO user_stories
    // prototype lists user_stories in its chained_from with text "Build prototype"
    // ppt lists user_stories in its chained_from with text "Ship the deck"
    expect(index.user_stories).toEqual(
      expect.arrayContaining([
        { id: "prototype", label: "Prototype", beta: false, text: "Build prototype", wizard_path: "/workflow/create?mode=prototype" },
        { id: "ppt", label: "Presentation", beta: false, text: "Ship the deck", wizard_path: "/workflow/create?mode=ppt" },
      ]),
    );
  });

  it("carries the edge-level beta override from chained_from onto the derived entry", () => {
    const state = makeState([
      makeWorkflow({ id: "app_builder", name: "App Builder", is_beta: false, chained_from: [{ id: "prototype", beta: true, text: "Ship the code" }] }),
      makeWorkflow({ id: "prototype", name: "Prototype", chained_from: [] }),
    ]);
    const index = selectChainIntoIndex(state);

    expect(index.prototype).toEqual([{ id: "app_builder", label: "App Builder", beta: true, text: "Ship the code" }]);
  });


  it("a workflow that authors no chained_from produces no entries for anyone", () => {
    const state = makeState([
      makeWorkflow({ id: "chat", chained_from: [] }),
      makeWorkflow({ id: "prototype", chained_from: [] }),
    ]);
    const index = selectChainIntoIndex(state);
    expect(index.prototype).toBeUndefined();
    expect(index.chat).toBeUndefined();
  });
});

// ─────────────────────────────────────────────────────────────────
// QA-PS-035/036/038/041/046: the signedIn preload no longer fetches recent
// runs; HomeLaunchGrid does, on its own mount, and only while the slice is
// neither "loading" nor "succeeded". An account switch therefore relies on
// globalCleared putting the seed back to "idle" — otherwise the next account's
// home would keep the previous one's rows and never refetch.
// ─────────────────────────────────────────────────────────────────

describe("globalCleared", () => {
  it("returns the recent-runs seed to idle, so HomeLaunchGrid's mount refetches it for the next account", () => {
    const signedInState = {
      ...globalReducer(undefined, { type: "@@init" }),
      recentRuns: [{ id: "prior-account-run" } as WorkflowRun],
      recentRunsStatus: "succeeded" as const,
    };

    const cleared = globalReducer(signedInState, globalCleared());

    expect(cleared.recentRuns).toEqual([]);
    expect(cleared.recentRunsStatus).toBe("idle");
  });
});
