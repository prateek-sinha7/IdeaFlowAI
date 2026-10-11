import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { UserStoryPreview } from "./UserStoryPreview";

const BACKLOG = [
  "# Epic: Auth [P0]",
  "Users sign in securely.",
  "**Business Value:** Secure access",
  "",
  "## Story: Login",
  "**As a** user, **I want** to log in, **so that** I reach my data.",
  "**Story Points:** 5",
  "**Dependencies:** Story Setup",
  "- **Given** a registered user, **When** they submit valid credentials, **Then** they are signed in",
  "- [ ] Plain criterion",
  "",
  "## Story: Logout",
  "**Story Points:** 3",
  "**Dependencies:** None",
  "",
  "# Epic: Billing [P1]",
  "## Story: Invoices",
  "**Story Points:** 8",
  "",
  "# Epic: Docs",
  "**Priority:** Nice to have",
  "## Story: Readme",
  "",
].join("\n");

// Reads the numeric value shown above a stats-bar label.
function statValue(label: string): string {
  return screen.getByText(label).previousElementSibling?.textContent ?? "";
}

function setup(ui: React.ReactElement) {
  const user = userEvent.setup();
  const writeText = vi.spyOn(navigator.clipboard, "writeText");
  return { user, writeText, ...render(ui) };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("UserStoryPreview — empty and fallback states", () => {
  it.each([
    ["undefined", undefined],
    ["an empty string", ""],
  ])("shows the 'No User Stories Yet' placeholder when content is %s", (_l, content) => {
    render(<UserStoryPreview content={content} />);

    expect(screen.getByText("No User Stories Yet")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Copy MD/ })).not.toBeInTheDocument();
  });

  it("shows the raw markdown with a copy button when no epic can be parsed", () => {
    render(<UserStoryPreview content={"just free text\nwith no headings"} />);

    expect(screen.getByText(/just free text/)).toBeInTheDocument();
    expect(screen.queryByText("Product Backlog")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Copy MD/ })).toBeInTheDocument();
  });

  it("copies the raw markdown from the unparsed fallback view", async () => {
    const { user, writeText } = setup(<UserStoryPreview content={"free text only"} />);

    await user.click(screen.getByRole("button", { name: /Copy MD/ }));

    expect(writeText).toHaveBeenCalledWith("free text only");
    expect(await screen.findByRole("button", { name: /Copied/ })).toBeInTheDocument();
  });

  it("reports 'Copy failed' from the unparsed fallback view when the clipboard rejects", async () => {
    const { user, writeText } = setup(<UserStoryPreview content={"free text only"} />);
    writeText.mockRejectedValueOnce(new DOMException("denied"));

    await user.click(screen.getByRole("button", { name: /Copy MD/ }));

    expect(await screen.findByRole("button", { name: /Copy failed/ })).toBeInTheDocument();
  });
});

