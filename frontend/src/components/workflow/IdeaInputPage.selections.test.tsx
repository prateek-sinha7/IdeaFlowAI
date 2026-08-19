/**
 * WR-01 (EMP-01) — wiring assertion: the Advanced-expander selections map (reported
 * up via `onSelectionsChange` from AgentsPopup) threads into the run_pipeline payload
 * as `selections`, and an EMPTY selection leaves the payload byte-identical (no
 * `selections` key) so existing runs are unchanged (INV-3 / SC-001).
 *
 * Before this fix `selectionsRef.current` was used ONLY in `handleSaveWorkflow` — a
 * user could compose Advanced levers and save them, but launching applied none of
 * them (the whole EMP-01 overlay was dead on the live FE path). This test pins the
 * launch contract: the selections reach `onRun(..., extraParams.selections)`, the
 * exact key `websocket.py` reads off the payload and `engine._apply_selections`
 * overlays onto the compiled plan.
 *
 * Strategy mirrors IdeaInputPage.modelOverrides.test.tsx: mock `./AgentsPopup` with a
 * tiny double surfacing `onSelectionsChange` as a button; drive Run; assert extraParams.
 */

import { describe, expect, it, vi } from "vitest";
import { renderWithProviders, screen } from "@/test/renderWithProviders";
import userEvent from "@testing-library/user-event";

import { IdeaInputPage } from "./IdeaInputPage";
import { SkillsHooksProvider } from "@/context/SkillsHooksContext";
import type { AgentDef } from "@/types/index";

vi.mock("@/hooks/useSpeechRecognition", () => ({
  useSpeechRecognition: () => ({
    isListening: false,
    transcript: "",
    startListening: vi.fn(),
    stopListening: vi.fn(),
    isSupported: false,
  }),
}));

// Test double: expose the EMP-01 contract — `onSelectionsChange` — as a button so the
// test can drive an Advanced-lever selection deterministically (the real expander
// would fetch /api/capabilities). Also surfaces `initialSelections` so the
// re-load-on-launch path can be asserted.
const _SELECTION = {
  "market-research-agent": {
    validators: ["spec_plan_coverage"],
    gates: ["validation"],
    retry: 2,
  },
};

// 51-06 — a composed FAN-OUT selection: the worker step carries the generic
// fan-out levers (`strategy` + `task_source.source_step`). It must thread into
// the LAUNCH `selections` payload byte-for-byte, just like any other lever
// (INV-3 — the whole selections map is forwarded generically).
const _FANOUT_SELECTION = {
  "worker-agent": {
    strategy: "fanout_batch",
    task_source: {
      kind: "parsed",
      parser: "heading_tasks",
      source_step: "prototype-plan",
    },
  },
};

vi.mock("./AgentsPopup", () => ({
  AgentsPopup: ({
    onSelectionsChange,
    initialSelections,
  }: {
    onSelectionsChange?: (s: Record<string, Record<string, unknown>>) => void;
    initialSelections?: Record<string, Record<string, unknown>>;
  }) => (
    <>
      <button
        type="button"
        data-testid="pick-levers"
        onClick={() => onSelectionsChange?.(_SELECTION)}
      >
        pick levers
      </button>
      <button
        type="button"
        data-testid="pick-fanout"
        onClick={() => onSelectionsChange?.(_FANOUT_SELECTION)}
      >
        pick fanout
      </button>
      <span data-testid="seeded-selections">
        {JSON.stringify(initialSelections ?? null)}
      </span>
    </>
  ),
}));

vi.mock("./ReviewGatesSection", () => ({
  ReviewGatesSection: () => null,
}));

