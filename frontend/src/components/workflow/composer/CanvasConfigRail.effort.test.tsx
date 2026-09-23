/**
 * CanvasConfigRail.effort.test.tsx — spec 020, the canvas Effort dropdown.
 *
 * What the control has to get right:
 *
 *   1. Its options come from the SELECTED model's own catalog entry, so a GPT
 *      step offers six levels and a Claude step offers two. SC-001: nothing in
 *      this file may be a hardcoded model or level list, and nothing in the
 *      component may be either — the fixture below is the whole source of both.
 *   2. "none" reads "None" on a GPT model and "Off" on a Claude one. Same wire
 *      value, different promise: on GPT it selects the model's lowest reasoning
 *      setting, on Claude it turns extended thinking off.
 *   3. A model with no reasoning control renders no dropdown at all — an Effort
 *      select on such a model would be a control that does nothing.
 *   4. Switching GPT→Claude clears a level the new model cannot accept. Left
 *      alone, `xhigh` would sit in the step selection and be dropped at the
 *      request boundary: the UI would show a setting the run never applied.
 *   5. The chosen level reaches `onSelection` as `effort`. The payload is what
 *      the backend reads; the select's own value passing proves nothing.
 *
 * Mirrors CanvasConfigRail.test.tsx's harness (mocked `@/lib/api` + skills).
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import type { ComponentProps } from "react";
import { renderWithProviders, screen, within, waitFor } from "@/test/renderWithProviders";
import userEvent from "@testing-library/user-event";
import type { CapabilitiesPalette } from "@/lib/api";
import type { AgentDef } from "@/types/index";
import type { StepSelection } from "../AgentsPopup";

const mockGetCapabilities = vi.fn();
vi.mock("@/lib/api", () => ({
  getToken: () => "test-token",
  getCapabilities: (t: string) => mockGetCapabilities(t),
  getAgentPrompt: vi
    .fn()
    .mockResolvedValue({ prompt_body: "", override: null, has_override: false }),
  saveAgentPromptOverride: vi.fn(),
  deleteAgentPromptOverride: vi.fn(),
}));

vi.mock("@/hooks/useSkillsCatalog", () => ({
  useSkillsCatalog: () => ({ skills: [], categories: [] }),
}));

import { CanvasConfigRail } from "./CanvasConfigRail";

// One model per reasoning mode in model_catalog.py. Shapes and level tuples are
// the real ones — if the backend's Reasoning capability changes, this fixture is
// what has to be updated, and these tests are what will say so.
const LUNA = "global.openai.gpt-5.6-luna";
const HAIKU_45 = "eu.anthropic.claude-haiku-4-5-20251001-v1:0";
const SONNET_5 = "eu.anthropic.claude-sonnet-5";
// No catalog model has reasoning_mode "none" since Haiku 3.5 was removed
// (2026-09-22). The MODE is still live, so it is pinned with a synthetic entry
// rather than dropped with the model.
const NO_REASONING = "eu.anthropic.claude-no-reasoning-v1:0";

const PALETTE: CapabilitiesPalette = {
  capabilities: [
    { kind: "mechanical", name: "publish", user_allowed: true, description: "Code step: copy the highest publish_from_glob match onto the deliverable — no model.", security_gated: false, config_schema: {} },
  ],
  model_catalog: [
    { id: LUNA,     label: "GPT-5.6 Luna",     description: "", tier: "fast",     cost_class: "cheap",   provider: "bedrock", context_window: 1000000, user_allowed: true, reasoning_mode: "effort",   reasoning_levels: ["none", "low", "medium", "high", "xhigh", "max"] },
    { id: HAIKU_45, label: "Claude Haiku 4.5", description: "", tier: "fast",     cost_class: "cheap",   provider: "bedrock", context_window: 200000,  user_allowed: true, reasoning_mode: "budget",   reasoning_levels: ["none", "on"] },
    { id: SONNET_5, label: "Claude Sonnet 5",  description: "", tier: "powerful", cost_class: "premium", provider: "bedrock", context_window: 200000,  user_allowed: true, reasoning_mode: "adaptive", reasoning_levels: ["none", "on"] },
    { id: NO_REASONING, label: "No-Reasoning Model", description: "", tier: "fast", cost_class: "cheap", provider: "bedrock", context_window: 200000, user_allowed: true, reasoning_mode: "none", reasoning_levels: [] },
  ],
};

function mkAgent(over: Partial<AgentDef> & { id: string; name: string }): AgentDef {
  return {
    role: "Does a thing",
    description: "A capable agent.",
    pipeline_type: "custom",
    order: 1,
    icon: "",
    estimated_duration: 120,
    has_skill: false,
    ...over,
  } as AgentDef;
}

const WRITER = mkAgent({ id: "writer", name: "Writer" });

function renderRail(props: Partial<ComponentProps<typeof CanvasConfigRail>> = {}) {
  const onSelection = vi.fn();
  const utils = renderWithProviders(
    <CanvasConfigRail
      agent={WRITER}
      index={1}
      total={2}
      selection={undefined}
      onSelection={onSelection}
      priorAgents={[mkAgent({ id: "plan", name: "Plan" })]}
      {...props}
    />,
  );
  return { ...utils, onSelection };
}

/** Open Config and wait for the capabilities fetch to settle (userEvent clicks
 *  are swallowed while a pending act/microtask is in flight). */
