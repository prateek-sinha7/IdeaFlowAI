import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";

import { SubAgentReadOnlyList } from "./SubAgentReadOnlyList";
import type { AgentDef } from "@/types/index";

function makeAgent(overrides: Partial<AgentDef> & Pick<AgentDef, "id" | "name" | "role">): AgentDef {
  return {
    description: "",
    pipeline_type: "custom",
    order: 0,
    icon: "bot",
    estimated_duration: 0,
    has_skill: false,
    ...overrides,
  };
}

describe("SubAgentReadOnlyList", () => {
  it("renders nothing when there are no sub-agents", () => {
    const { container } = render(<SubAgentReadOnlyList agents={[]} />);

    expect(container).toBeEmptyDOMElement();
  });

  it("shows each sub-agent's name, role, initials and Sub-agent badge", () => {
    render(
      <SubAgentReadOnlyList
        agents={[
          makeAgent({ id: "a1", name: "Data Collector", role: "Gathers sources" }),
          makeAgent({ id: "a2", name: "Writer", role: "Drafts the report" }),
        ]}
      />,
    );

    const first = screen.getByTestId("subagent-row-a1");
    expect(within(first).getByText("Data Collector")).toBeInTheDocument();
    expect(within(first).getByText("Gathers sources")).toBeInTheDocument();
    expect(within(first).getByText("DC")).toBeInTheDocument();
    expect(within(first).getByText("Sub-agent")).toBeInTheDocument();

    const second = screen.getByTestId("subagent-row-a2");
    expect(within(second).getByText("Writer")).toBeInTheDocument();
    expect(within(second).getByText("WR")).toBeInTheDocument();
    expect(within(second).getByText("Sub-agent")).toBeInTheDocument();
  });

  it("renders nested children inside their parent's row, however deep", () => {
    render(
      <SubAgentReadOnlyList
        agents={[
          makeAgent({
            id: "parent",
            name: "Parent Agent",
            role: "Coordinates",
            children: [
              makeAgent({
                id: "child",
                name: "Child Helper",
                role: "Helps",
                children: [makeAgent({ id: "grandchild", name: "Grand Child", role: "Leaf" })],
              }),
            ],
          }),
        ]}
      />,
    );

    const parent = screen.getByTestId("subagent-row-parent");
    const child = within(parent).getByTestId("subagent-row-child");
    expect(within(child).getByText("Child Helper")).toBeInTheDocument();
    expect(within(child).getByTestId("subagent-row-grandchild")).toBeInTheDocument();
    expect(screen.getAllByText("Sub-agent")).toHaveLength(3);
  });

  it("does not nest anything for an agent whose children list is empty or absent", () => {
    render(
      <SubAgentReadOnlyList
        agents={[
          makeAgent({ id: "empty", name: "Empty Kids", role: "None", children: [] }),
          makeAgent({ id: "absent", name: "No Kids", role: "None" }),
        ]}
      />,
    );

    expect(screen.getAllByText("Sub-agent")).toHaveLength(2);
    expect(within(screen.getByTestId("subagent-row-empty")).queryByTestId(/^subagent-row-/)).toBeNull();
    expect(within(screen.getByTestId("subagent-row-absent")).queryByTestId(/^subagent-row-/)).toBeNull();
  });
});
