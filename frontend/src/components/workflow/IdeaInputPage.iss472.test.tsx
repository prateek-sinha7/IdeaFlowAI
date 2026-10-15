/**
 * ISS-472 / QA-KB-052 — IdeaInputPage has no tier lock. A basic-tier account on
 * /create/app (app_builder is pro+) gets a fully interactive composer and only
 * the backend 403 stops the run. Expected: same locked/upgrade state as
 * LaunchWizard (ISS-321) and Run blocked client-side (button AND Cmd+Enter).
 *
 * The tier is supplied both ways the fix might read it (a `userTier` prop and
 * a getMe() profile) so the test does not dictate the fix's tier source.
 */
import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { IdeaInputPage } from "./IdeaInputPage";
import { SkillsHooksProvider } from "@/context/SkillsHooksContext";
import renderWithProviders from "@/test/renderWithProviders";

vi.mock("@/hooks/useSpeechRecognition", () => ({
  useSpeechRecognition: () => ({
    isListening: false, transcript: "", startListening: vi.fn(), stopListening: vi.fn(), isSupported: false,
  }),
}));
vi.mock("./AgentsPopup", () => ({ AgentsPopup: () => null }));
vi.mock("./ReviewGatesSection", () => ({ ReviewGatesSection: () => null }));

vi.mock("@/lib/api", () => ({
  getToken: () => "test-token",
  getMe: vi.fn().mockResolvedValue({ id: "u1", email: "qa-basic@flowinqa.com", tier: "basic" }),
  createUserWorkflow: vi.fn(),
  getWorkflowDetail: vi.fn(),
  setWorkflowOverrideEnabled: vi.fn(),
}));

const AGENTS = [
  {
    id: "app-builder-agent", name: "App Builder", role: "Builds the app", description: "d",
    pipeline_type: "app_builder", order: 1, icon: "x", estimated_duration: 60, has_skill: false,
  },
];

async function renderBasic() {
  const onRun = vi.fn();
  const extra = { userTier: "basic" } as Record<string, unknown>;
  renderWithProviders(
    <SkillsHooksProvider>
      <IdeaInputPage workflowType="app_builder" onBack={vi.fn()} onRun={onRun} {...extra} />
    </SkillsHooksProvider>,
    {
      preloadedState: {
        agents: { agents: AGENTS, totalCount: 1, pipelines: {}, status: "succeeded", error: null },
      },
    },
  );
  const user = userEvent.setup();
  await user.type(screen.getByRole("textbox"), "Build a todo app.");
  return { onRun, user };
}

describe("ISS-472 — IdeaInputPage tier lock for an unentitled pipeline", () => {
  it("shows the upgrade lock and disables Run for a basic tier on app_builder", async () => {
    await renderBasic();
    expect(await screen.findByText(/requires .* plan|does not include/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /run workflow/i })).toBeDisabled();
  });

  it("does not launch on Cmd+Enter for a basic tier on app_builder", async () => {
    const { onRun, user } = await renderBasic();
    await screen.findByText(/requires .* plan|does not include/i, {}, { timeout: 500 }).catch(() => {});
    await user.keyboard("{Meta>}{Enter}{/Meta}");
    expect(onRun).not.toHaveBeenCalled();
  });
});