async function openConfig() {
  await userEvent.click(screen.getByRole("tab", { name: /config/i }));
  await screen.findByLabelText(/^Model$/i);
}

/** The Effort select's option labels, in order. */
function effortOptions(): string[] {
  const select = screen.getByLabelText("Effort") as HTMLSelectElement;
  return within(select).getAllByRole("option").map((o) => o.textContent ?? "");
}

beforeEach(() => {
  vi.clearAllMocks();
  mockGetCapabilities.mockResolvedValue(PALETTE);
});

describe("CanvasConfigRail — Effort dropdown (spec 020)", () => {
  it("offers a GPT step all six catalog levels, Default first", async () => {
    renderRail({ selection: { model: LUNA } });
    await openConfig();
    expect(effortOptions()).toEqual([
      "Default", "None", "Low", "Medium", "High", "xHigh", "Max",
    ]);
  });

  it("offers a Claude step only Off/On — its catalog entry has two levels", async () => {
    renderRail({ selection: { model: HAIKU_45 } });
    await openConfig();
    expect(effortOptions()).toEqual(["Default", "Off", "On"]);
  });

  it("labels the same 'none' level Off on Claude and None on GPT", async () => {
    // The wire value is identical; only the promise differs, so the label is the
    // only thing telling the user which one they are getting.
    const { unmount } = renderRail({ selection: { model: SONNET_5 } });
    await openConfig();
    const claudeNone = within(screen.getByLabelText("Effort")).getByRole("option", { name: "Off" });
    expect((claudeNone as HTMLOptionElement).value).toBe("none");
    unmount();

    renderRail({ selection: { model: LUNA } });
    await openConfig();
    const gptNone = within(screen.getByLabelText("Effort")).getByRole("option", { name: "None" });
    expect((gptNone as HTMLOptionElement).value).toBe("none");
  });

  it("renders no Effort control for a model with no reasoning capability", async () => {
    renderRail({ selection: { model: NO_REASONING } });
    await openConfig();
    expect(screen.queryByLabelText("Effort")).not.toBeInTheDocument();
  });

  it("renders no Effort control before a model is chosen", async () => {
    // Default (workflow model) — the rail cannot know which levels apply, and
    // guessing would show a scale the step may not honour.
    renderRail();
    await openConfig();
    expect(screen.queryByLabelText("Effort")).not.toBeInTheDocument();
  });

  it("renders neither Model nor Effort for a Code step", async () => {
    // A mechanical step runs no model at all. The Model select used to render
    // here regardless, contradicting its own hint text.
    renderRail({ agent: mkAgent({ id: "publish", name: "Publish", mechanical: "publish" }) });
    await userEvent.click(screen.getByRole("tab", { name: /config/i }));
    await waitFor(() => expect(mockGetCapabilities).toHaveBeenCalled());
    expect(screen.queryByLabelText(/^Model$/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Effort")).not.toBeInTheDocument();
  });

  it("persists the chosen level as `effort` on the step selection", async () => {
    const { onSelection } = renderRail({ selection: { model: LUNA } });
    await openConfig();
    await userEvent.selectOptions(screen.getByLabelText("Effort"), "high");
    await waitFor(() => expect(onSelection).toHaveBeenCalled());
    const [id, sel] = onSelection.mock.calls.at(-1) as [string, StepSelection | undefined];
    expect(id).toBe("writer");
    expect(sel).toMatchObject({ model: LUNA, effort: "high" });
  });

  it("clears an effort the newly-chosen model does not accept", async () => {
    // GPT xhigh → Claude. Keeping it would leave the rail showing a level the
    // run silently drops.
    const { onSelection } = renderRail({ selection: { model: LUNA, effort: "xhigh" } });
    await openConfig();
    await userEvent.selectOptions(screen.getByLabelText("Model"), HAIKU_45);
    await waitFor(() => expect(onSelection).toHaveBeenCalled());
    const [, sel] = onSelection.mock.calls.at(-1) as [string, StepSelection | undefined];
    expect(sel).toMatchObject({ model: HAIKU_45 });
    expect(sel?.effort).toBeUndefined();
  });

  it("keeps an effort both models accept when switching between them", async () => {
    // "none" is in both level sets, so the switch must NOT discard it —
    // clearing indiscriminately would silently re-enable thinking on a step the
    // user had turned it off for.
    const { onSelection } = renderRail({ selection: { model: HAIKU_45, effort: "none" } });
    await openConfig();
    await userEvent.selectOptions(screen.getByLabelText("Model"), LUNA);
    await waitFor(() => expect(onSelection).toHaveBeenCalled());
    const [, sel] = onSelection.mock.calls.at(-1) as [string, StepSelection | undefined];
    expect(sel).toMatchObject({ model: LUNA, effort: "none" });
  });

  it("drops `effort` from the selection when set back to Default", async () => {
    const { onSelection } = renderRail({ selection: { model: LUNA, effort: "high" } });
    await openConfig();
    await userEvent.selectOptions(screen.getByLabelText("Effort"), "");
    await waitFor(() => expect(onSelection).toHaveBeenCalled());
    const [, sel] = onSelection.mock.calls.at(-1) as [string, StepSelection | undefined];
    expect(sel?.effort).toBeUndefined();
  });
});
