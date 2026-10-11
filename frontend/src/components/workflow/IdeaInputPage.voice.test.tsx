/**
 * IdeaInputPage — voice dictation into the brief. The speech hook is the system
 * boundary (browser SpeechRecognition); the page owns the Voice/Stop control, the
 * "Listening..." placeholder and merging the live transcript after the text that
 * was already typed.
 */
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { IdeaInputPage } from "./IdeaInputPage";
import renderWithProviders from "@/test/renderWithProviders";
import type { AgentDef } from "@/types/index";

const speech = vi.hoisted(() => ({
  isListening: false,
  transcript: "",
  isSupported: true,
  startListening: vi.fn(),
  stopListening: vi.fn(),
}));

vi.mock("@/hooks/useSpeechRecognition", () => ({ useSpeechRecognition: () => speech }));
vi.mock("./AgentsPopup", () => ({ AgentsPopup: () => null }));
vi.mock("./ReviewGatesSection", () => ({ ReviewGatesSection: () => null }));

const AGENT: AgentDef = {
  id: "domain-analyst",
  name: "Domain Analyst",
  role: "role",
  description: "d",
  pipeline_type: "user_stories",
  order: 1,
  icon: "x",
  estimated_duration: 0,
  has_skill: false,
};

function renderPage() {
  const element = <IdeaInputPage workflowType="user_stories" onBack={vi.fn()} onRun={vi.fn()} />;
  const result = renderWithProviders(element, {
    preloadedState: {
      agents: { agents: [AGENT], totalCount: 1, pipelines: {}, status: "succeeded", error: null },
    },
  });
  return { rerender: () => result.rerender(element) };
}

const brief = () => screen.getByRole("textbox", { name: "Brief description" });

beforeEach(() => {
  speech.isListening = false;
  speech.transcript = "";
  speech.isSupported = true;
  speech.startListening.mockReset();
  speech.stopListening.mockReset();
});

describe("IdeaInputPage voice input", () => {
  it("does not offer a Voice control when speech recognition is unsupported", () => {
    speech.isSupported = false;

    renderPage();

    expect(screen.queryByRole("button", { name: "Voice" })).not.toBeInTheDocument();
  });

  it("starts listening when Voice is clicked", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("button", { name: "Voice" }));

    expect(speech.startListening).toHaveBeenCalledTimes(1);
    expect(speech.stopListening).not.toHaveBeenCalled();
  });

  it("shows Stop and the listening placeholder while listening, and stops on click", async () => {
    const user = userEvent.setup();
    speech.isListening = true;
    renderPage();

    expect(brief()).toHaveAttribute("placeholder", "Listening... speak your idea");
    await user.click(screen.getByRole("button", { name: "Stop" }));

    expect(speech.stopListening).toHaveBeenCalledTimes(1);
    expect(speech.startListening).not.toHaveBeenCalled();
  });

  it("appends the live transcript after the text typed before dictation started", async () => {
    const user = userEvent.setup();
    const { rerender } = renderPage();
    await user.type(brief(), "Hello");
    await user.click(screen.getByRole("button", { name: "Voice" }));

    speech.isListening = true;
    speech.transcript = "world";
    rerender();

    expect(brief()).toHaveValue("Hello world");
  });

  it("uses the transcript alone when nothing was typed before dictation", async () => {
    const user = userEvent.setup();
    const { rerender } = renderPage();
    await user.click(screen.getByRole("button", { name: "Voice" }));

    speech.isListening = true;
    speech.transcript = "dictated brief";
    rerender();

    expect(brief()).toHaveValue("dictated brief");
  });

  it("ignores a leftover transcript when the recogniser is not listening", () => {
    speech.transcript = "stale words";

    renderPage();

    expect(brief()).toHaveValue("");
  });
});
