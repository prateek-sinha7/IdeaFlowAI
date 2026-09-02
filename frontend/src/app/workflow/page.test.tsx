/**
 * ISS-492 — `app/workflow/page.tsx` must wire `onStartPipeline` (and
 * `pipelineState`, so the step machine can ever leave "build") into
 * `WorkflowView`. Today it only passes `pipelineType`, `userMessage`, and
 * `onClose` (`page.tsx:58-62`), which is the root cause both ISS-328's
 * silent-no-op Run click and this card's permanently-unreachable
 * running/complete steps trace back to.
 *
 * `WorkflowView` is stubbed at the module boundary purely to capture the
 * props `WorkflowPage` supplies it — its own internal behaviour is covered
 * by WorkflowView.zeroAgents.test.tsx (ISS-328) and is out of scope here.
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));
vi.mock("@/lib/api", () => ({
  getToken: () => "test-token",
}));
vi.mock("@/components/workflow/AgentLibrary", () => ({
  AgentLibrary: () => null,
}));

let capturedProps: Record<string, unknown> | null = null;
vi.mock("@/components/workflow/WorkflowView", () => ({
  WorkflowView: (props: Record<string, unknown>) => {
    capturedProps = props;
    return <div data-testid="workflow-view-stub" />;
  },
}));

import WorkflowPage from "./page";

describe("WorkflowPage (ISS-492)", () => {
  it("passes a real onStartPipeline callback and pipelineState into WorkflowView", async () => {
    render(<WorkflowPage />);
    await screen.findByTestId("workflow-view-stub");

    expect(typeof capturedProps?.onStartPipeline).toBe("function");
    expect(capturedProps?.pipelineState).toBeDefined();
  });
});
