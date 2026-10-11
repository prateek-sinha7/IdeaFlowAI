/**
 * WorkflowPickerModal — target picker for a `trigger: "workflow"` conditional
 * outcome (spec 014 / R-22).
 *
 * Contract pinned here:
 *   - group rules: System = system ∧ launchable ∧ ¬beta, Revision = system `*_revision`,
 *     Yours = user, All = their concatenation
 *   - opens on the tab that holds the current value
 *   - a click only HIGHLIGHTS a row; "Pick workflow" (or a double-click) commits
 *   - Esc / backdrop / Close cancel; clicks inside the dialog do not
 *   - loading / empty / no-match states
 *
 * Only a browser API jsdom lacks (`scrollIntoView`) is stubbed.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { WorkflowPickerModal } from "./WorkflowPickerModal";
import type { WorkflowPickerOption } from "./CanvasNode";

function option(overrides: Partial<WorkflowPickerOption> & { id: string }): WorkflowPickerOption {
  return {
    name: overrides.id,
    kind: "system",
    launchable: true,
    isBeta: false,
    ...overrides,
  };
}

const USER_STORIES = option({
  id: "user_stories",
  name: "User Stories",
  shortName: "US",
  description: "Turns a brief into a backlog",
  stepCount: 6,
  icon: "FileText",
});
const PPT = option({ id: "ppt", name: "Slide Deck", stepCount: 1, icon: "Presentation" });
const BETA = option({ id: "beta_flow", name: "Beta Flow", isBeta: true });
const HIDDEN = option({ id: "hidden_flow", name: "Hidden Flow", launchable: false });
const REVISION = option({
  id: "ppt_revision",
  name: "Slide Deck Revision",
  launchable: false,
  description: "Revises an existing deck",
});
const MINE = option({
  id: "my_flow",
  name: "My Flow",
  kind: "user",
  description: "Personal automation",
  stepCount: 0,
});

const ALL_OPTIONS = [USER_STORIES, PPT, BETA, HIDDEN, REVISION, MINE];

let scrollIntoView: ReturnType<typeof vi.fn>;

beforeEach(() => {
  scrollIntoView = vi.fn();
  Object.defineProperty(Element.prototype, "scrollIntoView", {
    configurable: true,
    writable: true,
    value: scrollIntoView,
  });
});

afterEach(() => {
  // jsdom ships no scrollIntoView; remove the stub so tests stay independent.
  delete (Element.prototype as unknown as Record<string, unknown>).scrollIntoView;
});

function renderPicker(
  props: Partial<React.ComponentProps<typeof WorkflowPickerModal>> = {},
) {
  const onSelect = vi.fn();
  const onCancel = vi.fn();
  const utils = render(
    <WorkflowPickerModal
      value=""
      workflows={ALL_OPTIONS}
      onSelect={onSelect}
      onCancel={onCancel}
      {...props}
    />,
  );
  return { onSelect, onCancel, ...utils };
}

function chipCount(id: string): string {
  const chip = screen.getByTestId(`workflow-picker-chip-${id}`);
  return chip.lastElementChild?.textContent ?? "";
}

describe("WorkflowPickerModal — structure and accessibility", () => {
  it("renders a named dialog portalled to document.body with the search box focused", () => {
    const { container } = renderPicker();

    const dialog = screen.getByRole("dialog", { name: "Pick a workflow" });
    expect(dialog).toBeInTheDocument();
    expect(container).not.toContainElement(dialog);
    expect(document.body).toContainElement(dialog);
    expect(screen.getByRole("textbox", { name: "Search workflows" })).toHaveFocus();
  });

  it("shows each group chip with its member count (beta and non-launchable excluded from System)", () => {
    renderPicker();

    // System: user_stories + ppt (beta_flow is beta, hidden_flow is not launchable)
    expect(chipCount("system")).toBe("2");
    expect(chipCount("revision")).toBe("1");
    expect(chipCount("user")).toBe("1");
    expect(chipCount("all")).toBe("4");
  });
});

describe("WorkflowPickerModal — opening tab", () => {
  it("opens on All when no value is set", () => {
    renderPicker({ value: "" });

    expect(screen.getByTestId("workflow-picker-row-user_stories")).toBeInTheDocument();
    expect(screen.getByTestId("workflow-picker-row-ppt_revision")).toBeInTheDocument();
    expect(screen.getByTestId("workflow-picker-row-my_flow")).toBeInTheDocument();
  });

  it("opens on System when the current value is a system workflow", () => {
    renderPicker({ value: "ppt" });

    expect(screen.getByTestId("workflow-picker-row-ppt")).toBeInTheDocument();
    expect(screen.queryByTestId("workflow-picker-row-ppt_revision")).not.toBeInTheDocument();
    expect(screen.queryByTestId("workflow-picker-row-my_flow")).not.toBeInTheDocument();
  });

  it("opens on Revision when the current value is a revision workflow", () => {
    renderPicker({ value: "ppt_revision" });

    expect(screen.getByTestId("workflow-picker-row-ppt_revision")).toBeInTheDocument();
    expect(screen.queryByTestId("workflow-picker-row-user_stories")).not.toBeInTheDocument();
  });

  it("opens on Yours when the current value is a user workflow", () => {
    renderPicker({ value: "my_flow" });

    expect(screen.getByTestId("workflow-picker-row-my_flow")).toBeInTheDocument();
    expect(screen.queryByTestId("workflow-picker-row-user_stories")).not.toBeInTheDocument();
  });

  it("opens on System and echoes the raw id in the footer when the value matches no known workflow", () => {
    renderPicker({ value: "deleted_flow" });

    // System tab is showing, and nothing in it is highlighted.
    expect(screen.getByTestId("workflow-picker-row-user_stories")).toBeInTheDocument();
    // The footer falls back to the id because the name is unresolvable.
    expect(screen.getByText("deleted_flow")).toBeInTheDocument();
    expect(screen.getByTestId("workflow-picker-confirm")).toBeEnabled();
  });

  it("scrolls the currently-selected row into view on open", () => {
    renderPicker({ value: "ppt" });

    expect(scrollIntoView).toHaveBeenCalledWith({ block: "nearest" });
  });

  it("does not scroll when nothing is selected", () => {
    renderPicker({ value: "" });

    expect(scrollIntoView).not.toHaveBeenCalled();
  });
});

describe("WorkflowPickerModal — row content", () => {
  it("renders name, short name, description and a plural step count", () => {
    renderPicker({ value: "" });

    const row = screen.getByTestId("workflow-picker-row-user_stories");
    expect(within(row).getByText("User Stories")).toBeInTheDocument();
    expect(within(row).getByText("US")).toBeInTheDocument();
    expect(within(row).getByText("Turns a brief into a backlog")).toBeInTheDocument();
    expect(within(row).getByText("6 steps")).toBeInTheDocument();
  });

  it("uses the singular for exactly one step", () => {
    renderPicker({ value: "" });

    expect(
      within(screen.getByTestId("workflow-picker-row-ppt")).getByText("1 step"),
    ).toBeInTheDocument();
  });

  it("renders '0 steps' for a zero count and omits the line when stepCount is absent", () => {
    renderPicker({ value: "" });

    expect(
      within(screen.getByTestId("workflow-picker-row-my_flow")).getByText("0 steps"),
    ).toBeInTheDocument();
    expect(
      within(screen.getByTestId("workflow-picker-row-ppt_revision")).queryByText(/step/),
    ).not.toBeInTheDocument();
  });

  it("omits the short-name badge and description when the option has neither", () => {
    renderPicker({ value: "" });

    const row = screen.getByTestId("workflow-picker-row-ppt");
    expect(within(row).getByText("Slide Deck")).toBeInTheDocument();
    expect(within(row).queryByText("US")).not.toBeInTheDocument();
    // Only the name and the step line are text in this row.
    expect(row).toHaveTextContent(/^Slide Deck1 step$/);
  });

  it("falls back to a generic icon for an unrecognised manifest icon name", () => {
    renderPicker({
      value: "",
      workflows: [option({ id: "mystery", name: "Mystery", icon: "NotARealIcon" })],
    });

    expect(screen.getByTestId("workflow-picker-row-mystery")).toBeInTheDocument();
  });
});

describe("WorkflowPickerModal — tab switching", () => {
  it("switches to the Yours tab and lists only user workflows", async () => {
    const user = userEvent.setup();
    renderPicker({ value: "" });

    await user.click(screen.getByTestId("workflow-picker-chip-user"));

    expect(screen.getByTestId("workflow-picker-row-my_flow")).toBeInTheDocument();
    expect(screen.queryByTestId("workflow-picker-row-user_stories")).not.toBeInTheDocument();
  });

  it("switches to the Revision tab and lists only revision workflows", async () => {
    const user = userEvent.setup();
    renderPicker({ value: "" });

    await user.click(screen.getByTestId("workflow-picker-chip-revision"));

    expect(screen.getByTestId("workflow-picker-row-ppt_revision")).toBeInTheDocument();
    expect(screen.queryByTestId("workflow-picker-row-ppt")).not.toBeInTheDocument();
  });

  it("never lists beta or non-launchable system workflows in any tab", async () => {
    const user = userEvent.setup();
    renderPicker({ value: "" });

    for (const id of ["all", "system", "revision", "user"]) {
      await user.click(screen.getByTestId(`workflow-picker-chip-${id}`));
      expect(screen.queryByTestId("workflow-picker-row-beta_flow")).not.toBeInTheDocument();
      expect(screen.queryByTestId("workflow-picker-row-hidden_flow")).not.toBeInTheDocument();
    }
  });

  it("resets the list scroll position to the top when the tab changes", async () => {
    const user = userEvent.setup();
    renderPicker({ value: "" });
    const list = screen
      .getByTestId("workflow-picker-row-user_stories")
      .closest<HTMLElement>(".overflow-y-auto")!;
    const writes: number[] = [];
    Object.defineProperty(list, "scrollTop", {
      configurable: true,
      get: () => 0,
      set: (v: number) => void writes.push(v),
    });

    await user.click(screen.getByTestId("workflow-picker-chip-user"));

    expect(writes).toEqual([0]);
  });
});

describe("WorkflowPickerModal — search", () => {
  it("filters by name, case-insensitively, and updates the per-tab counts", async () => {
    const user = userEvent.setup();
    renderPicker({ value: "" });

    await user.type(screen.getByRole("textbox", { name: "Search workflows" }), "SLIDE");

    expect(screen.getByTestId("workflow-picker-row-ppt")).toBeInTheDocument();
    expect(screen.getByTestId("workflow-picker-row-ppt_revision")).toBeInTheDocument();
    expect(screen.queryByTestId("workflow-picker-row-user_stories")).not.toBeInTheDocument();
    expect(chipCount("all")).toBe("2");
    expect(chipCount("system")).toBe("1");
    expect(chipCount("revision")).toBe("1");
    expect(chipCount("user")).toBe("0");
  });

  it("filters by id", async () => {
    const user = userEvent.setup();
    renderPicker({ value: "" });

    await user.type(screen.getByRole("textbox", { name: "Search workflows" }), "my_fl");

    expect(screen.getByTestId("workflow-picker-row-my_flow")).toBeInTheDocument();
    expect(screen.queryByTestId("workflow-picker-row-ppt")).not.toBeInTheDocument();
  });

  it("filters by description", async () => {
    const user = userEvent.setup();
    renderPicker({ value: "" });

    await user.type(screen.getByRole("textbox", { name: "Search workflows" }), "backlog");

    expect(screen.getByTestId("workflow-picker-row-user_stories")).toBeInTheDocument();
    expect(screen.queryByTestId("workflow-picker-row-ppt")).not.toBeInTheDocument();
  });

  it("ignores surrounding whitespace in the query", async () => {
    const user = userEvent.setup();
    renderPicker({ value: "" });

    await user.type(screen.getByRole("textbox", { name: "Search workflows" }), "  ppt  ");

    expect(screen.getByTestId("workflow-picker-row-ppt")).toBeInTheDocument();
  });

  it("shows a 'No match' message quoting the trimmed query when nothing matches", async () => {
    const user = userEvent.setup();
    renderPicker({ value: "" });

    await user.type(screen.getByRole("textbox", { name: "Search workflows" }), " zzz ");

    expect(screen.getByText("No match for “zzz” in this group.")).toBeInTheDocument();
  });

  it("keeps matches in other tabs reachable while the current tab has none", async () => {
    const user = userEvent.setup();
    renderPicker({ value: "ppt" }); // System tab
    await user.type(screen.getByRole("textbox", { name: "Search workflows" }), "personal");

    expect(screen.getByText(/No match for “personal”/)).toBeInTheDocument();
    expect(chipCount("user")).toBe("1");

    await user.click(screen.getByTestId("workflow-picker-chip-user"));
    expect(screen.getByTestId("workflow-picker-row-my_flow")).toBeInTheDocument();
  });
});

describe("WorkflowPickerModal — loading and empty states", () => {
  it("shows a loading message and a disabled confirm button while workflows is null", () => {
    renderPicker({ workflows: null });

    expect(screen.getByText("Loading workflows…")).toBeInTheDocument();
    expect(screen.getByText("Nothing selected yet.")).toBeInTheDocument();
    expect(screen.getByTestId("workflow-picker-confirm")).toBeDisabled();
  });

  it("shows 'Nothing in this group yet.' when the catalogue is empty", () => {
    renderPicker({ workflows: [] });

    expect(screen.getByText("Nothing in this group yet.")).toBeInTheDocument();
    expect(chipCount("all")).toBe("0");
  });

  it("shows 'Nothing in this group yet.' for a group with no members", async () => {
    const user = userEvent.setup();
    renderPicker({ workflows: [USER_STORIES], value: "" });

    await user.click(screen.getByTestId("workflow-picker-chip-user"));

    expect(screen.getByText("Nothing in this group yet.")).toBeInTheDocument();
  });
});

describe("WorkflowPickerModal — selection", () => {
  it("highlights a row and shows its name in the footer without committing", async () => {
    const user = userEvent.setup();
    const { onSelect } = renderPicker({ value: "" });
    expect(screen.getByText("Nothing selected yet.")).toBeInTheDocument();

    await user.click(screen.getByTestId("workflow-picker-row-ppt"));

    expect(screen.queryByText("Nothing selected yet.")).not.toBeInTheDocument();
    const footerName = screen
      .getByTestId("workflow-picker-confirm")
      .previousElementSibling as HTMLElement;
    expect(footerName).toHaveTextContent("Slide Deck");
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("commits the highlighted row only when 'Pick workflow' is clicked", async () => {
    const user = userEvent.setup();
    const { onSelect } = renderPicker({ value: "" });

    await user.click(screen.getByTestId("workflow-picker-row-my_flow"));
    await user.click(screen.getByRole("button", { name: "Pick workflow" }));

    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect).toHaveBeenCalledWith("my_flow");
  });

  it("commits the pre-selected value without further interaction", async () => {
    const user = userEvent.setup();
    const { onSelect } = renderPicker({ value: "ppt" });

    await user.click(screen.getByRole("button", { name: "Pick workflow" }));

    expect(onSelect).toHaveBeenCalledWith("ppt");
  });

  it("moves the highlight to the most recently clicked row", async () => {
    const user = userEvent.setup();
    const { onSelect } = renderPicker({ value: "" });

    await user.click(screen.getByTestId("workflow-picker-row-ppt"));
    await user.click(screen.getByTestId("workflow-picker-row-user_stories"));
    await user.click(screen.getByRole("button", { name: "Pick workflow" }));

    expect(onSelect).toHaveBeenCalledWith("user_stories");
  });

  it("commits immediately on double-click", async () => {
    const user = userEvent.setup();
    const { onSelect } = renderPicker({ value: "" });

    await user.dblClick(screen.getByTestId("workflow-picker-row-ppt"));

    expect(onSelect).toHaveBeenCalledWith("ppt");
  });

  it("does not commit when the confirm button is disabled (no selection)", async () => {
    const user = userEvent.setup();
    const { onSelect } = renderPicker({ value: "" });

    await user.click(screen.getByTestId("workflow-picker-confirm"));

    expect(onSelect).not.toHaveBeenCalled();
  });

  it("keeps the highlight when the user changes tab", async () => {
    const user = userEvent.setup();
    const { onSelect } = renderPicker({ value: "" });
    await user.click(screen.getByTestId("workflow-picker-row-ppt"));

    await user.click(screen.getByTestId("workflow-picker-chip-user"));
    await user.click(screen.getByRole("button", { name: "Pick workflow" }));

    expect(onSelect).toHaveBeenCalledWith("ppt");
  });
});

describe("WorkflowPickerModal — dismissal", () => {
  it("cancels on Escape", async () => {
    const user = userEvent.setup();
    const { onCancel, onSelect } = renderPicker();

    await user.keyboard("{Escape}");

    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("ignores other keys", async () => {
    const user = userEvent.setup();
    const { onCancel } = renderPicker();

    await user.keyboard("a{Enter}{Tab}");

    expect(onCancel).not.toHaveBeenCalled();
  });

  it("stops listening for Escape after unmount", async () => {
    const user = userEvent.setup();
    const { onCancel, unmount } = renderPicker();

    unmount();
    await user.keyboard("{Escape}");

    expect(onCancel).not.toHaveBeenCalled();
  });

  it("cancels from the Close button", async () => {
    const user = userEvent.setup();
    const { onCancel } = renderPicker();

    await user.click(screen.getByRole("button", { name: "Close" }));

    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("cancels when the backdrop is clicked", async () => {
    const user = userEvent.setup();
    const { onCancel } = renderPicker();
    const backdrop = screen.getByRole("dialog").parentElement as HTMLElement;

    await user.click(backdrop);

    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("does not cancel when clicking inside the dialog", async () => {
    const user = userEvent.setup();
    const { onCancel } = renderPicker();

    await user.click(screen.getByText("Pick a workflow", { selector: "p" }));
    await user.click(screen.getByTestId("workflow-picker-chip-user"));

    expect(onCancel).not.toHaveBeenCalled();
  });
});
