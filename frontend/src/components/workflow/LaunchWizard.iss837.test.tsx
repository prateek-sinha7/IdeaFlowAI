import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, cleanup, waitFor } from "@testing-library/react";
import { Provider } from "react-redux";
import { combineReducers, configureStore } from "@reduxjs/toolkit";
import React from "react";
import authReducer from "@/store/slices/authSlice";
import agentsReducer from "@/store/slices/agentsSlice";
import skillsReducer from "@/store/slices/skillsSlice";
import hooksReducer from "@/store/slices/hooksSlice";
import globalReducer from "@/store/slices/globalSlice";
import { SkillsHooksProvider } from "@/context/SkillsHooksContext";

// ─────────────────────────────────────────────────────────────────────────────
// QA-PS-044 / ISS-837 — LaunchWizard.tsx:617-654's "Load both template
// families + the design-system registry once authed" effect unconditionally
// calls listPrototypeTemplates() (the WEB/prototype family) even on
// /create/ppt (initialMode="ppt"), a deck-only route that never renders a web
// template picker. This is the over-fetch mechanism behind the report's
// duplicate-looking `GET /api/templates` count on the PPT wizard: two
// different template endpoints fire on a route that only needs one.
// ─────────────────────────────────────────────────────────────────────────────

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
}));

vi.mock("@/lib/api", () => ({
  getToken: () => "test-token",
  getMe: vi.fn().mockResolvedValue({ id: "u1", email: "qa@flowinqa.com", tier: "enterprise" }),
  extractFileText: vi.fn(),
  stageRunFile: vi.fn(),
  createUserWorkflow: vi.fn().mockResolvedValue({ id: "wf-1" }),
  saveUserWorkflow: vi.fn().mockResolvedValue({ id: "wf-1" }),
  handleSessionExpiry: vi.fn(),
  getWorkflowDetail: vi.fn().mockResolvedValue({
    id: "ppt", steps: [], manifest_steps: null, has_override: false, is_overridden: false, override_id: null,
  }),
  setWorkflowOverrideEnabled: vi.fn().mockResolvedValue({}),
}));

const listPrototypeTemplatesMock = vi.fn().mockResolvedValue([]);
const listDesignSystemsMock = vi.fn().mockResolvedValue([]);
const listPPTTemplatesMock = vi.fn().mockResolvedValue([]);

vi.mock("@/lib/prototype-api", () => ({
  listPrototypeTemplates: (...args: unknown[]) => listPrototypeTemplatesMock(...args),
  listDesignSystems: (...args: unknown[]) => listDesignSystemsMock(...args),
}));
vi.mock("@/lib/ppt-api", () => ({
  listPPTTemplates: (...args: unknown[]) => listPPTTemplatesMock(...args),
}));
vi.mock("@/hooks/useSpeechRecognition", () => ({
  useSpeechRecognition: () => ({
    isListening: false, transcript: "", startListening: vi.fn(), stopListening: vi.fn(), isSupported: false,
  }),
}));
vi.mock("@/components/workflow/WizardStepper", () => ({
  WizardStepper: () => <div data-testid="stepper" />,
}));
vi.mock("@/components/workflow/prototype/DesignSystemPicker", () => ({
  DesignSystemPicker: () => <div data-testid="ds-picker" />,
}));
vi.mock("@/components/workflow/ReviewGatesSection", () => ({
  ReviewGatesSection: () => <div data-testid="gates" />,
}));
vi.mock("@/components/workflow/AgentsPopup", () => ({
  AgentsPopup: () => <div data-testid="agents-popup" />,
}));
vi.mock("@/components/catalog/NameWorkflowModal", () => ({
  NameWorkflowModal: () => <div data-testid="save-modal" />,
}));

import { LaunchWizard } from "./LaunchWizard";

const testRootReducer = combineReducers({
  auth: authReducer,
  agents: agentsReducer,
  skills: skillsReducer,
  hooks: hooksReducer,
  global: globalReducer,
});

function renderPpt() {
  const testStore = configureStore({
    reducer: testRootReducer,
    preloadedState: {
      agents: { agents: [], totalCount: 0, pipelines: {}, status: "succeeded" as const, error: null },
    },
  });
  return render(
    <Provider store={testStore}>
      <SkillsHooksProvider>
        <LaunchWizard initialMode="ppt" />
      </SkillsHooksProvider>
    </Provider>,
  );
}

beforeEach(() => {
  listPrototypeTemplatesMock.mockClear();
  listDesignSystemsMock.mockClear();
  listPPTTemplatesMock.mockClear();
});

afterEach(() => {
  cleanup();
});

describe("LaunchWizard template-family fetch scoping (QA-PS-044 / ISS-837)", () => {
  it("does not fetch the web/prototype template family on a deck-only (ppt) open", async () => {
    renderPpt();

    await waitFor(() => {
      expect(listPPTTemplatesMock).toHaveBeenCalled();
    });

    // /create/ppt only ever renders the deck template picker — it never needs
    // the web/prototype template family, which LaunchWizard's shared
    // "load both families" effect fetches unconditionally regardless of mode.
    expect(listPrototypeTemplatesMock).not.toHaveBeenCalled();
  });
});