function renderPage(
  onRun = vi.fn(),
  initialSelections?: Record<string, Record<string, unknown>>,
) {
  const mockAgents: AgentDef[] = [
    {
      id: "domain-analyst",
      name: "Domain Analyst",
      role: "Discovery Lead",
      description: "Analyse the business domain",
      pipeline_type: "user_stories",
      order: 1,
      icon: "search",
      estimated_duration: 120,
      has_skill: false,
    },
    {
      id: "epic-architect",
      name: "Epic Architect",
      role: "Architect",
      description: "Design epics and features",
      pipeline_type: "user_stories",
      order: 2,
      icon: "building",
      estimated_duration: 180,
      has_skill: false,
    },
  ];

  renderWithProviders(
    <SkillsHooksProvider>
      <IdeaInputPage
        workflowType="user_stories"
        onBack={vi.fn()}
        onRun={onRun}
        initialSelections={initialSelections}
      />
    </SkillsHooksProvider>,
    {
      preloadedState: {
        agents: {
          agents: mockAgents,
          totalCount: mockAgents.length,
          pipelines: {},
          status: "succeeded",
          error: null,
        },
      },
    },
  );
  return { onRun };
}

describe("IdeaInputPage — EMP-01 selections launch wiring (WR-01)", () => {
  it("threads composed Advanced levers into onRun extraParams.selections", async () => {
    const user = userEvent.setup();
    const { onRun } = renderPage();

    await user.type(screen.getByRole("textbox"), "Analyse the market.");
    await user.click(screen.getByTestId("pick-levers"));
    await user.click(screen.getByRole("button", { name: /run workflow/i }));

    expect(onRun).toHaveBeenCalledTimes(1);
    const [message, agentIds, resolvedType, extraParams] = onRun.mock.calls[0];
    expect(message).toBe("Analyse the market.");
    expect(Array.isArray(agentIds)).toBe(true);
    expect(resolvedType).toBe("user_stories");
    // The selection lands as `selections` — the exact key websocket.py reads off
    // the run_pipeline payload and engine._apply_selections overlays.
    expect(extraParams).toEqual({ selections: _SELECTION });
  });

  it("threads a composed FAN-OUT selection into onRun extraParams.selections (51-06)", async () => {
    const user = userEvent.setup();
    const { onRun } = renderPage();

    await user.type(screen.getByRole("textbox"), "Fan out over the plan.");
    await user.click(screen.getByTestId("pick-fanout"));
    await user.click(screen.getByRole("button", { name: /run workflow/i }));

    expect(onRun).toHaveBeenCalledTimes(1);
    const [, , , extraParams] = onRun.mock.calls[0];
    // The fan-out levers reach the launch payload verbatim — the exact shape
    // engine._apply_selections overlays (strategy + task_source.source_step).
    expect(extraParams).toEqual({ selections: _FANOUT_SELECTION });
  });

  it("omits selections entirely when no lever is set (byte-identical payload, INV-3)", async () => {
    const user = userEvent.setup();
    const { onRun } = renderPage();

    await user.type(screen.getByRole("textbox"), "Analyse the market.");
    await user.click(screen.getByRole("button", { name: /run workflow/i }));

    expect(onRun).toHaveBeenCalledTimes(1);
    const [, , , extraParams] = onRun.mock.calls[0];
    expect(extraParams).toBeUndefined();
  });

  it("re-sends persisted selections seeded on a launched saved workflow", async () => {
    const user = userEvent.setup();
    // A launched saved workflow seeds the expander with its persisted manifest_json
    // selections; with no further edit Run must re-send them (the seed pre-fills the
    // ref so the levers are not lost on a saved-workflow launch).
    const { onRun } = renderPage(vi.fn(), _SELECTION);

    // The seed reached AgentsPopup (re-load) ...
    expect(screen.getByTestId("seeded-selections").textContent).toBe(
      JSON.stringify(_SELECTION),
    );

    await user.type(screen.getByRole("textbox"), "Re-run the saved workflow.");
    await user.click(screen.getByRole("button", { name: /run workflow/i }));

    expect(onRun).toHaveBeenCalledTimes(1);
    const [, , , extraParams] = onRun.mock.calls[0];
    // ... and re-sends on launch (the persisted levers re-reach the overlay).
    expect(extraParams).toEqual({ selections: _SELECTION });
  });
});
