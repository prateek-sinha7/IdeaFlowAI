import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import React from "react";
import type { ClarifyRound } from "@/types/index";
import { FilesTab } from "./FilesTab";

// ─────────────────────────────────────────────────────────────────
// Workstream C2 (POR §5 D7) — Files "Run input" section real-DOM specs.
// prompt.md is present whenever the parsed brief is threaded; clarifications.md
// only when rounds exist; both download via the default downloadBlob path; a
// call site that threads neither shows NO "Run input" section (zero regression).
// ─────────────────────────────────────────────────────────────────

const STRIPPED_MOTION_PROPS = new Set([
  "initial", "animate", "exit", "transition", "whileHover",
  "whileTap", "whileFocus", "whileInView", "viewport", "layout",
  "layoutId", "drag", "dragConstraints", "variants", "custom",
]);
vi.mock("motion/react", () => ({
  motion: new Proxy(
    {},
    {
      get: (_target, prop: string) =>
        ({ children, ...rest }: { children?: React.ReactNode } & Record<string, unknown>) => {
          const cleaned = Object.fromEntries(
            Object.entries(rest).filter(([k]) => !STRIPPED_MOTION_PROPS.has(k)),
          );
          return React.createElement(prop, cleaned, children);
        },
    },
  ),
  AnimatePresence: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
}));

vi.mock("@/lib/exporters/storyExporter", () => ({ exportUserStories: vi.fn() }));

const ROUNDS: ClarifyRound[] = [
  { round: 1, qa: [{ question_id: "q1", question_text: "Auth?", impact_level: "high", answer: "OAuth" }] },
];

const createObjectURL = vi.fn(() => "blob:mock");
const revokeObjectURL = vi.fn();

beforeEach(() => {
  createObjectURL.mockClear();
  revokeObjectURL.mockClear();
  // jsdom lacks URL.createObjectURL — install a spy so the downloadBlob path runs.
  (URL as unknown as { createObjectURL: typeof createObjectURL }).createObjectURL = createObjectURL;
  (URL as unknown as { revokeObjectURL: typeof revokeObjectURL }).revokeObjectURL = revokeObjectURL;
});

describe("FilesTab — Run input section", () => {
  it("renders prompt.md + clarifications.md when both are threaded", () => {
    render(<FilesTab workflowType={"prototype"} runInput={"Build a landing page."} clarifications={ROUNDS} />);
    expect(screen.getByText("Run input")).toBeInTheDocument();
    expect(screen.getByText("prompt.md")).toBeInTheDocument();
    expect(screen.getByText("clarifications.md")).toBeInTheDocument();
  });

  it("renders prompt.md but NOT clarifications.md when no rounds exist", () => {
    render(<FilesTab workflowType={"prototype"} runInput={"Build a landing page."} />);
    expect(screen.getByText("prompt.md")).toBeInTheDocument();
    expect(screen.queryByText("clarifications.md")).toBeNull();
  });

  it("downloads each run-input row via the downloadBlob path", () => {
    render(<FilesTab workflowType={"prototype"} runInput={"Build a landing page."} clarifications={ROUNDS} />);

    fireEvent.click(screen.getByRole("button", { name: /download prompt\.md/i }));
    expect(createObjectURL).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: /download clarifications\.md/i }));
    expect(createObjectURL).toHaveBeenCalledTimes(2);
  });

  it("shows NO 'Run input' section when neither prop is threaded (zero regression)", () => {
    render(<FilesTab workflowType={"user_stories"} userStoryContent={"# Heading\n\nbody"} />);
    // The existing final-output row still renders; there is no Run input section.
    expect(screen.getByText("heading.md")).toBeInTheDocument();
    expect(screen.queryByText("Run input")).toBeNull();
    expect(screen.queryByText("prompt.md")).toBeNull();
  });
});
