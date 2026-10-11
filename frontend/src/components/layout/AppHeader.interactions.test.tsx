/**
 * AppHeader — interaction coverage for the paths the a11y / ISS-647 /
 * running-dropdown-snapshot suites do not reach: outside-click dismissal, badge
 * progress derivation, notification-only pipelines, the bell, the legacy badge,
 * and every profile-menu action (upgrade, navigation, admin, theme, logout).
 *
 * Boundary mocked: next/navigation only (so the Admin route push is assertable).
 * Redux/labels, NotificationPanel, UpgradePlanModal and useTheme run for real.
 * Menu closure is asserted with waitFor because the menus leave through an
 * AnimatePresence exit animation.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { renderWithProviders, screen, waitFor, within } from "@/test/renderWithProviders";
import userEvent from "@testing-library/user-event";

const { pushMock } = vi.hoisted(() => ({ pushMock: vi.fn() }));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock, replace: vi.fn(), prefetch: vi.fn() }),
}));

import { AppHeader } from "./AppHeader";
import type { PipelineNotification } from "@/hooks/useNotifications";
import type { WorkflowRun } from "@/types/index";

type HeaderProps = React.ComponentProps<typeof AppHeader>;

function makeRun(overrides: Partial<WorkflowRun> = {}): WorkflowRun {
  return {
    id: "run-a",
    title: "Alpha",
    type: "user_stories",
    status: "running",
    input: "{}",
    createdAt: new Date(0).toISOString(),
    parentRunId: null,
    rootRunId: "run-a",
    agentCount: 4,
    ...overrides,
  } as WorkflowRun;
}

function makeNotification(overrides: Partial<PipelineNotification> = {}): PipelineNotification {
  return {
    id: "n-1",
    workflowType: "user_stories",
    title: "Notif",
    status: "running",
    createdAt: new Date(0),
    read: true,
    ...overrides,
  } as PipelineNotification;
}

/** A promise the test settles by hand, to pin the await-then-navigate ordering. */
function deferred() {
  let resolve!: () => void;
  const promise = new Promise<void>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}

function setup(overrides: Partial<HeaderProps> = {}) {
  const spies = {
    onNavigate: vi.fn(),
    onLogout: vi.fn(),
    onGoToPipeline: vi.fn(),
    onSwitchToLiveRun: vi.fn(),
    onSelectWorkflowRun: vi.fn(),
    onViewResults: vi.fn(),
    onMarkAllRead: vi.fn(),
    onClearNotifications: vi.fn(),
    onDismissOneNotification: vi.fn(),
  };
  const buildUi = (extra: Partial<HeaderProps> = {}) => (
    <AppHeader currentPage="home" userEmail="qa@flowin.test" {...spies} {...overrides} {...extra} />
  );
  const view = renderWithProviders(buildUi());
  return { ...spies, rerenderWith: (extra: Partial<HeaderProps>) => view.rerender(buildUi(extra)) };
}

const accountTrigger = () => screen.getByRole("button", { name: "Account menu" });
const waitForNoMenu = () =>
  waitFor(() => expect(screen.queryByRole("menu")).not.toBeInTheDocument());

async function openAccountMenu(user: ReturnType<typeof userEvent.setup>) {
  await user.click(accountTrigger());
  return screen.getByRole("menu");
}

beforeEach(() => {
  pushMock.mockClear();
});

afterEach(() => {
  document.documentElement.removeAttribute("data-theme");
  localStorage.clear();
});

