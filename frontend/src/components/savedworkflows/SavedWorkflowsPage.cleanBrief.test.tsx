/** ISS-882 — cleanBrief's `[^\]]*` leaves ".txt]" in the preview for legacy briefs. */
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";

const mockGetUserWorkflows = vi.fn();
vi.mock("@/lib/api", () => ({
  getToken: () => "t",
  getUserWorkflows: (t: string) => mockGetUserWorkflows(t),
  createUserWorkflow: vi.fn(),
  renameUserWorkflow: vi.fn(),
  deleteUserWorkflow: vi.fn(),
}));
vi.mock("motion/react", () => {
  const strip = new Set(["initial","animate","exit","transition","whileHover","whileTap","whileFocus","whileInView","viewport","layout","layoutId","drag","dragConstraints","variants","custom"]);
  return {
    motion: new Proxy({}, {
      get: (_t, prop: string) => ({ children, ...rest }: { children?: React.ReactNode } & Record<string, unknown>) =>
        React.createElement(prop, Object.fromEntries(Object.entries(rest).filter(([k]) => !strip.has(k))), children),
    }),
    AnimatePresence: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  };
});
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
  useSearchParams: () => ({ get: vi.fn(() => null) }),
}));

import { SavedWorkflowsPage } from "./SavedWorkflowsPage";

describe("SavedWorkflowsPage cleanBrief (ISS-882)", () => {
  it('brief preview drops a marker whose filename contains "]"', async () => {
    mockGetUserWorkflows.mockResolvedValue([{
      id: "uw-1", name: "Legacy", description: "", base_pipeline_type: "custom",
      agent_ids: [], model_overrides: null, updated_at: "2026-07-01T10:00:00",
      selections: { _wizard: { brief: "idea\n\n[Attached: my].txt]" } },
    }]);
    render(<SavedWorkflowsPage />);
    await screen.findByText("Legacy");
    const preview = await screen.findByText(/^idea/);
    expect(preview.textContent?.trim()).toBe("idea");
  });
});
