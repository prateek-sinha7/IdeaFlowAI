import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { paramsState } = vi.hoisted(() => ({
  paramsState: { value: { token: "tok-abc" } as { token?: string } | null },
}));

vi.mock("next/navigation", () => ({
  useParams: () => paramsState.value,
}));

// Stub: the real workflow owns auth, fetch and sockets and has its own tests
// (HandoffWorkflow.test.tsx, page.security.test.tsx). The stub echoes the received
// token so the page's hand-off contract is observable. A test id is used because it has no role.
vi.mock("@/components/handoff/HandoffWorkflow", () => ({
  HandoffWorkflow: ({ token }: { token: string }) => <div data-testid="handoff-workflow-stub">{token}</div>,
}));

import HandoffPage from "./page";

describe("HandoffPage", () => {
  beforeEach(() => {
    paramsState.value = { token: "tok-abc" };
  });

  it("passes the route token to HandoffWorkflow", () => {
    render(<HandoffPage />);

    expect(screen.getByTestId("handoff-workflow-stub")).toHaveTextContent("tok-abc");
  });

  it("passes an unusual token through verbatim without altering it", () => {
    paramsState.value = { token: "a%2Fb..c" };
    render(<HandoffPage />);

    expect(screen.getByTestId("handoff-workflow-stub")).toHaveTextContent("a%2Fb..c");
  });

  it.each([
    ["the token param is missing", {}],
    ["the token param is an empty string", { token: "" }],
    ["params are null", null],
  ])("renders nothing when %s", (_label, params) => {
    paramsState.value = params;
    const { container } = render(<HandoffPage />);

    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByTestId("handoff-workflow-stub")).not.toBeInTheDocument();
  });
});