describe("AppHeader outside-click and keyboard dismissal", () => {
  it("closes the account menu when the user presses outside it", async () => {
    const user = userEvent.setup();
    setup();
    await openAccountMenu(user);

    await user.click(document.body);

    await waitForNoMenu();
    expect(accountTrigger()).toHaveAttribute("aria-expanded", "false");
  });

  it("closes the running dropdown when the user presses outside it", async () => {
    const user = userEvent.setup();
    setup({ recentRuns: [makeRun({ id: "a" }), makeRun({ id: "b", title: "Beta" })] });
    const badge = screen.getByRole("button", { name: /2 pipelines running/i });
    await user.click(badge);
    expect(screen.getByRole("menu")).toBeInTheDocument();

    await user.click(document.body);

    await waitForNoMenu();
    expect(badge).toHaveAttribute("aria-expanded", "false");
  });

  it("lets Escape propagate when the account menu is closed", async () => {
    const user = userEvent.setup();
    setup();
    const onDocumentKeyDown = vi.fn();
    document.addEventListener("keydown", onDocumentKeyDown);
    try {
      accountTrigger().focus();
      await user.keyboard("{Escape}");
    } finally {
      document.removeEventListener("keydown", onDocumentKeyDown);
    }

    expect(onDocumentKeyDown).toHaveBeenCalledTimes(1);
    expect(accountTrigger()).toHaveAttribute("aria-expanded", "false");
  });

  it("swallows Escape when the account menu is open", async () => {
    const user = userEvent.setup();
    setup();
    await openAccountMenu(user);
    const onDocumentKeyDown = vi.fn();
    document.addEventListener("keydown", onDocumentKeyDown);
    try {
      await user.keyboard("{Escape}");
    } finally {
      document.removeEventListener("keydown", onDocumentKeyDown);
    }

    expect(onDocumentKeyDown).not.toHaveBeenCalled();
    await waitForNoMenu();
  });
});

describe("AppHeader running badge source and progress", () => {
  it("falls back to running and gate notifications while recentRuns is empty", () => {
    setup({
      recentRuns: [],
      notifications: [
        makeNotification({ id: "n-1", status: "running" }),
        makeNotification({ id: "n-2", status: "gate" }),
      ],
    });

    expect(screen.getByRole("button", { name: /2 pipelines running/i })).toBeInTheDocument();
  });

  it("shows no running badge when the only notification is terminal", () => {
    setup({ recentRuns: [], notifications: [makeNotification({ status: "completed" })] });

    expect(screen.queryByRole("button", { name: /pipelines? running/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /user stories/i })).not.toBeInTheDocument();
  });

  it.each([
    ["the active run prefers the live scalar total", { id: "run-a", agentCount: 4 }, { activePipelineRunId: "run-a", pipelineAgentsCompleted: 2, pipelineAgentsTotal: 6 }, /user stories.*2\/6/i],
    ["the active run falls back to agentCount when the live total is 0", { id: "run-a", agentCount: 4 }, { activePipelineRunId: "run-a", pipelineAgentsCompleted: 0, pipelineAgentsTotal: 0 }, /user stories.*0\/4/i],
    ["a background run reads the per-run completed map", { id: "run-a", agentCount: 4 }, { activePipelineRunId: "other", runAgentsCompletedMap: { "run-a": 3 } }, /user stories.*3\/4/i],
    ["a background run without a map entry starts at 0", { id: "run-a", agentCount: 4 }, { activePipelineRunId: null }, /user stories.*0\/4/i],
    ["a background run with no agentCount shows no count", { id: "run-a", agentCount: undefined }, { activePipelineRunId: null }, /^user stories$/i],
  ] as const)("badge progress: %s", (_name, runOverrides, headerOverrides, expectedName) => {
    setup({ recentRuns: [makeRun(runOverrides as Partial<WorkflowRun>)], ...(headerOverrides as Partial<HeaderProps>) });

    expect(screen.getByRole("button", { name: expectedName })).toBeInTheDocument();
  });

  it.each([
    "running",
    "revising",
    "planning",
    "generating",
    "clarifying",
    "analyzing",
    "waiting_for_user",
  ])("counts a %s run as in flight", (status) => {
    setup({ recentRuns: [makeRun({ status: status as WorkflowRun["status"] })] });

    expect(screen.getByRole("button", { name: /user stories/i })).toBeInTheDocument();
  });

  it("does not count a completed run as in flight", () => {
    setup({ recentRuns: [makeRun({ status: "completed" })] });

    expect(screen.queryByRole("button", { name: /user stories/i })).not.toBeInTheDocument();
  });

  it("shows the agent count on a notification badge only when a total exists", () => {
    setup({
      recentRuns: [],
      notifications: [makeNotification({ agentsCompleted: 2, agentsTotal: 5 })],
    });

    expect(screen.getByRole("button", { name: /user stories.*2\/5/i })).toBeInTheDocument();
  });

  it("counts from 0 on a notification badge that has a total but no completed count", () => {
    setup({ recentRuns: [], notifications: [makeNotification({ agentsTotal: 5 })] });

    expect(screen.getByRole("button", { name: /user stories.*0\/5/i })).toBeInTheDocument();
  });

  it("omits the count on a notification badge without a total", () => {
    setup({ recentRuns: [], notifications: [makeNotification()] });

    expect(screen.getByRole("button", { name: /^user stories$/i })).toBeInTheDocument();
  });
});