describe("UserStoryPreview — parsed backlog", () => {
  it("shows the backlog heading and the aggregate stats", () => {
    render(<UserStoryPreview content={BACKLOG} />);

    expect(screen.getByRole("heading", { level: 1, name: "Product Backlog" })).toBeInTheDocument();
    expect(statValue("Epics")).toBe("3");
    expect(statValue("Stories")).toBe("4");
    expect(statValue("Points")).toBe("16");
    expect(statValue("Sprints")).toBe("1");
  });

  it("counts a started second sprint once points exceed 30", () => {
    render(
      <UserStoryPreview content={"# Epic: Big\n## Story: Huge\n**Story Points:** 31\n"} />,
    );

    expect(statValue("Points")).toBe("31");
    expect(statValue("Sprints")).toBe("2");
  });

  it("reports one sprint and zero points for a backlog with no estimates", () => {
    render(<UserStoryPreview content={"# Epic: Empty\n## Story: Unestimated\n"} />);

    expect(statValue("Points")).toBe("0");
    expect(statValue("Sprints")).toBe("1");
  });

  it("shows a priority pill per bucket, treating unprioritised epics as nice-to-have", () => {
    render(<UserStoryPreview content={BACKLOG} />);

    expect(screen.getByText("1 Must-have")).toBeInTheDocument();
    expect(screen.getByText("1 Should-have")).toBeInTheDocument();
    expect(screen.getByText("1 Nice-to-have")).toBeInTheDocument();
  });

  it("omits priority pills for empty buckets", () => {
    render(<UserStoryPreview content={"# Epic: Only [P0]\n## Story: S\n"} />);

    expect(screen.getByText("1 Must-have")).toBeInTheDocument();
    expect(screen.queryByText(/Should-have/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Nice-to-have/)).not.toBeInTheDocument();
  });

  it("labels each epic with its priority badge, title, story count and business value", () => {
    render(<UserStoryPreview content={BACKLOG} />);

    const auth = screen.getByRole("button", { name: /Auth/ });
    expect(auth).toHaveTextContent("P0");
    expect(auth).toHaveTextContent("2 stories");
    expect(auth).toHaveTextContent("Secure access");
    expect(screen.getByRole("button", { name: /Billing/ })).toHaveTextContent("P1");
    expect(screen.getByRole("button", { name: /Docs/ })).toHaveTextContent("P2");
  });

  it("renders story numbering, title, points and the cleaned description", () => {
    render(<UserStoryPreview content={BACKLOG} />);

    expect(screen.getByText("1.1")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 3, name: "Login" })).toBeInTheDocument();
    expect(screen.getByText("5 SP")).toBeInTheDocument();
    expect(
      screen.getByText("As a user, I want to log in, so that I reach my data."),
    ).toBeInTheDocument();
  });

  it("shows a dependency except when it is 'None'", () => {
    render(<UserStoryPreview content={BACKLOG} />);

    expect(screen.getByText("Story Setup")).toBeInTheDocument();
    expect(screen.getAllByText("Depends on:")).toHaveLength(1);
  });

  it("renders acceptance criteria with Given/When/Then emphasised and checkbox prefixes removed", () => {
    render(<UserStoryPreview content={BACKLOG} />);

    expect(screen.getByText("Acceptance Criteria")).toBeInTheDocument();
    expect(screen.getByText("Given").tagName).toBe("SPAN");
    expect(screen.getByText("When").tagName).toBe("SPAN");
    expect(screen.getByText("Then").tagName).toBe("SPAN");
    expect(screen.getByText("Plain criterion")).toBeInTheDocument();
  });

  it("emphasises plain-text Given/When/Then keywords as well as bold ones", () => {
    render(
      <UserStoryPreview
        content={"# Epic: E\n## Story: S\n- Given a cart, When paying, Then a receipt appears\n"}
      />,
    );

    expect(screen.getByText("Given").tagName).toBe("SPAN");
    expect(screen.getByText("When").tagName).toBe("SPAN");
    expect(screen.getByText("Then").tagName).toBe("SPAN");
  });
});

describe("UserStoryPreview — epic expansion", () => {
  it("collapses and re-expands an epic's stories from its header", async () => {
    const { user } = setup(<UserStoryPreview content={BACKLOG} />);
    expect(screen.getByRole("heading", { level: 3, name: "Login" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Auth/ }));
    expect(screen.queryByRole("heading", { level: 3, name: "Login" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Auth/ }));
    expect(screen.getByRole("heading", { level: 3, name: "Login" })).toBeInTheDocument();
  });

  it("starts the seventh and later epics collapsed and expands them on demand", async () => {
    const epics = Array.from({ length: 7 }, (_, i) => `# Epic: Epic ${i + 1}\n## Story: Story ${i + 1}\n`);
    const { user } = setup(<UserStoryPreview content={epics.join("\n")} />);

    expect(screen.getByRole("heading", { level: 3, name: "Story 6" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 3, name: "Story 7" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Epic 7/ }));

    expect(screen.getByRole("heading", { level: 3, name: "Story 7" })).toBeInTheDocument();
  });
});

describe("UserStoryPreview — copy", () => {
  it("copies the markdown source and confirms with 'Copied'", async () => {
    const { user, writeText } = setup(<UserStoryPreview content={BACKLOG} />);

    await user.click(screen.getByRole("button", { name: /Copy MD/ }));

    expect(writeText).toHaveBeenCalledWith(BACKLOG);
    expect(await screen.findByRole("button", { name: /Copied/ })).toBeInTheDocument();
  });

  it("reports 'Copy failed' when the clipboard write rejects", async () => {
    const { user, writeText } = setup(<UserStoryPreview content={BACKLOG} />);
    writeText.mockRejectedValueOnce(new DOMException("denied"));

    await user.click(screen.getByRole("button", { name: /Copy MD/ }));

    expect(await screen.findByRole("button", { name: /Copy failed/ })).toBeInTheDocument();
  });
});

