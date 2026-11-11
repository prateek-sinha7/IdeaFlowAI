import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useRef, useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { BUILDER_PANEL_ID, BuilderPanel, DOCK_MIN_WIDTH_PX } from "./BuilderPanel";
import type { BuilderPanelHeaderProps } from "./BuilderPanelHeader";

/** jsdom has no `matchMedia`; this stub answers the dock query for a given viewport width. */
function stubViewport(widthPx: number) {
  vi.stubGlobal(
    "matchMedia",
    (query: string) => ({
      matches: widthPx >= DOCK_MIN_WIDTH_PX && query.includes(`${DOCK_MIN_WIDTH_PX}px`),
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }),
  );
}

const HEADER: Omit<BuilderPanelHeaderProps, "onCollapse"> = {
  sessions: [],
  currentSessionId: null,
  hasMoreSessions: false,
  onShowMore: vi.fn(),
  onSelectSession: vi.fn(),
  onDeleteSession: vi.fn(),
  onNewConversation: vi.fn(),
};

/** A host with an AI button that opens and closes the panel, like the Composer does. */
function Host({
  onCollapse,
  startCollapsed = false,
  withMessageBox = false,
}: {
  onCollapse?: () => void;
  startCollapsed?: boolean;
  withMessageBox?: boolean;
}) {
  const [collapsed, setCollapsed] = useState(startCollapsed);
  const aiButton = useRef<HTMLButtonElement>(null);
  return (
    <div>
      <button ref={aiButton} type="button" onClick={() => setCollapsed(false)}>
        Build with AI
      </button>
      <BuilderPanel
        collapsed={collapsed}
        header={HEADER}
        onCollapse={() => {
          setCollapsed(true);
          onCollapse?.();
        }}
        onExpand={() => setCollapsed(false)}
        returnFocusRef={aiButton}
      >
        <input aria-label="Body field" />
        {withMessageBox ? <textarea aria-label="Message to the builder" /> : null}
      </BuilderPanel>
    </div>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("BuilderPanel at 1280 px and wider", () => {
  beforeEach(() => stubViewport(1440));

  it("docks as a 360 px complementary column with no backdrop", () => {
    render(<Host />);
    const panel = screen.getByRole("complementary", { name: "AI workflow builder" });
    expect(panel).toHaveClass("w-[360px]");
    expect(panel).not.toHaveAttribute("aria-modal");
    expect(screen.queryByTestId("builder-backdrop")).toBeNull();
    expect(screen.getByRole("textbox", { name: "Body field" })).toBeInTheDocument();
  });

  it("carries the id the AI button names in aria-controls", () => {
    render(<Host />);
    expect(screen.getByRole("complementary", { name: "AI workflow builder" })).toHaveAttribute(
      "id",
      BUILDER_PANEL_ID,
    );
  });

  it("puts the cursor in the message box when it opens", async () => {
    const user = userEvent.setup();
    render(<Host startCollapsed withMessageBox />);
    await user.click(screen.getByRole("button", { name: "Build with AI" }));
    expect(screen.getByRole("textbox", { name: "Message to the builder" })).toHaveFocus();
  });

  it("leaves focus where it was when it opens without a message box", async () => {
    const user = userEvent.setup();
    render(<Host startCollapsed />);
    await user.click(screen.getByRole("button", { name: "Build with AI" }));
    expect(screen.getByRole("button", { name: "Build with AI" })).toHaveFocus();
  });

  it("does not collapse on Escape", async () => {
    const user = userEvent.setup();
    const onCollapse = vi.fn();
    render(<Host onCollapse={onCollapse} />);
    screen.getByRole("textbox", { name: "Body field" }).focus();
    await user.keyboard("{Escape}");
    expect(onCollapse).not.toHaveBeenCalled();
  });

  it("drops the panel when collapsed and brings it back from the AI button", async () => {
    const user = userEvent.setup();
    render(<Host />);
    await user.click(screen.getByRole("button", { name: "Collapse builder panel" }));
    expect(screen.queryByRole("complementary")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Build with AI" }));
    expect(screen.getByRole("complementary", { name: "AI workflow builder" })).toBeInTheDocument();
  });

  it("leaves a rail with an open icon when collapsed and reopens the panel from it", async () => {
    const user = userEvent.setup();
    render(<Host />);
    expect(screen.queryByTestId("builder-collapsed-rail")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Collapse builder panel" }));
    expect(screen.getByTestId("builder-collapsed-rail")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Open builder panel" }));
    expect(screen.getByRole("complementary", { name: "AI workflow builder" })).toBeInTheDocument();
    expect(screen.queryByTestId("builder-collapsed-rail")).toBeNull();
  });

  it("returns focus to the AI button when the panel closes", async () => {
    const user = userEvent.setup();
    render(<Host />);
    await user.click(screen.getByRole("button", { name: "Collapse builder panel" }));
    expect(screen.getByRole("button", { name: "Build with AI" })).toHaveFocus();
  });
});

describe("BuilderPanel below 1280 px", () => {
  // 1100 px docked under the old 1024 px threshold; it must overlay now.
  beforeEach(() => stubViewport(1100));

  it("is a modal overlay with a backdrop and moves focus inside", () => {
    render(<Host />);
    const panel = screen.getByRole("dialog", { name: "AI workflow builder" });
    expect(panel).toHaveAttribute("aria-modal", "true");
    expect(screen.getByTestId("builder-backdrop")).toBeInTheDocument();
    expect(panel).toContainElement(document.activeElement as HTMLElement);
  });

  it("collapses on a backdrop click", async () => {
    const user = userEvent.setup();
    const onCollapse = vi.fn();
    render(<Host onCollapse={onCollapse} />);
    await user.click(screen.getByTestId("builder-backdrop"));
    expect(onCollapse).toHaveBeenCalledOnce();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("collapses on Escape and returns focus to the AI button", async () => {
    const user = userEvent.setup();
    const onCollapse = vi.fn();
    render(<Host onCollapse={onCollapse} />);
    screen.getByRole("textbox", { name: "Body field" }).focus();
    await user.keyboard("{Escape}");
    expect(onCollapse).toHaveBeenCalledOnce();
    expect(screen.getByRole("button", { name: "Build with AI" })).toHaveFocus();
  });

  it("traps Tab inside the panel, wrapping from the last control to the first", async () => {
    const user = userEvent.setup();
    render(<Host />);
    const panel = screen.getByRole("dialog", { name: "AI workflow builder" });
    const body = screen.getByRole("textbox", { name: "Body field" });
    body.focus();
    await user.tab();
    expect(panel).toContainElement(document.activeElement as HTMLElement);
    expect(document.activeElement).toBe(
      panel.querySelector("button"), // the first focusable control: the Conversations menu
    );
  });

  it("wraps Shift+Tab from the first control to the last", async () => {
    const user = userEvent.setup();
    render(<Host />);
    const panel = screen.getByRole("dialog", { name: "AI workflow builder" });
    const first = panel.querySelector<HTMLElement>("button");
    first?.focus();
    await user.tab({ shift: true });
    expect(screen.getByRole("textbox", { name: "Body field" })).toHaveFocus();
  });
});
