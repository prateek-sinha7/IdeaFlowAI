/**
 * ISS-371 (QA-KB-014) — IdeaInputPage never reports unsaved state to the shared
 * Back guard (DashboardLayout `handleUnsavedChange` / `hasUnsavedWork`), so Back
 * silently discards the typed brief and agent picks. ComposerPage already does
 * this via `onUnsavedChange`. Each case is `it.fails`: red today, and the
 * runner flags it the moment the fix lands so the marker gets removed.
 */
import { describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import path from "node:path";
import userEvent from "@testing-library/user-event";
import { renderWithProviders, screen } from "@/test/renderWithProviders";

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
vi.mock("./AgentsPopup", () => ({ AgentsPopup: () => null }));
vi.mock("./ReviewGatesSection", () => ({ ReviewGatesSection: () => null }));

const agents: AgentDef[] = [
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
];

function renderPage(onUnsavedChange = vi.fn()) {
  // Spread through a loose record: the prop does not exist on IdeaInputPage yet.
  const extra = { onUnsavedChange } as Record<string, unknown>;
  renderWithProviders(
    <SkillsHooksProvider>
      <IdeaInputPage workflowType="user_stories" onBack={vi.fn()} onRun={vi.fn()} {...extra} />
    </SkillsHooksProvider>,
    {
      preloadedState: {
        agents: { agents, totalCount: 1, pipelines: {}, status: "succeeded", error: null },
      },
    },
  );
  return onUnsavedChange;
}

describe("ISS-371 — IdeaInputPage reports unsaved work to the Back guard", () => {
  it("reports dirty after a brief is typed", async () => {
    const onUnsavedChange = renderPage();
    await userEvent.setup().type(screen.getByRole("textbox"), "Build a thing");
    expect(onUnsavedChange).toHaveBeenLastCalledWith(true);
  });

  it("is not dirty after the async roster re-seed alone, and clears when the brief is emptied", async () => {
    const onUnsavedChange = renderPage();
    // Mount (incl. roster seeding) reports state, and never reports dirty.
    expect(onUnsavedChange).toHaveBeenCalled();
    expect(onUnsavedChange).not.toHaveBeenCalledWith(true);
    const user = userEvent.setup();
    const box = screen.getByRole("textbox");
    await user.type(box, "x");
    await user.clear(box);
    expect(onUnsavedChange).toHaveBeenLastCalledWith(false);
  });

  it("DashboardLayout feeds the IdeaInputPage mount into the guard (Back with dirty state prompts)", () => {
    const src = readFileSync(path.join(__dirname, "../layout/DashboardLayout.tsx"), "utf8");
    const start = src.indexOf("<IdeaInputPage");
    const mount = src.slice(start, src.indexOf("/>", start));
    expect(mount).toContain("onUnsavedChange={handleUnsavedChange}");
  });
});