describe("UserStoryPreview — revision bar", () => {
  it("does not render the revision bar when onRevise is not provided", () => {
    render(<UserStoryPreview content={BACKLOG} />);

    expect(screen.queryByLabelText("Revision instructions")).not.toBeInTheDocument();
  });

  it("disables Revise until the input has non-whitespace text", async () => {
    const { user } = setup(<UserStoryPreview content={BACKLOG} onRevise={vi.fn()} />);
    const revise = screen.getByRole("button", { name: /Revise/ });

    expect(revise).toBeDisabled();
    await user.type(screen.getByLabelText("Revision instructions"), "  ");
    expect(revise).toBeDisabled();
    await user.type(screen.getByLabelText("Revision instructions"), "x");
    expect(revise).toBeEnabled();
  });

  it("submits the trimmed instruction on click and clears the input", async () => {
    const onRevise = vi.fn();
    const { user } = setup(<UserStoryPreview content={BACKLOG} onRevise={onRevise} />);
    const input = screen.getByLabelText("Revision instructions");

    await user.type(input, "  add password reset  ");
    await user.click(screen.getByRole("button", { name: /Revise/ }));

    expect(onRevise).toHaveBeenCalledWith("add password reset");
    expect(input).toHaveValue("");
  });

  it("submits on Enter and ignores Enter on a blank input", async () => {
    const onRevise = vi.fn();
    const { user } = setup(<UserStoryPreview content={BACKLOG} onRevise={onRevise} />);
    const input = screen.getByLabelText("Revision instructions");

    await user.type(input, "  {Enter}");
    expect(onRevise).not.toHaveBeenCalled();

    await user.type(input, "drop NFR epic{Enter}");
    expect(onRevise).toHaveBeenCalledTimes(1);
    expect(onRevise).toHaveBeenCalledWith("drop NFR epic");
  });
});

describe("UserStoryPreview — unsafe model output in acceptance criteria", () => {
  function renderWithCriterion(criterion: string) {
    return render(
      <UserStoryPreview content={`# Epic: E\n## Story: S\n- ${criterion}\n`} />,
    );
  }

  afterEach(() => {
    delete (window as unknown as Record<string, unknown>).__pwned;
  });

  it("strips a <script> tag so no script element is created", () => {
    const { container } = renderWithCriterion("<script>window.__pwned = true;</script>ok");

    expect(container.querySelector("script")).toBeNull();
    expect((window as unknown as Record<string, unknown>).__pwned).toBeUndefined();
  });

  it("strips an anchor tag carrying a javascript: URL", () => {
    const { container } = renderWithCriterion('<a href="javascript:alert(1)">click</a> done');

    expect(container.querySelector("a")).toBeNull();
    expect(container.querySelector('[href^="javascript:" i]')).toBeNull();
  });

  it("shows a markdown-style javascript: link as plain text, not as a link", () => {
    renderWithCriterion("[click](javascript:alert(1))");

    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(screen.getByText("[click](javascript:alert(1))")).toBeInTheDocument();
  });

  it("strips an <img onerror> payload", () => {
    const { container } = renderWithCriterion('<img src=x onerror="window.__pwned=true"> after');

    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("[onerror]")).toBeNull();
  });

  // SUSPECTED BUG (see report): the tag-strip regex /<[^>]*>/ needs a closing '>'.
  // An UNTERMINATED tag survives, and the later Given/When/Then replacement injects
  // a '<span ...>' whose '>' closes it — producing a live <img onerror>. vitest's
  // it.fails is the repo's xfail idiom: it passes while the defect exists and turns
  // red the moment the sanitiser is fixed, prompting removal of the marker.
  it.fails("does not create a live element from an unterminated tag (sanitiser bypass)", () => {
    const { container } = renderWithCriterion("<img src=x onerror=alert(1) Given");

    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("[onerror]")).toBeNull();
  });
});
