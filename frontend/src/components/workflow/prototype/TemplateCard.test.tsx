import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TemplateCard } from "./TemplateCard";
import type { PrototypeTemplate } from "@/lib/prototype-api";

type IOCallback = (entries: Array<{ isIntersecting: boolean }>) => void;

let ioCallbacks: IOCallback[] = [];
const disconnect = vi.fn();
const observe = vi.fn();

beforeEach(() => {
  ioCallbacks = [];
  disconnect.mockClear();
  observe.mockClear();
  vi.stubGlobal(
    "IntersectionObserver",
    class {
      constructor(cb: IOCallback) {
        ioCallbacks.push(cb);
      }
      observe = observe;
      disconnect = disconnect;
      unobserve = vi.fn();
      takeRecords = vi.fn();
    },
  );
});
afterEach(() => vi.unstubAllGlobals());

const base: PrototypeTemplate = {
  id: "tpl 1",
  name: "Landing",
  description: "A landing page",
  mode: null,
  platform: "web",
  scenario: null,
  triggers: [],
  craft_required: [],
  example_prompt: null,
  has_preview: true,
  has_thumbnail: false,
};

function setup(template: Partial<PrototypeTemplate> = {}, selected = false) {
  const onSelect = vi.fn();
  const onOpenDetail = vi.fn();
  const utils = render(
    <TemplateCard
      template={{ ...base, ...template }}
      selected={selected}
      onSelect={onSelect}
      onOpenDetail={onOpenDetail}
    />,
  );
  return { onSelect, onOpenDetail, ...utils };
}

const intersect = () => act(() => ioCallbacks[0]([{ isIntersecting: true }]));

describe("TemplateCard", () => {
  it("renders name, description and platform pill; click opens detail", async () => {
    const user = userEvent.setup();
    const { onOpenDetail, onSelect } = setup();
    expect(screen.getByText("Landing")).toBeInTheDocument();
    expect(screen.getByText("A landing page")).toBeInTheDocument();
    expect(screen.getByText("web")).toBeInTheDocument();
    await user.click(screen.getByRole("button"));
    expect(onOpenDetail).toHaveBeenCalledWith("tpl 1");
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("omits the platform pill when platform is null", () => {
    setup({ platform: null });
    expect(screen.queryByText("web")).not.toBeInTheDocument();
  });

  it("shows no-preview placeholder when there is no preview or thumbnail", () => {
    setup({ has_preview: false });
    expect(screen.getByText("No preview available")).toBeInTheDocument();
  });

  it("shows loading placeholder until the card intersects, then mounts a sandboxed iframe", () => {
    setup();
    expect(screen.getByText("Loading preview…")).toBeInTheDocument();
    expect(document.querySelector("iframe")).toBeNull();

    intersect();
    const frame = screen.getByTitle("Landing preview") as HTMLIFrameElement;
    expect(frame).toHaveAttribute("sandbox", "allow-scripts");
    expect(frame.getAttribute("src")).toContain("/api/prototype/templates/tpl%201/preview");
    expect(frame.style.opacity).toBe("0");
    expect(disconnect).toHaveBeenCalled();

    fireEvent.load(frame);
    expect(frame.style.opacity).toBe("1");
  });

  it("ignores non-intersecting observer entries", () => {
    setup();
    act(() => ioCallbacks[0]([{ isIntersecting: false }]));
    expect(screen.getByText("Loading preview…")).toBeInTheDocument();
  });

  it("disconnects the observer on unmount", () => {
    const { unmount } = setup();
    disconnect.mockClear();
    unmount();
    expect(disconnect).toHaveBeenCalled();
  });

  it("renders a thumbnail image and reveals it on load", () => {
    setup({ has_thumbnail: true });
    const img = screen.getByAltText("Landing preview") as HTMLImageElement;
    expect(img.getAttribute("src")).toContain("/api/prototype/templates/tpl%201/thumbnail");
    expect(img.style.opacity).toBe("0");
    fireEvent.load(img);
    expect(img.style.opacity).toBe("1");
  });

  it("falls back to the live iframe when the thumbnail errors", () => {
    setup({ has_thumbnail: true });
    fireEvent.error(screen.getByAltText("Landing preview"));
    expect(screen.queryByAltText("Landing preview")).not.toBeInTheDocument();
    expect(screen.getByTitle("Landing preview")).toBeInTheDocument();
  });

  it("falls back to the placeholder when thumbnail errors and no preview exists", () => {
    setup({ has_thumbnail: true, has_preview: false });
    fireEvent.error(screen.getByAltText("Landing preview"));
    expect(screen.getByText("No preview available")).toBeInTheDocument();
  });

  it("shows the selected indicator only when selected", () => {
    const { container, unmount } = setup({}, true);
    expect(container.querySelector("svg")).not.toBeNull();
    unmount();
    const second = setup({}, false);
    expect(second.container.querySelector("svg")).toBeNull();
  });
});
