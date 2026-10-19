import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

// ─────────────────────────────────────────────────────────────────────────────
// RunHeader (Phase 39, RUNUI-06/07 → Phase U task U1) — the mock's right-column
// header bar across the settled / live / failed states. Isolated component
// specs: no PreviewPanel, no network. Asserts the state-driven composition +
// the client-only Share (ND-H) + the Version menu wiring (FR-038/043: tag-based
// refs; task U1: one selector for the whole run, usable in every run state,
// no restore).
// ─────────────────────────────────────────────────────────────────────────────

import { RunHeader } from "./RunHeader";
import * as api from "@/lib/api";

beforeEach(() => {
  // A clipboard spy so the client-only Share path is observable.
  Object.assign(navigator, { clipboard: { writeText: vi.fn().mockResolvedValue(undefined) } });
  // Mock the API module
  vi.resetAllMocks();
});

describe("RunHeader — settled state", () => {
  it("renders the Version menu + Share + Download; hides the status badge", async () => {
    vi.spyOn(api, "getToken").mockReturnValue("test-token");
    vi.spyOn(api, "getRunSandboxRefs").mockResolvedValue(["v1", "v2"]);

    render(
      <RunHeader
        runState="complete"
        activeRunId="r1"
        versionLabel="v2"
        onSelectVersion={() => {}}
        onShare={() => {}}
        onDownload={() => {}}
        canDownload
      />,
    );

    // Wait for tags to be fetched so the menu renders
    await waitFor(() => {
      expect(api.getRunSandboxRefs).toHaveBeenCalled();
    });

    // The chip text is the bare live label — task U1 drops the "Version " prefix.
    // (Accessible name also carries the trailing "▾" indicator.)
    expect(screen.getByRole("button", { name: /^v2\b/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Share this run/ })).toBeEnabled();
    expect(screen.getByRole("button", { name: /Download the deliverable/ })).toBeEnabled();
    // No live status badge in the settled state.
    expect(screen.queryByText(/streaming/i)).toBeNull();
    expect(screen.queryByText(/Run failed/i)).toBeNull();
  });

  it("Share button opens popover (no runId → legacy onShare path)", async () => {
    const onShare = vi.fn();
    vi.spyOn(api, "getToken").mockReturnValue("test-token");
    vi.spyOn(api, "getRunSandboxRefs").mockResolvedValue(["v1", "v2"]);

    render(
      <RunHeader runState="complete" activeRunId="r1" versionLabel="v2" onShare={onShare} />,
    );

    // Wait for tags to be fetched
    await waitFor(() => {
      expect(api.getRunSandboxRefs).toHaveBeenCalled();
    });

    // Wait for the Share button to be available and click it
    await waitFor(() => {
      const shareBtn = screen.getByRole("button", { name: /Share this run/ });
      expect(shareBtn).toBeEnabled();
      fireEvent.click(shareBtn);
    });

    // Popover opens — shows share panel heading.
    expect(screen.getByText(/Share deliverable/i)).toBeInTheDocument();
  });

  // ── QA-PS-058 — "Latest (live)" means ONE thing: the UNCOMMITTED working
  // tree. The single test that stood here asserted it as the unconditional
  // first option, which was correct for the pre-QA-PS-058 behaviour and is
  // deliberately revised (not deleted) into the three states of the new rule —
  // its callback contract (tag string / null) is kept in the in-flight case.
  it("in flight: Latest (live) is the first option, newest tag next; picking a tag/Latest drives onSelectVersion with the tag string / null", async () => {
    const onSelectVersion = vi.fn();
    vi.spyOn(api, "getToken").mockReturnValue("test-token");
    vi.spyOn(api, "getRunSandboxRefs").mockResolvedValue(["v1", "v2"]);

    render(
      <RunHeader
        runState="building"
        activeRunId="r1"
        versionLabel="v3"
        latestVersionTag={null}
        latestVersionInFlight
        onSelectVersion={onSelectVersion}
      />,
    );

    // Wait for tags to be fetched
    await waitFor(() => {
      expect(api.getRunSandboxRefs).toHaveBeenCalledWith("test-token", "r1");
    });

    // Open the menu by clicking the version chip.
    const versionButton = screen.getByRole("button", { name: /^v3 draft\b/ });
    fireEvent.click(versionButton);

    await waitFor(() => {
      expect(screen.getAllByRole("option")).toHaveLength(3);
    });
    const options = screen.getAllByRole("option");
    expect(options[0]).toHaveTextContent("Latest (live)");
    // Newest tag first after "Latest (live)".
    expect(options[1]).toHaveTextContent("v2");
    expect(options[2]).toHaveTextContent("v1");
    // No selectedRef prop supplied → live/latest is the current selection.
    expect(options[0].getAttribute("aria-selected")).toBe("true");
    // Work still in flight is not work that was never captured.
    expect(screen.queryByText(/never captured/i)).toBeNull();

    // Choosing a tag passes the tag string.
    fireEvent.click(screen.getByRole("option", { name: "v1" }));
    expect(onSelectVersion).toHaveBeenCalledWith("v1");

    // Choosing "Latest (live)" passes null.
    fireEvent.click(versionButton);
    fireEvent.click(screen.getByRole("option", { name: "Latest (live)" }));
    expect(onSelectVersion).toHaveBeenLastCalledWith(null);
  });

  it("settled + newest member tagged: NO Latest (live) — tags only, newest first (QA-PS-058)", async () => {
    vi.spyOn(api, "getToken").mockReturnValue("test-token");
    vi.spyOn(api, "getRunSandboxRefs").mockResolvedValue(["v1", "v2"]);

    render(
      <RunHeader
        runState="complete"
        activeRunId="r1"
        versionLabel="v2"
        latestVersionTag="v2"
        onSelectVersion={() => {}}
      />,
    );

    await waitFor(() => expect(api.getRunSandboxRefs).toHaveBeenCalledWith("test-token", "r1"));

    fireEvent.click(screen.getByRole("button", { name: /^v2\b/ }));

    await waitFor(() => expect(screen.getAllByRole("option")).toHaveLength(2));
    const options = screen.getAllByRole("option");
    // Nothing is offered twice: the live tree IS v2's bytes here.
    expect(screen.queryByRole("option", { name: "Latest (live)" })).toBeNull();
    expect(options[0]).toHaveTextContent("v2");
    expect(options[1]).toHaveTextContent("v1");
    // …and v2 carries the selection the live entry used to carry.
    expect(options[0].getAttribute("aria-selected")).toBe("true");
  });

  it("settled + newest member NEVER tagged: Latest (live) STAYS and says so — the only route to that content (ISS-697)", async () => {
    vi.spyOn(api, "getToken").mockReturnValue("test-token");
    // The family has v1 and v2; only v1 ever got a tag (tag creation is
    // best-effort — engine.py:2349-2456 — so git_tag can stay NULL forever).
    vi.spyOn(api, "getRunSandboxRefs").mockResolvedValue(["v1"]);

    render(
      <RunHeader
        runState="complete"
        activeRunId="r1"
        versionLabel="v2"
        latestVersionTag={null}
        onSelectVersion={() => {}}
      />,
    );

    await waitFor(() => expect(api.getRunSandboxRefs).toHaveBeenCalledWith("test-token", "r1"));

    fireEvent.click(screen.getByRole("button", { name: /^v2\b/ }));

    await waitFor(() => expect(screen.getAllByRole("option")).toHaveLength(2));
    const options = screen.getAllByRole("option");
    expect(options[0]).toHaveTextContent("Latest (live)");
    expect(options[1]).toHaveTextContent("v1");
    expect(screen.getByText(/never captured/i)).toBeInTheDocument();
  });

  it("settled + the newest member's recorded tag is NOT in the sandbox's list: Latest (live) STAYS (ISS-697 mechanism 2)", async () => {
    vi.spyOn(api, "getToken").mockReturnValue("test-token");
    // The DB row claims v2, but the sandbox's own `git tag --list` lost it —
    // there is still nothing selectable that reaches that content.
    vi.spyOn(api, "getRunSandboxRefs").mockResolvedValue(["v1"]);

    render(
      <RunHeader
        runState="complete"
        activeRunId="r1"
        versionLabel="v2"
        latestVersionTag="v2"
        onSelectVersion={() => {}}
      />,
    );

    await waitFor(() => expect(api.getRunSandboxRefs).toHaveBeenCalledWith("test-token", "r1"));

    fireEvent.click(screen.getByRole("button", { name: /^v2\b/ }));

    await waitFor(() => expect(screen.getAllByRole("option")).toHaveLength(2));
    expect(screen.getAllByRole("option")[0]).toHaveTextContent("Latest (live)");
  });

  it("a pinned selectedRef shows 'Viewing {tag}' on the chip and marks that option selected", async () => {
    vi.spyOn(api, "getToken").mockReturnValue("test-token");
    vi.spyOn(api, "getRunSandboxRefs").mockResolvedValue(["v1", "v2"]);

    render(
      <RunHeader
        runState="complete"
        activeRunId="r1"
        versionLabel="v2"
        selectedRef="v1"
        onSelectVersion={() => {}}
      />,
    );

    await waitFor(() => expect(api.getRunSandboxRefs).toHaveBeenCalled());
    const chip = screen.getByRole("button", { name: /^Viewing v1\b/ });
    fireEvent.click(chip);
    const v1Option = screen.getByRole("option", { name: "v1" });
    expect(v1Option.getAttribute("aria-selected")).toBe("true");
  });

  it("the listbox is a descendant of the chip's relative-positioned wrapper (task U1 fix)", async () => {
    vi.spyOn(api, "getToken").mockReturnValue("test-token");
    vi.spyOn(api, "getRunSandboxRefs").mockResolvedValue(["v1"]);

    render(<RunHeader runState="complete" activeRunId="r1" versionLabel="v1" onSelectVersion={() => {}} />);
    await waitFor(() => expect(api.getRunSandboxRefs).toHaveBeenCalled());

    const chip = screen.getByRole("button", { name: /^v1\b/ });
    fireEvent.click(chip);
    const listbox = screen.getByRole("listbox");
    const wrapper = chip.closest(".relative");
    expect(wrapper).not.toBeNull();
    expect(wrapper?.contains(listbox)).toBe(true);
  });
});