describe("AppHeader bell while the run list loads", () => {
  it("says it is checking for active pipelines when nothing is known yet", async () => {
    const user = userEvent.setup();
    setup({ recentRuns: [], recentRunsLoaded: false });

    await user.click(screen.getByRole("button", { name: "Notifications" }));

    expect(await screen.findByText("Checking for active pipelines…")).toBeInTheDocument();
  });

  it("says there are no notifications once the run list has loaded empty", async () => {
    const user = userEvent.setup();
    setup({ recentRuns: [], recentRunsLoaded: true });

    await user.click(screen.getByRole("button", { name: "Notifications" }));

    expect(await screen.findByText("No notifications yet")).toBeInTheDocument();
    expect(screen.queryByText("Checking for active pipelines…")).not.toBeInTheDocument();
  });
});

describe("AppHeader running dropdown navigation", () => {
  const twoLive = () => [
    makeRun({ id: "run-a", title: "Alpha" }),
    makeRun({ id: "run-b", title: "Beta" }),
  ];

  it("waits for onSwitchToLiveRun to settle before navigating", async () => {
    const user = userEvent.setup();
    const switching = deferred();
    const onSwitchToLiveRun = vi.fn(() => switching.promise);
    const { onGoToPipeline } = setup({ recentRuns: twoLive(), onSwitchToLiveRun });
    await user.click(screen.getByRole("button", { name: /2 pipelines running/i }));

    await user.click(within(screen.getByRole("menu")).getByRole("menuitem", { name: /beta/i }));

    expect(onSwitchToLiveRun).toHaveBeenCalledExactlyOnceWith("run-b");
    expect(onGoToPipeline).not.toHaveBeenCalled();
    switching.resolve();
    await waitFor(() => expect(onGoToPipeline).toHaveBeenCalledWith("run-b"));
  });

  it("navigates immediately when no switch handler is supplied", async () => {
    const user = userEvent.setup();
    const { onGoToPipeline } = setup({ recentRuns: twoLive(), onSwitchToLiveRun: undefined });
    await user.click(screen.getByRole("button", { name: /2 pipelines running/i }));

    await user.click(within(screen.getByRole("menu")).getByRole("menuitem", { name: /beta/i }));

    expect(onGoToPipeline).toHaveBeenCalledExactlyOnceWith("run-b");
  });

  it("opens a run that finished while the menu was open through onSelectWorkflowRun", async () => {
    const user = userEvent.setup();
    const { onSelectWorkflowRun, onGoToPipeline, rerenderWith } = setup({ recentRuns: twoLive() });
    await user.click(screen.getByRole("button", { name: /2 pipelines running/i }));
    rerenderWith({ recentRuns: [makeRun({ id: "run-a", title: "Alpha" }), makeRun({ id: "run-b", title: "Beta", status: "completed" })] });

    await user.click(within(screen.getByRole("menu")).getByRole("menuitem", { name: /beta/i }));

    expect(onSelectWorkflowRun).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({ id: "run-b" }));
    expect(onGoToPipeline).not.toHaveBeenCalled();
  });

  it("falls back to a bare onGoToPipeline for a finished run when onSelectWorkflowRun is absent", async () => {
    const user = userEvent.setup();
    const { onGoToPipeline, rerenderWith } = setup({ recentRuns: twoLive(), onSelectWorkflowRun: undefined });
    await user.click(screen.getByRole("button", { name: /2 pipelines running/i }));
    rerenderWith({ recentRuns: [makeRun({ id: "run-a", title: "Alpha" }), makeRun({ id: "run-b", title: "Beta", status: "completed" })] });

    await user.click(within(screen.getByRole("menu")).getByRole("menuitem", { name: /beta/i }));

    expect(onGoToPipeline).toHaveBeenCalledExactlyOnceWith();
  });

  it("labels each row with its status and falls back to Running for unmapped statuses", async () => {
    const user = userEvent.setup();
    setup({
      recentRuns: [
        makeRun({ id: "run-a", title: "Alpha", status: "waiting_for_user" }),
        makeRun({ id: "run-b", title: "Beta", status: "analyzing" }),
      ],
    });
    await user.click(screen.getByRole("button", { name: /2 pipelines running/i }));

    const [gateRow, analyzingRow] = within(screen.getByRole("menu")).getAllByRole("menuitem");

    expect(gateRow).toHaveTextContent("Waiting for you");
    expect(analyzingRow).toHaveTextContent("Running");
  });
});

