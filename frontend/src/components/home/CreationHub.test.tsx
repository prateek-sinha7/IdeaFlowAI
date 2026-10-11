import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Tier } from "@/lib/entitlements";
import type { WorkflowType } from "@/types/index";

const { pushMock, router } = vi.hoisted(() => {
  const pushMock = vi.fn();
  return { pushMock, router: { push: pushMock } };
});

vi.mock("next/navigation", () => ({ useRouter: () => router }));

import { CreationHub } from "./CreationHub";

const LABELS = {
  user_stories: /Generate product requirements/,
  ppt: /Pitch an idea/,
  prototype: /Build an interactive prototype/,
  app_builder: /Build an end-to-end application/,
  migration: /Platform workflows/,
  custom: /Compose a custom workflow/,
} as const;

function renderHub(props: { userTier?: Tier } = {}) {
  const onSelectFeature = vi.fn<(type: WorkflowType) => void>();
  const user = userEvent.setup();
  render(<CreationHub onSelectFeature={onSelectFeature} {...props} />);
  return { onSelectFeature, user };
}

const row = (key: keyof typeof LABELS) => screen.getByRole("button", { name: LABELS[key] });

describe("CreationHub", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the heading and one button per workflow", () => {
    renderHub();

    expect(
      screen.getByRole("heading", { level: 1, name: "What would you like to build today?" }),
    ).toBeInTheDocument();
    expect(screen.getAllByRole("button")).toHaveLength(6);
  });

  it("defaults to the basic tier when userTier is omitted", () => {
    renderHub();

    expect(row("user_stories")).toBeEnabled();
    expect(row("ppt")).toBeEnabled();
    expect(row("prototype")).toBeDisabled();
    expect(row("app_builder")).toBeDisabled();
    expect(row("migration")).toBeDisabled();
    expect(row("custom")).toBeDisabled();
  });

  it.each([
    ["prototype", "Requires Pro plan"],
    ["app_builder", "Requires Pro plan"],
    ["migration", "Requires Enterprise plan"],
    ["custom", "Requires Enterprise plan"],
  ] as const)("shows the required tier on the locked %s row (basic)", (key, text) => {
    renderHub({ userTier: "basic" });

    expect(within(row(key)).getByText(text)).toBeInTheDocument();
    expect(within(row("user_stories")).queryByText(/Requires/)).not.toBeInTheDocument();
    expect(within(row("ppt")).queryByText(/Requires/)).not.toBeInTheDocument();
  });

  it("unlocks every row and shows the NEW badge on enterprise", () => {
    renderHub({ userTier: "enterprise" });

    for (const button of screen.getAllByRole("button")) {
      expect(button).toBeEnabled();
    }
    expect(screen.queryByText(/Requires/)).not.toBeInTheDocument();
    expect(screen.getByText("NEW")).toBeInTheDocument();
  });

  it("hides the NEW badge while the migration row is locked", () => {
    renderHub({ userTier: "basic" });

    expect(screen.queryByText("NEW")).not.toBeInTheDocument();
  });

  it("unlocks prototype and app builder but not migration on pro", () => {
    renderHub({ userTier: "pro" });

    expect(row("prototype")).toBeEnabled();
    expect(row("app_builder")).toBeEnabled();
    expect(row("migration")).toBeDisabled();
    expect(row("custom")).toBeDisabled();
    expect(within(row("migration")).getByText("Requires Enterprise plan")).toBeInTheDocument();
    expect(within(row("custom")).getByText("Requires Enterprise plan")).toBeInTheDocument();
  });

  it.each([
    ["basic", "user_stories"],
    ["pro", "app_builder"],
    ["enterprise", "migration"],
    ["enterprise", "custom"],
  ] as const)("calls onSelectFeature when %s selects %s", async (tier, type) => {
    const { onSelectFeature, user } = renderHub({ userTier: tier });

    await user.click(row(type));

    expect(onSelectFeature).toHaveBeenCalledTimes(1);
    expect(onSelectFeature).toHaveBeenCalledWith(type);
    expect(pushMock).not.toHaveBeenCalled();
  });

  it("routes ppt to the legacy wizard", async () => {
    const { onSelectFeature, user } = renderHub({ userTier: "basic" });

    await user.click(row("ppt"));

    expect(pushMock).toHaveBeenCalledWith("/workflow/create?mode=ppt");
    expect(onSelectFeature).not.toHaveBeenCalled();
  });

  it("routes prototype to the legacy wizard", async () => {
    const { onSelectFeature, user } = renderHub({ userTier: "pro" });

    await user.click(row("prototype"));

    expect(pushMock).toHaveBeenCalledWith("/workflow/create?mode=prototype");
    expect(onSelectFeature).not.toHaveBeenCalled();
  });

  it("does nothing when a locked row is clicked", async () => {
    const { onSelectFeature, user } = renderHub({ userTier: "basic" });

    await user.click(row("prototype"));

    expect(onSelectFeature).not.toHaveBeenCalled();
    expect(pushMock).not.toHaveBeenCalled();
  });

  it("locks ppt and keeps user stories and prototype enabled on hexaware", () => {
    // Only enabled/disabled is asserted: the upgrade label for hexaware is a
    // suspected defect (reads "Requires Basic plan"), reported separately.
    renderHub({ userTier: "hexaware" });

    expect(row("ppt")).toBeDisabled();
    expect(row("user_stories")).toBeEnabled();
    expect(row("prototype")).toBeEnabled();
  });

  it("is operable from the keyboard on enabled rows only", async () => {
    const { onSelectFeature, user } = renderHub({ userTier: "basic" });

    await user.tab();
    expect(row("user_stories")).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(onSelectFeature).toHaveBeenCalledWith("user_stories");

    await user.tab();
    expect(row("ppt")).toHaveFocus();
    await user.tab();
    for (const key of ["prototype", "app_builder", "migration", "custom"] as const) {
      expect(row(key)).not.toHaveFocus();
    }
  });
});
