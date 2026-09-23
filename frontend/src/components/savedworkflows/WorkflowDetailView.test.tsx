import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";
import { Provider } from "react-redux";
import { configureStore } from "@reduxjs/toolkit";
import authReducer from "@/store/slices/authSlice";
import agentsReducer from "@/store/slices/agentsSlice";
import skillsReducer from "@/store/slices/skillsSlice";
import hooksReducer from "@/store/slices/hooksSlice";
import globalReducer from "@/store/slices/globalSlice";
import type { AgentDef } from "@/types/index";
import type { UserWorkflowSummary } from "@/store/api/userWorkflows";
import { WorkflowDetailView } from "./WorkflowDetailView";

// ISS-327 — WorkflowDetailView (/workflows/{id}) renders workflow.agent_ids
// verbatim with no id-to-name lookup, unlike LibraryPage/ComposerPage which
// both resolve the same ids via useAgentLibrary()'s allAgents. This test
// seeds the same Redux `agents` slice ComposerPage reads (populated by
// GET /api/agents/library in the real app) and asserts the detail view
// resolves the friendly name/role instead of the raw slug.

const AGENTS: AgentDef[] = [
  {
    id: "documentation-agent",
    name: "Documentation",
    role: "API & Technical Writing",
    description: "",
    pipeline_type: "user_stories",
    order: 1,
    icon: "file-text",
    estimated_duration: 60,
    has_skill: false,
  },
  {
    id: "prototype-specify",
    name: "Spec Writer",
    role: "Specification & Architecture",
    description: "",
    pipeline_type: "prototype",
    order: 1,
    icon: "file-text",
    estimated_duration: 60,
    has_skill: false,
  },
];

function renderWithStore(ui: React.ReactElement) {
  const store = configureStore({
    reducer: {
      auth: authReducer,
      agents: agentsReducer,
      skills: skillsReducer,
      hooks: hooksReducer,
      global: globalReducer,
    },
    preloadedState: {
      agents: {
        agents: AGENTS,
        totalCount: AGENTS.length,
        pipelines: {},
        status: "succeeded" as const,
        error: null,
      },
    },
  });
  return render(<Provider store={store}>{ui}</Provider>);
}

const WORKFLOW: UserWorkflowSummary = {
  id: "656ca387-e69c-474d-b7ff-5fd9eb017cc0",
  name: "My prototype",
  description: "A saved workflow",
  base_pipeline_type: "prototype",
  agent_ids: ["documentation-agent", "prototype-specify"],
};

describe("WorkflowDetailView — ISS-327", () => {
  // xfail(strict): ISS-327 unfixed — WorkflowDetailView never calls
  // useAgentLibrary(), so it renders raw agent_ids. Remove `fails` once the
  // component resolves ids to names; a passing run with `fails` still set
  // errors loudly, per the project's xfail-strict convention.
  it("resolves agent ids to friendly display names, not raw slugs", () => {
    renderWithStore(<WorkflowDetailView workflow={WORKFLOW} />);

    expect(screen.getByText("Documentation")).toBeInTheDocument();
    expect(screen.getByText("Spec Writer")).toBeInTheDocument();

    expect(screen.queryByText("documentation-agent")).not.toBeInTheDocument();
    expect(screen.queryByText("prototype-specify")).not.toBeInTheDocument();
  });
});

// ISS-490 — INFERRED sibling: a custom-agent instance's real name lives on
// `workflow.manifest.steps[].name` (set by `instantiateIfTemplate`/renamed in
// the Composer), never in the `agents/library` catalog `useAgentLibrary()`
// exposes (the catalog only has the bare "custom-agent" template, seeded
// with the placeholder name "New agent"). A fix that only adds catalog
// lookup still shows the raw `custom-agent:<instance_id>` slug (or the
// generic placeholder) for these ids — it must also fall back to the
// manifest step's own `name`.
describe("WorkflowDetailView — ISS-490", () => {
  it(
    "resolves a custom-agent instance's own name from the manifest, not the catalog placeholder",
    () => {
      const workflow: UserWorkflowSummary = {
        id: "custom-wf-1",
        name: "My custom workflow",
        description: null,
        base_pipeline_type: "custom",
        agent_ids: ["custom-agent:inst-abc123"],
        manifest: {
          steps: [
            {
              agent: "custom-agent",
              instance_id: "inst-abc123",
              name: "Risk Reviewer",
            },
          ],
        },
      };

      renderWithStore(<WorkflowDetailView workflow={workflow} />);

      expect(screen.getByText("Risk Reviewer")).toBeInTheDocument();
      expect(screen.queryByText("custom-agent:inst-abc123")).not.toBeInTheDocument();
      expect(screen.queryByText("New agent")).not.toBeInTheDocument();
    },
  );
});