describe("AppHeader single badge built from a notification", () => {
  const runningNotification = (overrides: Partial<PipelineNotification> = {}) =>
    makeNotification({ workflowRunId: "run-n", ...overrides });

  it("waits for onSwitchToLiveRun before navigating to the notification's run", async () => {
    const user = userEvent.setup();
    const switching = deferred();
    const onSwitchToLiveRun = vi.fn(() => switching.promise);
    const { onGoToPipeline } = setup({
      recentRuns: [],
      notifications: [runningNotification()],
      onSwitchToLiveRun,
    });

    await user.click(screen.getByRole("button", { name: /user stories/i }));

    expect(onSwitchToLiveRun).toHaveBeenCalledExactlyOnceWith("run-n");
    expect(onGoToPipeline).not.toHaveBeenCalled();
    switching.resolve();
    await waitFor(() => expect(onGoToPipeline).toHaveBeenCalledExactlyOnceWith("run-n"));
  });

  it("navigates directly to the notification's run when no switch handler exists", async () => {
    const user = userEvent.setup();
    const { onGoToPipeline } = setup({
      recentRuns: [],
      notifications: [runningNotification()],
      onSwitchToLiveRun: undefined,
    });

    await user.click(screen.getByRole("button", { name: /user stories/i }));

    expect(onGoToPipeline).toHaveBeenCalledExactlyOnceWith("run-n");
  });

  it("navigates with no run id and skips the switch when the notification has none", async () => {
    const user = userEvent.setup();
    const { onGoToPipeline, onSwitchToLiveRun } = setup({
      recentRuns: [],
      notifications: [makeNotification({ workflowRunId: undefined })],
    });

    await user.click(screen.getByRole("button", { name: /user stories/i }));

    expect(onSwitchToLiveRun).not.toHaveBeenCalled();
    expect(onGoToPipeline).toHaveBeenCalledExactlyOnceWith(undefined);
  });
});

describe("AppHeader running dropdown built from notifications", () => {
  const notifications = () => [
    makeNotification({ id: "n-1", title: "T1", agentsCompleted: 2, agentsTotal: 6 }),
    makeNotification({ id: "n-2", title: "", status: "gate" }),
  ];

  it("lists each notification with its title, progress and status", async () => {
    const user = userEvent.setup();
    setup({ recentRuns: [], notifications: notifications() });
    await user.click(screen.getByRole("button", { name: /2 pipelines running/i }));

    const [first, second] = within(screen.getByRole("menu")).getAllByRole("menuitem");

    expect(first).toHaveTextContent("T1");
    expect(first).toHaveTextContent("2/6");
    expect(first).toHaveTextContent("Running");
    expect(second).toHaveTextContent("Awaiting review");
    expect(second).not.toHaveTextContent("·");
    expect(second).not.toHaveTextContent("/");
  });

  it("counts from 0 on a row that has a total but no completed count", async () => {
    const user = userEvent.setup();
    setup({
      recentRuns: [],
      notifications: [
        makeNotification({ id: "n-1", agentsTotal: 5 }),
        makeNotification({ id: "n-2", status: "gate" }),
      ],
    });
    await user.click(screen.getByRole("button", { name: /2 pipelines running/i }));

    const [first] = within(screen.getByRole("menu")).getAllByRole("menuitem");

    expect(first).toHaveTextContent("0/5");
  });

  it("opens the clicked notification through onViewResults and closes the menu", async () => {
    const user = userEvent.setup();
    const list = notifications();
    const { onViewResults } = setup({ recentRuns: [], notifications: list });
    await user.click(screen.getByRole("button", { name: /2 pipelines running/i }));

    await user.click(within(screen.getByRole("menu")).getAllByRole("menuitem")[0]);

    expect(onViewResults).toHaveBeenCalledExactlyOnceWith(list[0]);
    await waitForNoMenu();
  });

  it("still closes the menu when onViewResults is not supplied", async () => {
    const user = userEvent.setup();
    setup({ recentRuns: [], notifications: notifications(), onViewResults: undefined });
    await user.click(screen.getByRole("button", { name: /2 pipelines running/i }));

    await user.click(within(screen.getByRole("menu")).getAllByRole("menuitem")[0]);

    await waitForNoMenu();
  });
});