describe("RunHeader — live (building) state", () => {
  it("renders a streaming status badge + a 'draft' version chip + a DISABLED Share; no Download", () => {
    render(
      <RunHeader
        runState="building"
        versionLabel="v1"
        currentAgentName="Build Agent"
        buildStepIndex={4}
        buildStepTotal={7}
        onShare={() => {}}
      />,
    );
    expect(screen.getByText(/streaming/i)).toBeInTheDocument();
    expect(screen.getByText(/building step 4 of 7/i)).toBeInTheDocument();
    expect(screen.getByText(/v1 draft/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Share this run/ })).toBeDisabled();
    expect(screen.queryByRole("button", { name: /Download the deliverable/ })).toBeNull();
    // No tags fetched (no activeRunId) → no interactive Version menu.
    expect(screen.queryByRole("listbox")).toBeNull();
  });

  it("clarify state surfaces the 'Waiting on you' badge with the question count", () => {
    render(<RunHeader runState="clarify" versionLabel="v1" clarifyCount={6} />);
    expect(screen.getByText(/Waiting on you/)).toBeInTheDocument();
    expect(screen.getByText(/6 questions to answer before the build starts/)).toBeInTheDocument();
  });

  it("gate state surfaces the 'Paused · review gate' badge", () => {
    render(<RunHeader runState="gate" versionLabel="v1" />);
    expect(screen.getByText(/Paused · review gate/)).toBeInTheDocument();
  });

  it("task U1: once the run has ≥1 tag, the interactive VersionMenu renders WHILE RUNNING, next to (not instead of) the status badge", async () => {
    vi.spyOn(api, "getToken").mockReturnValue("test-token");
    vi.spyOn(api, "getRunSandboxRefs").mockResolvedValue(["v1"]);

    render(
      <RunHeader runState="building" activeRunId="r1" versionLabel="v1" onSelectVersion={() => {}} />,
    );

    await waitFor(() => expect(api.getRunSandboxRefs).toHaveBeenCalledWith("test-token", "r1"));
    // The interactive menu chip (still says "v1 draft" — the live label).
    expect(screen.getByRole("button", { name: /^v1 draft\b/ })).toBeInTheDocument();
    // The running status badge is STILL there, alongside it.
    expect(screen.getByText(/streaming/i)).toBeInTheDocument();
  });
});

