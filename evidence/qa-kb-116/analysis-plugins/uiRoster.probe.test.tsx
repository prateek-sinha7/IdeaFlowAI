// QA-KB-116 analysis probe, component tier. Offline (jsdom). Mounts the REAL IdeaInputPage / LaunchWizard /
// ReviewGatesSection with the payloads captured from the live :8000 backend and the live agent library, and
// reads what the Review gates checklist and the Advanced pill actually render. Only the network module, the
// router, the speech hook and the heavy popups are stubbed (same stubs the repo's own tests use).
//
//   admin@velocity.ai holds ENABLED overrides of user_stories / ppt / prototype / ppt_v2 (created by e2e);
//   pro@velocity.ai holds none. Same code, same library; only the payload differs.
import { beforeEach, describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { readFileSync } from "node:fs";
import path from "node:path";
import { renderWithProviders, screen, waitFor } from "@/test/renderWithProviders";
import type { AgentDef } from "@/types/index";

const h = vi.hoisted(() => ({ detail: {} as Record<string, unknown> }));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
}));
vi.mock("@/lib/api", () => ({
  getToken: () => "test-token",
  getMe: vi.fn().mockResolvedValue({ id: "u1", email: "probe@velocity.ai", tier: "enterprise" }),
  isNotFoundError: () => false,
  getWorkflowDetail: (_t: string, id: string) => Promise.resolve(h.detail[id]),
  createUserWorkflow: vi.fn().mockResolvedValue({ id: "wf-scratch" }),
  saveUserWorkflow: vi.fn().mockResolvedValue({ id: "wf-scratch" }),
  setWorkflowOverrideEnabled: vi.fn().mockResolvedValue({}),
  extractFileText: vi.fn(),
  stageRunFile: vi.fn(),
  getCapabilities: vi.fn().mockResolvedValue({ capabilities: [], model_catalog: [] }),
}));
vi.mock("@/lib/prototype-api", () => ({
  listPrototypeTemplates: vi.fn().mockResolvedValue([]),
  listDesignSystems: vi.fn().mockResolvedValue([]),
}));
vi.mock("@/lib/ppt-api", () => ({ listPPTTemplates: vi.fn().mockResolvedValue([]) }));
vi.mock("@/hooks/useSpeechRecognition", () => ({
  useSpeechRecognition: () => ({
    isListening: false, transcript: "", startListening: vi.fn(), stopListening: vi.fn(), isSupported: false,
  }),
}));
vi.mock("@/components/workflow/WizardStepper", () => ({
  WizardStepper: (props: { dsSlot?: React.ReactNode }) => <div>{props.dsSlot}</div>,
}));
vi.mock("@/components/catalog/NameWorkflowModal", () => ({ NameWorkflowModal: () => null }));
// The popup is stubbed to PRINT the roster it was handed (the canvas titles come from this list).
vi.mock("@/components/workflow/AgentsPopup", () => ({
  AgentsPopup: ({ agents }: { agents: AgentDef[] }) => (
    <div data-testid="popup-names">{agents.map((a) => a.name).join(" | ")}</div>
  ),
}));

import { IdeaInputPage } from "@/components/workflow/IdeaInputPage";
import { LaunchWizard } from "@/components/workflow/LaunchWizard";

const DIR = path.resolve(process.cwd(), "../evidence/qa-kb-116/analysis-plugins");
const load = (f: string) => JSON.parse(readFileSync(path.join(DIR, f), "utf8"));
const LIBRARY: AgentDef[] = load("library.json").agents;
const preloadedState = {
  agents: { agents: LIBRARY, totalCount: LIBRARY.length, pipelines: {}, status: "succeeded" as const, error: null },
};

/** Expand "Review gates" and return the visible row names, in order. */
async function reviewGateRows(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole("button", { name: /Review gates/ }));
  return Array.from(document.querySelectorAll<HTMLInputElement>('input[name^="review-gate-"]')).map(
    (i) => i.closest("label")?.querySelector("span.min-w-0 > span")?.textContent ?? "?",
  );
}
const pillText = () => screen.getByRole("button", { name: /Advanced/ }).textContent;

beforeEach(() => {
  sessionStorage.clear();
});