describe("AppHeader legacy scalar badge", () => {
  it("shows the pipeline label with progress when only the scalar props say running", () => {
    setup({
      recentRuns: [],
      isPipelineRunning: true,
      pipelineType: "user_stories",
      pipelineAgentsCompleted: 1,
      pipelineAgentsTotal: 3,
    });

    expect(screen.getByRole("button", { name: /user stories.*1\/3/i })).toBeInTheDocument();
  });

  it("omits the count when the scalar total is 0", () => {
    setup({ recentRuns: [], isPipelineRunning: true, pipelineType: "user_stories" });

    expect(screen.getByRole("button", { name: /^user stories$/i })).toBeInTheDocument();
  });

  it("shows no badge without a pipeline type", () => {
    setup({ recentRuns: [], isPipelineRunning: true });

    expect(screen.queryByRole("button", { name: /user stories/i })).not.toBeInTheDocument();
  });

  it("reports a bare onGoToPipeline when clicked", async () => {
    const user = userEvent.setup();
    const { onGoToPipeline } = setup({ recentRuns: [], isPipelineRunning: true, pipelineType: "user_stories" });

    await user.click(screen.getByRole("button", { name: /user stories/i }));

    expect(onGoToPipeline).toHaveBeenCalledExactlyOnceWith();
  });
});

describe("AppHeader notification bell handlers", () => {
  const terminal = () => [makeNotification({ id: "done-1", status: "completed", workflowRunId: "run-done", read: false })];

  it("marks everything read when the bell opens with unread notifications", async () => {
    const user = userEvent.setup();
    const { onMarkAllRead } = setup({ notifications: terminal(), unreadCount: 1 });

    await user.click(screen.getByRole("button", { name: "Notifications" }));

    expect(onMarkAllRead).toHaveBeenCalledTimes(1);
  });

  it("clears all notifications from the panel", async () => {
    const user = userEvent.setup();
    const { onClearNotifications } = setup({ notifications: terminal() });
    await user.click(screen.getByRole("button", { name: "Notifications" }));

    await user.click(await screen.findByRole("button", { name: /clear all/i }));

    expect(onClearNotifications).toHaveBeenCalledTimes(1);
  });

  it("dismisses one notification by id", async () => {
    const user = userEvent.setup();
    const { onDismissOneNotification } = setup({ notifications: terminal() });
    await user.click(screen.getByRole("button", { name: "Notifications" }));

    await user.click(await screen.findByRole("button", { name: /dismiss notification for user stories/i }));

    expect(onDismissOneNotification).toHaveBeenCalledExactlyOnceWith("done-1");
  });

  it("opens a terminal notification through onViewResults", async () => {
    const user = userEvent.setup();
    const list = terminal();
    const { onViewResults } = setup({ notifications: list });
    await user.click(screen.getByRole("button", { name: "Notifications" }));

    await user.click(await screen.findByRole("button", { name: "Notif" }));

    expect(onViewResults).toHaveBeenCalledExactlyOnceWith(list[0]);
  });

  it("survives every bell action when the optional handlers are absent", async () => {
    const user = userEvent.setup();
    setup({
      notifications: terminal(),
      unreadCount: 1,
      onMarkAllRead: undefined,
      onClearNotifications: undefined,
      onViewResults: undefined,
      onGoToPipeline: undefined,
    });
    const bell = screen.getByRole("button", { name: "Notifications" });

    await user.click(bell);
    await user.click(await screen.findByRole("button", { name: /clear all/i }));
    await user.click(screen.getByRole("button", { name: "Notif" }));

    await waitFor(() => expect(bell).toHaveAttribute("aria-expanded", "false"));
  });
});

