/**
 * ISS-647 (QA-PS-005), second mechanism: the open "N Running" menu rendered the
 * live run list, so a run finishing mid-click reflowed the rows under the
 * cursor — the click hit whichever run shifted into that slot, or nothing.
 * The open menu must keep the list it opened with until it closes.
 */
import { describe, it, expect, vi } from "vitest";
import { renderWithProviders, screen, within } from "@/test/renderWithProviders";
import userEvent from "@testing-library/user-event";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
}));

import { AppHeader } from "./AppHeader";
import type { WorkflowRun } from "@/types/index";

function makeRun(id: string, title: string, status = "running"): WorkflowRun {
  return {
    id, title, status, type: "user_stories", input: "{}",
    createdAt: new Date().toISOString(), parentRunId: null, rootRunId: id, agentCount: 4,
  } as WorkflowRun;
}

describe("AppHeader — ISS-647 open 'N Running' menu does not reflow", () => {
  it("keeps a run that finished while the menu was open in its row, then goes live on close", async () => {
    const user = userEvent.setup();
    const onSelectWorkflowRun = vi.fn();
    const header = (recentRuns: WorkflowRun[]) => (
      <AppHeader
        currentPage="home"
        onNavigate={vi.fn()}
        onLogout={vi.fn()}
        onSelectWorkflowRun={onSelectWorkflowRun}
        recentRuns={recentRuns}
      />
    );
    const { rerender } = renderWithProviders(
      header([makeRun("a", "Alpha"), makeRun("b", "Beta"), makeRun("c", "Gamma")]),
    );

    await user.click(screen.getByRole("button", { name: /3 pipelines running/i }));
    // Alpha completes in the background while the menu is open.
    rerender(header([makeRun("a", "Alpha", "completed"), makeRun("b", "Beta"), makeRun("c", "Gamma")]));

    const items = within(screen.getByRole("menu")).getAllByRole("menuitem");
    expect(items.map((i) => i.textContent)).toEqual([
      expect.stringContaining("Alpha"),
      expect.stringContaining("Beta"),
      expect.stringContaining("Gamma"),
    ]);

    // The click lands on the run the user aimed at (now finished → opened as a terminal run).
    await user.click(items[0]);
    expect(onSelectWorkflowRun).toHaveBeenCalledWith(expect.objectContaining({ id: "a" }));
    // Closed: the badge is back on the live list.
    expect(screen.getByRole("button", { name: /2 pipelines running/i })).toBeInTheDocument();
  });
});