describe("QA-KB-116 UI probe: the Review gates checklist as rendered", () => {
  it("[today] U1 IdeaInputPage /create/user-stories, admin payload (enabled override): rows are raw ids, pill ~6m", async () => {
    h.detail = { user_stories: load("detail.admin.user_stories.json") };
    const user = userEvent.setup();
    renderWithProviders(<IdeaInputPage workflowType="user_stories" workflowId="user_stories" onBack={vi.fn()} onRun={vi.fn()} />, { preloadedState });
    await waitFor(() => expect(screen.getByTestId("popup-names").textContent).toContain("domain-analyst"));
    const rows = await reviewGateRows(user);
    console.log("[U1] Review gates rows:", JSON.stringify(rows));
    console.log("[U1] popup roster names:", screen.getByTestId("popup-names").textContent);
    console.log("[U1] Advanced pill:", JSON.stringify(pillText()));
    expect(rows).toEqual(["domain-analyst", "epic-architect", "story-estimator", "nfr-specialist", "backlog-reviewer", "backlog-compiler"]);
    expect(pillText()).toContain("~6m");
  });

  it("[control] U2 IdeaInputPage /create/user-stories, pro payload (no override): rows are the agents' names", async () => {
    h.detail = { user_stories: load("detail.pro.user_stories.json") };
    const user = userEvent.setup();
    renderWithProviders(<IdeaInputPage workflowType="user_stories" workflowId="user_stories" onBack={vi.fn()} onRun={vi.fn()} />, { preloadedState });
    await waitFor(() => expect(screen.getByTestId("popup-names").textContent).toContain("Domain Discovery Agent"));
    const rows = await reviewGateRows(user);
    console.log("[U2] Review gates rows:", JSON.stringify(rows));
    console.log("[U2] Advanced pill:", JSON.stringify(pillText()));
    expect(rows[0]).toBe("Domain Discovery Agent");
  });

  it("[today] U3 LaunchWizard ppt_v2, pro payload (NO override): rows are raw ids", async () => {
    h.detail = { ppt_v2: load("detail.pro.ppt_v2.json") };
    const user = userEvent.setup();
    renderWithProviders(<LaunchWizard initialMode="ppt_v2" />, { preloadedState });
    await waitFor(() => expect(screen.getByTestId("popup-names").textContent?.split(" | ").length).toBe(4));
    const rows = await reviewGateRows(user);
    console.log("[U3] Review gates rows:", JSON.stringify(rows));
    console.log("[U3] popup roster names:", screen.getByTestId("popup-names").textContent);
    expect(rows).toEqual(["ppt-brief-analyst", "ppt-composer", "ppt-deck-qa-v2", "ppt-code-generator"]);
  });

  it("[today] U4 LaunchWizard ppt_v2, admin payload (enabled override): rows are raw ids", async () => {
    h.detail = { ppt_v2: load("detail.admin.ppt_v2.json") };
    const user = userEvent.setup();
    renderWithProviders(<LaunchWizard initialMode="ppt_v2" />, { preloadedState });
    await waitFor(() => expect(screen.getByTestId("popup-names").textContent?.split(" | ").length).toBe(4));
    const rows = await reviewGateRows(user);
    console.log("[U4] Review gates rows:", JSON.stringify(rows));
    expect(rows).toEqual(["ppt-brief-analyst", "ppt-composer", "ppt-deck-qa-v2", "ppt-code-generator"]);
  });

  it("[control] U5 LaunchWizard ppt, pro payload (no override): rows are the agents' names", async () => {
    h.detail = { ppt: load("detail.pro.ppt.json") };
    const user = userEvent.setup();
    renderWithProviders(<LaunchWizard initialMode="ppt" />, { preloadedState });
    await waitFor(() => expect(screen.getByTestId("popup-names").textContent?.split(" | ").length).toBe(3));
    const rows = await reviewGateRows(user);
    console.log("[U5] Review gates rows:", JSON.stringify(rows));
    expect(rows[0]).toBe("Presentation Strategist Agent");
  });

  it("[today] U6 LaunchWizard ppt, admin payload (enabled override): rows are raw ids", async () => {
    h.detail = { ppt: load("detail.admin.ppt.json") };
    const user = userEvent.setup();
    renderWithProviders(<LaunchWizard initialMode="ppt" />, { preloadedState });
    await waitFor(() => expect(screen.getByTestId("popup-names").textContent).toContain("ppt-brief-analyst"));
    const rows = await reviewGateRows(user);
    console.log("[U6] Review gates rows:", JSON.stringify(rows));
    expect(rows).toEqual(["ppt-brief-analyst", "ppt-composer", "ppt-validator"]);
  });
});
