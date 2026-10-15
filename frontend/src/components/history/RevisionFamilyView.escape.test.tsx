// ISS-931 (QA-KB-041): Escape must close the History "Run actions" menu after an unfocused click.
// it.fails: red today by design; remove `.fails` when the fix lands. RowMenu
// (RevisionFamilyView.tsx:446-451, module-local; rendered via the exported FamilyGroupCard).
import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React, { useState } from "react";
import { FamilyGroupCard, type FamilyGroup } from "@/components/history/RevisionFamilyView";
import type { WorkflowRun } from "@/types/index";

vi.mock("@/hooks/useWorkflowMetadata", () => ({
  useWorkflowShortNames: () => () => undefined,
}));

const run = {
  id: "b0642e0f-fe74-4f7e-9f16-8b164a6e989d", title: "A history run", type: "custom",
  status: "completed", createdAt: "2026-09-01T14:46:55.000Z", agentCount: 3,
} as WorkflowRun;
const group = { root: run, members: [run], latest: run } as FamilyGroup;

// Same wiring WorkflowHistory.tsx:1455-1456 uses for openMenuId / onToggleMenu.
function Harness() {
  const [openMenuId, setOpenMenuId] = useState<string | null>(null);
  return (
    <FamilyGroupCard group={group} index={0} expanded={false} onToggle={() => {}} onSelectRun={() => {}}
      openMenuId={openMenuId}
      onToggleMenu={(id, e) => { e?.stopPropagation(); setOpenMenuId(openMenuId === id ? null : id); }}
      onDeleteClick={() => {}} />
  );
}
describe("ISS-931 History RowMenu Escape", () => {
  it("ISS-931: Escape closes the Run actions menu after an unfocused click on the trigger", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const trigger = screen.getByRole("button", { name: "Run actions" });
    fireEvent.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    await user.keyboard("{Escape}");
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    await waitFor(() => expect(screen.queryByRole("menu")).toBeNull());
  });
});