describe("RunHeader — failed state", () => {
  it("renders the red 'Run failed' badge + a 'partial' version chip; no Share / Download", () => {
    render(<RunHeader runState="terminal" failed versionLabel="v1" onShare={() => {}} onDownload={() => {}} />);
    expect(screen.getByText(/Run failed/)).toBeInTheDocument();
    expect(screen.getByText(/v1 · partial/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Share this run/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /Download the deliverable/ })).toBeNull();
  });

  it("names the live failure location on the failed badge (ND-D reason)", () => {
    render(<RunHeader runState="terminal" failed versionLabel="v1" failureReason="Security reviewer" />);
    expect(screen.getByText(/Run failed · Security reviewer/)).toBeInTheDocument();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// RunHeader — backlog download split-button
//
// Covers the six acceptance criteria for the downloadVariant="backlog" path:
// (a) split button renders with the correct controls,
// (b) chevron opens the dropdown with all 3 items,
// (c) Zip option calls onDownloadZip,
// (d) PDF option calls onDownloadPdf,
// (e) clicking outside closes the dropdown,
// (f) default variant still renders the single "Download" button (regression).
// ─────────────────────────────────────────────────────────────────────────────
describe("RunHeader — backlog download split-button", () => {
  it("(a) renders split button when downloadVariant=backlog and canDownload=true", () => {
    render(
      <RunHeader
        runState="complete"
        versionLabel="v1"
        downloadVariant="backlog"
        canDownload
        onDownload={() => {}}
        onDownloadZip={() => {}}
        onDownloadPdf={() => {}}
        onDownloadZipWithPdf={() => {}}
      />,
    );
    expect(screen.getByRole("button", { name: /Download workspace ZIP/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /More download options/ })).toBeInTheDocument();
    // Dropdown is closed initially — no menu items visible.
    expect(screen.queryByRole("menuitem")).toBeNull();
  });

  it("(b) chevron click opens the dropdown with all 3 options", () => {
    render(
      <RunHeader
        runState="complete"
        versionLabel="v1"
        downloadVariant="backlog"
        canDownload
        onDownload={() => {}}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /More download options/ }));
    expect(screen.getByRole("menuitem", { name: /Download workspace ZIP archive/ })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /Download Backlog as PDF/ })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /Download ZIP with all documents as PDF/ })).toBeInTheDocument();
  });

  it("(c) clicking the Zip option calls onDownloadZip and closes the menu", () => {
    const onDownloadZip = vi.fn();
    render(
      <RunHeader
        runState="complete"
        versionLabel="v1"
        downloadVariant="backlog"
        canDownload
        onDownload={() => {}}
        onDownloadZip={onDownloadZip}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /More download options/ }));
    fireEvent.click(screen.getByRole("menuitem", { name: /Download workspace ZIP archive/ }));
    expect(onDownloadZip).toHaveBeenCalledTimes(1);
    // Dropdown closes after selection.
    expect(screen.queryByRole("menuitem")).toBeNull();
  });

  it("(d) clicking the PDF option calls onDownloadPdf and closes the menu", () => {
    const onDownloadPdf = vi.fn();
    render(
      <RunHeader
        runState="complete"
        versionLabel="v1"
        downloadVariant="backlog"
        canDownload
        onDownload={() => {}}
        onDownloadPdf={onDownloadPdf}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /More download options/ }));
    fireEvent.click(screen.getByRole("menuitem", { name: /Download Backlog as PDF/ }));
    expect(onDownloadPdf).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("menuitem")).toBeNull();
  });

  it("(e) mousedown outside the split-button container closes the dropdown", () => {
    render(
      <RunHeader
        runState="complete"
        versionLabel="v1"
        downloadVariant="backlog"
        canDownload
        onDownload={() => {}}
      />,
    );
    // Open the menu.
    fireEvent.click(screen.getByRole("button", { name: /More download options/ }));
    expect(screen.getByRole("menu")).toBeInTheDocument();
    // Simulate a mousedown on document.body — outside the split-button.
    fireEvent.mouseDown(document.body);
    expect(screen.queryByRole("menu")).toBeNull();
  });

  it("(f) default variant (no downloadVariant prop) renders the single Download button — regression guard", () => {
    render(
      <RunHeader
        runState="complete"
        versionLabel="v1"
        onDownload={() => {}}
        canDownload
      />,
    );
    expect(screen.getByRole("button", { name: /Download the deliverable/ })).toBeInTheDocument();
    // No split-button controls present.
    expect(screen.queryByRole("button", { name: /More download options/ })).toBeNull();
    expect(screen.queryByRole("menu")).toBeNull();
  });
});
