/**
 * Tools tab "Connected Apps" (design 4.4): per-tool switches, off until the
 * user turns them on, written only to the step's `tools.connectors`.
 *
 * Boundaries replaced: the Connectors REST client and `getToken`. The hook, the
 * cache and the component run for real.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ConnectorToolsResponse, ConnectorTool } from "@/types/connectors";
import { buildConnector, buildConnectedConnector } from "@/test/connectorFixtures";
import type { StepSelection } from "../AgentsPopup";

const mockList = vi.fn();
const mockTools = vi.fn();
vi.mock("@/store/api/connectors", () => ({
  connectorsApi: {
    list: (...a: unknown[]) => mockList(...a),
    tools: (...a: unknown[]) => mockTools(...a),
  },
}));
vi.mock("@/lib/api", () => ({ getToken: () => "test-token" }));

import { resetConnectedAppsCache } from "@/hooks/useConnectedApps";
import {
  ConnectedAppsSection,
  MAX_CONNECTOR_TOOLS,
  NOT_AVAILABLE_NOTE,
  LIMIT_NOTE,
  type ConnectedAppsAvailability,
} from "./ConnectedAppsSection";

const GITHUB = buildConnectedConnector({ key: "github", display_name: "GitHub" });
const JIRA_OFF = buildConnector({ key: "jira", display_name: "Jira", status: "not_connected" });
const JIRA_EXPIRED = buildConnector({ key: "jira", display_name: "Jira", status: "expired" });
const JIRA_UNCONFIGURED = buildConnector({
  key: "jira",
  display_name: "Jira",
  status: "not_configured",
});

function tool(key: string, name: string, extra: Partial<ConnectorTool> = {}): ConnectorTool {
  return {
    name: `${key}__${name}`,
    source_name: name,
    title: name.replace(/_/g, " "),
    description: `Description of ${name}.`,
    write_capable: false,
    ...extra,
  };
}

const GITHUB_TOOLS = [
  tool("github", "get_issue", { title: "Get issue" }),
  tool("github", "create_issue", { title: "Create issue", write_capable: true }),
];

function toolsResponse(key: string, tools: ConnectorTool[]): ConnectorToolsResponse {
  return { connector: key, status: "connected", tools, listed_at: null };
}

interface Options {
  sel?: StepSelection;
  availability?: ConnectedAppsAvailability;
}

function renderSection({ sel, availability = "available" }: Options = {}) {
  const onToolsChange = vi.fn();
  render(<ConnectedAppsSection sel={sel} availability={availability} onToolsChange={onToolsChange} />);
  return onToolsChange;
}

async function expandGitHub(user: ReturnType<typeof userEvent.setup>) {
  const group = await screen.findByRole("group", { name: /GitHub/ });
  await user.click(within(group).getByRole("button", { name: "Show GitHub tools" }));
  return group;
}

beforeEach(() => {
  vi.clearAllMocks();
  resetConnectedAppsCache();
  mockList.mockResolvedValue({ connectors: [GITHUB, JIRA_OFF] });
  mockTools.mockImplementation(async (key: string) =>
    toolsResponse(key, key === "github" ? GITHUB_TOOLS : []),
  );
});

describe("ConnectedAppsSection - states", () => {
  it("shows a loading placeholder while the connectors load", () => {
    mockList.mockReturnValue(new Promise(() => {}));
    renderSection();

    expect(screen.getByRole("status", { name: "Loading connected apps" })).toBeInTheDocument();
  });

  it("shows the error with a Retry that loads the connectors", async () => {
    const user = userEvent.setup();
    mockList.mockRejectedValueOnce(new Error("Service unavailable"));
    renderSection();

    expect(await screen.findByRole("alert")).toHaveTextContent("Service unavailable");
    await user.click(screen.getByRole("button", { name: "Retry loading connected apps" }));

    expect(await screen.findByRole("group", { name: /GitHub/ })).toBeInTheDocument();
  });

  it("says so when no connector is available", async () => {
    mockList.mockResolvedValue({ connectors: [] });
    renderSection();

    expect(await screen.findByText("No connectors are available.")).toBeInTheDocument();
  });

  it("names each connector in a labelled group with its status as text", async () => {
    renderSection();

    const github = await screen.findByRole("group", { name: /GitHub/ });
    const jira = screen.getByRole("group", { name: /Jira/ });
    expect(within(github).getByText("Connected")).toBeInTheDocument();
    expect(within(jira).getByText("Not connected")).toBeInTheDocument();
  });

  it("shows 'Not configured on this server' and no controls for a connector the server lacks", async () => {
    mockList.mockResolvedValue({ connectors: [JIRA_UNCONFIGURED] });
    renderSection();

    const group = await screen.findByRole("group", { name: /Jira/ });
    expect(within(group).getByText("Not configured on this server")).toBeInTheDocument();
    expect(within(group).queryByRole("switch")).not.toBeInTheDocument();
    expect(within(group).queryByRole("link")).not.toBeInTheDocument();
  });

  it("links a not-connected connector to Connectors in a new tab", async () => {
    renderSection();

    const group = await screen.findByRole("group", { name: /Jira/ });
    const link = within(group).getByRole("link", { name: "Connect in Connectors" });
    expect(link).toHaveAttribute("href", "/connectors?connector=jira");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    expect(within(group).queryByRole("switch")).not.toBeInTheDocument();
  });

  it("offers Reconnect for an expired connection", async () => {
    mockList.mockResolvedValue({ connectors: [JIRA_EXPIRED] });
    renderSection();

    const group = await screen.findByRole("group", { name: /Jira/ });
    expect(within(group).getByText(/Your Jira connection expired/)).toBeInTheDocument();
    expect(within(group).getByRole("link", { name: "Reconnect in Connectors" })).toBeInTheDocument();
  });
});

describe("ConnectedAppsSection - tools of a connected app", () => {
  it("lists no tools and makes no tools request until the group is opened", async () => {
    renderSection();

    const group = await screen.findByRole("group", { name: /GitHub/ });

    expect(within(group).getByRole("button", { name: "Show GitHub tools" })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
    expect(within(group).queryByRole("switch")).not.toBeInTheDocument();
    expect(mockTools).not.toHaveBeenCalled();
  });

  it("opens the list on demand with every tool off by default", async () => {
    const user = userEvent.setup();
    renderSection();

    const group = await expandGitHub(user);

    expect(await within(group).findByRole("switch", { name: "Get issue" })).toHaveAttribute(
      "aria-checked",
      "false",
    );
    expect(within(group).getByRole("switch", { name: "Create issue" })).toHaveAttribute(
      "aria-checked",
      "false",
    );
    expect(mockTools).toHaveBeenCalledWith("github");
    expect(within(group).getByRole("button", { name: "Hide GitHub tools" })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
  });

  it("marks a tool that can change data with a text badge, and only that tool", async () => {
    const user = userEvent.setup();
    renderSection();

    const group = await expandGitHub(user);
    await within(group).findByRole("switch", { name: "Get issue" });

    expect(within(group).getAllByText("Can change data")).toHaveLength(1);
    const createRow = within(group).getByRole("switch", { name: "Create issue" }).closest("li");
    expect(within(createRow as HTMLElement).getByText("Can change data")).toBeInTheDocument();
  });

  it("shows provider descriptions as plain text, never as HTML", async () => {
    const user = userEvent.setup();
    const hostile = '<img src="x" onerror="alert(1)"> <b>bold</b>';
    mockTools.mockResolvedValue(
      toolsResponse("github", [tool("github", "get_issue", { title: "Get issue", description: hostile })]),
    );
    renderSection();

    const group = await expandGitHub(user);

    expect(await within(group).findByText(hostile)).toBeInTheDocument();
    expect(group.querySelector("img")).toBeNull();
    expect(group.querySelector("b")).toBeNull();
  });

  it("keeps the full description in a tooltip", async () => {
    const user = userEvent.setup();
    renderSection();

    const group = await expandGitHub(user);

    expect(await within(group).findByText("Description of get_issue.")).toHaveAttribute(
      "title",
      "Description of get_issue.",
    );
  });

  it("counts how many of the connector's tools are on", async () => {
    const user = userEvent.setup();
    renderSection({ sel: { tools: { connectors: ["github__get_issue"] } } });

    const group = await screen.findByRole("group", { name: /GitHub/ });
    expect(within(group).getByText("1 on")).toBeInTheDocument();
    await user.click(within(group).getByRole("button", { name: "Show GitHub tools" }));

    expect(await within(group).findByText("1 of 2 on")).toBeInTheDocument();
  });

  it("filters the list by the search box", async () => {
    const user = userEvent.setup();
    renderSection();
    const group = await expandGitHub(user);
    await within(group).findByRole("switch", { name: "Get issue" });

    await user.type(within(group).getByRole("searchbox", { name: "Search GitHub tools" }), "create");

    expect(within(group).getByRole("switch", { name: "Create issue" })).toBeInTheDocument();
    expect(within(group).queryByRole("switch", { name: "Get issue" })).not.toBeInTheDocument();
  });

  it("says when the search matches nothing", async () => {
    const user = userEvent.setup();
    renderSection();
    const group = await expandGitHub(user);
    await within(group).findByRole("switch", { name: "Get issue" });

    await user.type(within(group).getByRole("searchbox", { name: "Search GitHub tools" }), "zzz");

    expect(within(group).getByText("No tools match your search.")).toBeInTheDocument();
  });

  it("shows a tools error with a Retry that loads the list", async () => {
    const user = userEvent.setup();
    mockTools.mockRejectedValueOnce(new Error("GitHub is unavailable"));
    renderSection();

    const group = await expandGitHub(user);
    expect(await within(group).findByRole("alert")).toHaveTextContent("GitHub is unavailable");
    await user.click(within(group).getByRole("button", { name: "Retry loading GitHub tools" }));

    expect(await within(group).findByRole("switch", { name: "Get issue" })).toBeInTheDocument();
  });

  it("explains when the connection ended since the list was read", async () => {
    const user = userEvent.setup();
    mockTools.mockResolvedValue({ ...toolsResponse("github", []), status: "expired" });
    renderSection();

    const group = await expandGitHub(user);

    expect(await within(group).findByText(/no longer connected/)).toBeInTheDocument();
    expect(within(group).queryByRole("switch")).not.toBeInTheDocument();
  });

  it("says when the app offers no tools", async () => {
    const user = userEvent.setup();
    mockTools.mockResolvedValue(toolsResponse("github", []));
    renderSection();

    const group = await expandGitHub(user);

    expect(await within(group).findByText("This app offers no tools.")).toBeInTheDocument();
  });
});

describe("ConnectedAppsSection - writing the grant", () => {
  it("turns a tool on by writing only the connectors key, keeping every other grant", async () => {
    const user = userEvent.setup();
    const onToolsChange = renderSection({
      sel: { tools: { read_files: true, write_files: false, tool_sets: ["playwright"] } },
    });
    const group = await expandGitHub(user);

    await user.click(await within(group).findByRole("switch", { name: "Get issue" }));

    expect(onToolsChange).toHaveBeenCalledTimes(1);
    expect(onToolsChange).toHaveBeenCalledWith({
      read_files: true,
      write_files: false,
      tool_sets: ["playwright"],
      connectors: ["github__get_issue"],
    });
  });

  it("adds to the tools already on, across connectors", async () => {
    const user = userEvent.setup();
    const onToolsChange = renderSection({ sel: { tools: { connectors: ["jira__search_issues"] } } });
    const group = await expandGitHub(user);

    await user.click(await within(group).findByRole("switch", { name: "Get issue" }));

    expect(onToolsChange).toHaveBeenCalledWith({
      read_files: true,
      write_files: true,
      connectors: ["jira__search_issues", "github__get_issue"],
    });
  });

  it("shows a tool that is already on as on", async () => {
    const user = userEvent.setup();
    renderSection({ sel: { tools: { connectors: ["github__create_issue"] } } });
    const group = await expandGitHub(user);

    expect(await within(group).findByRole("switch", { name: "Create issue" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    expect(within(group).getByRole("switch", { name: "Get issue" })).toHaveAttribute(
      "aria-checked",
      "false",
    );
  });

  it("omits the connectors key when the last tool is turned off", async () => {
    const user = userEvent.setup();
    const onToolsChange = renderSection({
      sel: { tools: { read_files: true, write_files: true, connectors: ["github__get_issue"] } },
    });
    const group = await expandGitHub(user);

    await user.click(await within(group).findByRole("switch", { name: "Get issue" }));

    const next = onToolsChange.mock.calls[0][0];
    expect(next).toEqual({ read_files: true, write_files: true });
    expect(next).not.toHaveProperty("connectors");
  });

  it("can be operated from the keyboard", async () => {
    const user = userEvent.setup();
    const onToolsChange = renderSection();
    const group = await expandGitHub(user);
    const toggle = await within(group).findByRole("switch", { name: "Get issue" });

    toggle.focus();
    await user.keyboard("{Enter}");

    expect(onToolsChange).toHaveBeenCalledTimes(1);
  });

  it("lists a tool that is on but no longer offered, and turns it off", async () => {
    const user = userEvent.setup();
    const onToolsChange = renderSection({
      sel: { tools: { connectors: ["github__get_issue", "github__retired_tool"] } },
    });
    const group = await expandGitHub(user);

    expect(await within(group).findByText("On, but this app no longer offers it")).toBeInTheDocument();
    await user.click(within(group).getByRole("button", { name: "Turn off github__retired_tool" }));

    expect(onToolsChange).toHaveBeenCalledWith({
      read_files: true,
      write_files: true,
      connectors: ["github__get_issue"],
    });
  });

  it("keeps a tool on for a connector that needs a connection, and offers Turn off", async () => {
    const user = userEvent.setup();
    const onToolsChange = renderSection({
      sel: { tools: { connectors: ["jira__search_issues", "github__get_issue"] } },
    });

    const group = await screen.findByRole("group", { name: /Jira/ });
    expect(within(group).getByText("On, needs a connection")).toBeInTheDocument();
    await user.click(within(group).getByRole("button", { name: "Turn off jira__search_issues" }));

    expect(onToolsChange).toHaveBeenCalledWith({
      read_files: true,
      write_files: true,
      connectors: ["github__get_issue"],
    });
  });

  it("only lists a connector's own tools under 'needs a connection'", async () => {
    renderSection({ sel: { tools: { connectors: ["github__get_issue"] } } });

    const group = await screen.findByRole("group", { name: /Jira/ });

    expect(within(group).queryByText("On, needs a connection")).not.toBeInTheDocument();
  });
});

describe("ConnectedAppsSection - the per-step limit", () => {
  const SIXTY_FOUR = Array.from({ length: MAX_CONNECTOR_TOOLS }, (_, i) => `github__tool_${i}`);

  it("disables turning on another tool at the limit and says why", async () => {
    const user = userEvent.setup();
    const onToolsChange = renderSection({ sel: { tools: { connectors: SIXTY_FOUR } } });
    const group = await expandGitHub(user);

    const off = await within(group).findByRole("switch", { name: "Get issue" });

    expect(off).toBeDisabled();
    expect(screen.getByRole("status")).toHaveTextContent(LIMIT_NOTE);
    await user.click(off);
    expect(onToolsChange).not.toHaveBeenCalled();
  });

  it("still lets a tool that is on be turned off at the limit", async () => {
    const user = userEvent.setup();
    const onToolsChange = renderSection({
      sel: { tools: { connectors: [...SIXTY_FOUR.slice(1), "github__get_issue"] } },
    });
    const group = await expandGitHub(user);

    const on = await within(group).findByRole("switch", { name: "Get issue" });
    expect(on).toBeEnabled();
    await user.click(on);

    expect(onToolsChange).toHaveBeenCalledTimes(1);
  });

  it("shows no limit note below the limit", async () => {
    renderSection({ sel: { tools: { connectors: SIXTY_FOUR.slice(1) } } });
    await screen.findByRole("group", { name: /GitHub/ });

    expect(screen.queryByText(LIMIT_NOTE)).not.toBeInTheDocument();
  });
});

describe("ConnectedAppsSection - availability", () => {
  it.each<ConnectedAppsAvailability>(["builtin", "override"])(
    "shows the save-a-copy note and disables every switch on a %s canvas",
    async (availability) => {
      const user = userEvent.setup();
      renderSection({ availability });

      const group = await expandGitHub(user);
      const toggle = await within(group).findByRole("switch", { name: "Get issue" });

      expect(screen.getByText(NOT_AVAILABLE_NOTE)).toBeInTheDocument();
      expect(toggle).toBeDisabled();
      expect(within(group).getByRole("switch", { name: "Create issue" })).toBeDisabled();
    },
  );

  it("disables Turn off on an unavailable canvas", async () => {
    mockList.mockResolvedValue({ connectors: [JIRA_OFF] });
    renderSection({ availability: "builtin", sel: { tools: { connectors: ["jira__search_issues"] } } });

    expect(await screen.findByRole("button", { name: "Turn off jira__search_issues" })).toBeDisabled();
  });

  it("shows no note on an available canvas", async () => {
    renderSection({ availability: "available" });
    await screen.findByRole("group", { name: /GitHub/ });

    expect(screen.queryByText(NOT_AVAILABLE_NOTE)).not.toBeInTheDocument();
  });
});
