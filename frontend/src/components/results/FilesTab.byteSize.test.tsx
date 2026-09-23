import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";

// ─────────────────────────────────────────────────────────────────
// ISS-351 — every FilesTab size label calls formatSize(content.length),
// where content is a JS string. String.prototype.length counts UTF-16 code
// units, not UTF-8 bytes, so a file whose content has multi-byte UTF-8
// characters (em dashes, arrows) is shown SMALLER than the byte size the
// Download button actually delivers. This proves the "Run input" prompt.md
// row's size label matches the true UTF-8 byte count, not the char count.
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

import { FilesTab } from "./FilesTab";

beforeEach(() => {
  (URL as unknown as { createObjectURL: () => string }).createObjectURL = () => "blob:mock";
  (URL as unknown as { revokeObjectURL: () => void }).revokeObjectURL = () => {};
});

// Em dash (—) is 1 UTF-16 code unit but 3 UTF-8 bytes; right-arrow (→) is the
// same. Content stays under 1024 bytes AND under 1024 chars so both the
// buggy (char) and correct (byte) computation land in formatSize's "B" branch
// — the two numbers differ but the unit suffix does not, isolating the defect
// to the number itself.
const CONTENT = "Build a landing page — fast → ship it.";

describe("FilesTab size labels — ISS-351", () => {
  it("prompt.md's declared size matches its true UTF-8 byte count, not its UTF-16 char count", () => {
    const trueBytes = new TextEncoder().encode(CONTENT).length;
    const charCount = CONTENT.length;
    expect(trueBytes).not.toBe(charCount); // sanity: the content actually exercises the bug

    render(<FilesTab workflowType="prototype" runInput={CONTENT} />);

    expect(screen.getByText("prompt.md")).toBeInTheDocument();
    // Today this renders `${charCount} B` (e.g. "38 B" instead of the true "41 B").
    expect(screen.getByText(`${trueBytes} B`)).toBeInTheDocument();
  });
});