describe("AppHeader account menu", () => {
  it("blocks the account menu while disabled", async () => {
    const user = userEvent.setup();
    setup({ disabled: true });

    expect(accountTrigger()).toBeDisabled();
    await user.click(accountTrigger());

    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });

  it("shows the email in the identity block", async () => {
    const user = userEvent.setup();
    setup({ userEmail: "who@flowin.test" });

    const menu = await openAccountMenu(user);

    expect(within(menu).getByText("who@flowin.test")).toBeInTheDocument();
    expect(within(menu).queryByText("Account")).not.toBeInTheDocument();
  });

  it("falls back to a generic Account label without an email", async () => {
    const user = userEvent.setup();
    setup({ userEmail: undefined });

    const menu = await openAccountMenu(user);

    expect(within(menu).getByText("Account")).toBeInTheDocument();
  });

  it.each([
    ["Account Settings", "settings"],
    ["Analytics", "analytics"],
    ["Run History", "history"],
  ])("%s navigates to %s and closes the menu", async (name, pageKey) => {
    const user = userEvent.setup();
    const { onNavigate } = setup();
    const menu = await openAccountMenu(user);

    await user.click(within(menu).getByRole("menuitem", { name }));

    expect(onNavigate).toHaveBeenCalledExactlyOnceWith(pageKey);
    await waitForNoMenu();
  });

  it("routes Admin Dashboard to /admin and closes the menu", async () => {
    const user = userEvent.setup();
    const { onNavigate } = setup({ isAdmin: true });
    const menu = await openAccountMenu(user);

    await user.click(within(menu).getByRole("menuitem", { name: "Admin Dashboard" }));

    expect(pushMock).toHaveBeenCalledExactlyOnceWith("/admin");
    expect(onNavigate).not.toHaveBeenCalled();
    await waitForNoMenu();
  });

  it("logs out and closes the menu", async () => {
    const user = userEvent.setup();
    const { onLogout } = setup();
    const menu = await openAccountMenu(user);

    await user.click(within(menu).getByRole("menuitem", { name: "Log out" }));

    expect(onLogout).toHaveBeenCalledTimes(1);
    await waitForNoMenu();
  });
});

describe("AppHeader upgrade", () => {
  it("offers Upgrade on the basic tier and opens the plan dialog", async () => {
    const user = userEvent.setup();
    setup({ userTier: "basic" });
    const menu = await openAccountMenu(user);

    await user.click(within(menu).getByRole("button", { name: "Upgrade" }));

    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    await waitForNoMenu();
  });

  it("closes the plan dialog with Escape", async () => {
    const user = userEvent.setup();
    setup({ userTier: "basic" });
    const menu = await openAccountMenu(user);
    await user.click(within(menu).getByRole("button", { name: "Upgrade" }));
    await screen.findByRole("dialog");

    await user.keyboard("{Escape}");

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("closes the plan dialog with its Close button", async () => {
    const user = userEvent.setup();
    setup({ userTier: "basic" });
    const menu = await openAccountMenu(user);
    await user.click(within(menu).getByRole("button", { name: "Upgrade" }));

    await user.click(await screen.findByRole("button", { name: "Close" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it.each(["pro", "enterprise", "hexaware"] as const)("does not offer Upgrade on the %s tier", async (userTier) => {
    const user = userEvent.setup();
    setup({ userTier });

    const menu = await openAccountMenu(user);

    expect(within(menu).queryByRole("button", { name: "Upgrade" })).not.toBeInTheDocument();
  });
});

describe("AppHeader theme toggle", () => {
  it("switches light to dark and back, persisting each choice", async () => {
    const user = userEvent.setup();
    setup();
    const menu = await openAccountMenu(user);
    const toggle = within(menu).getByRole("menuitem", { name: /dark mode/i });

    await user.click(toggle);
    expect(document.documentElement).toHaveAttribute("data-theme", "dark");
    expect(localStorage.getItem("velocity-theme")).toBe("dark");

    await user.click(toggle);
    expect(document.documentElement).toHaveAttribute("data-theme", "light");
    expect(localStorage.getItem("velocity-theme")).toBe("light");
  });

  it("switches to light on the first toggle when the page started dark", async () => {
    document.documentElement.setAttribute("data-theme", "dark");
    const user = userEvent.setup();
    setup();
    const menu = await openAccountMenu(user);

    await user.click(within(menu).getByRole("menuitem", { name: /dark mode/i }));

    expect(document.documentElement).toHaveAttribute("data-theme", "light");
    expect(localStorage.getItem("velocity-theme")).toBe("light");
  });
});

describe("AppHeader primary navigation", () => {
  it.each([
    ["Home", "home"],
    ["Library", "library"],
  ])("%s reports the %s page key", async (name, pageKey) => {
    const user = userEvent.setup();
    const { onNavigate } = setup({ currentPage: "history" });

    await user.click(screen.getByRole("button", { name }));

    expect(onNavigate).toHaveBeenCalledExactlyOnceWith(pageKey);
  });
});
