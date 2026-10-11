import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { PPTTemplate } from "@/lib/ppt-api";
import { PPTTemplateGallery } from "./PPTTemplateGallery";

vi.mock("@/lib/ppt-api", () => ({
  getPPTTemplatePreviewUrl: (id: string) => `/preview/${id}`,
  getPPTTemplateThumbnailUrl: (id: string) => `/thumb/${id}.png`,
}));

const STORAGE_KEY = "prototype.customTemplates";

let observers: Array<{ cb: IntersectionObserverCallback; disconnect: ReturnType<typeof vi.fn> }> = [];

function makeTemplate(over: Partial<PPTTemplate> & { id: string; name: string }): PPTTemplate {
  return {
    description: "",
    mode: null,
    platform: null,
    scenario: null,
    triggers: [],
    craft_required: [],
    example_prompt: null,
    has_preview: true,
    has_thumbnail: false,
    design_system: {},
    ...over,
  };
}

function intersectAll() {
  act(() => {
    for (const o of observers) {
      o.cb([{ isIntersecting: true } as IntersectionObserverEntry], {} as IntersectionObserver);
    }
  });
}

const templates: PPTTemplate[] = [
  makeTemplate({ id: "pitch", name: "Investor Pitch", description: "raise money", triggers: ["vc"], mode: "deck" }),
  makeTemplate({ id: "tech", name: "Tech Talk", has_thumbnail: true }),
  makeTemplate({ id: "mag", name: "Magazine Style" }),
  makeTemplate({ id: "wk", name: "Weekly Report" }),
  makeTemplate({ id: "min", name: "Minimal Clean" }),
  makeTemplate({ id: "cr", name: "Zebra", scenario: "design" }),
  makeTemplate({ id: "land", name: "Landing Page" }),
  makeTemplate({ id: "other", name: "Plain", design_system: { requires: true } }),
  makeTemplate({ id: "nopreview", name: "Hidden", has_preview: false }),
];

const custom = [
  { id: "c1", name: "My Deck", body: "<html/>", source: "file", sourceRef: "deck.html" },
  { id: "c2", name: "Remote", body: "<html/>", source: "url", sourceRef: "https://x.test" },
];

beforeEach(() => {
  observers = [];
  localStorage.clear();
  vi.stubGlobal(
    "IntersectionObserver",
    class {
      disconnect = vi.fn();
      observe = vi.fn();
      constructor(cb: IntersectionObserverCallback) {
        observers.push({ cb, disconnect: this.disconnect });
      }
    },
  );
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function setup(props: Partial<React.ComponentProps<typeof PPTTemplateGallery>> = {}) {
  const onSelect = vi.fn();
  const onSelectCustomTemplate = vi.fn();
  const user = userEvent.setup();
  // Used only for the Remove clicks, which previously bypassed the pointer-events check per call.
  const removeUser = userEvent.setup({ pointerEventsCheck: 0 });
  const utils = render(
    <PPTTemplateGallery
      templates={templates}
      selectedId={null}
      onSelect={onSelect}
      onSelectCustomTemplate={onSelectCustomTemplate}
      {...props}
    />,
  );
  return { user, removeUser, onSelect, onSelectCustomTemplate, ...utils };
}

describe("PPTTemplateGallery", () => {
  it("renders only templates with previews and a footer count", () => {
    setup();
    expect(screen.getByText("Investor Pitch")).toBeInTheDocument();
    expect(screen.queryByText("Hidden")).not.toBeInTheDocument();
    expect(screen.getByText("8 templates")).toBeInTheDocument();
  });

  it("uses singular footer text for one template", async () => {
    const { user } = setup({ templates: [templates[0]] });
    expect(screen.getByText("1 template")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Tech" }));
    expect(screen.getByText("No templates match your search.")).toBeInTheDocument();
    expect(screen.getByText("0 templates · Tech")).toBeInTheDocument();
  });

  it.each([
    ["Pitch Deck", "Investor Pitch"],
    ["Tech", "Tech Talk"],
    ["Editorial", "Magazine Style"],
    ["Business", "Weekly Report"],
    ["Minimal", "Minimal Clean"],
    ["Creative", "Zebra"],
  ])("filters by %s category", async (cat, expected) => {
    const { user } = setup();
    await user.click(screen.getByRole("button", { name: cat }));
    expect(screen.getByText(expected)).toBeInTheDocument();
    expect(screen.queryByText("Plain")).not.toBeInTheDocument();
  });

  it("buckets landing pages as Creative", async () => {
    const { user } = setup();
    await user.click(screen.getByRole("button", { name: "Creative" }));
    expect(screen.getByText("Landing Page")).toBeInTheDocument();
  });

  it("filters by search over name, description and triggers", async () => {
    const { user } = setup();
    const input = screen.getByLabelText("Search templates");
    await user.type(input, "raise");
    expect(screen.getByText("Investor Pitch")).toBeInTheDocument();
    expect(screen.queryByText("Tech Talk")).not.toBeInTheDocument();
    await user.clear(input);
    await user.type(input, "VC");
    expect(screen.getByText("Investor Pitch")).toBeInTheDocument();
    await user.clear(input);
    await user.type(input, "zzzz");
    expect(screen.getByText("No templates match your search.")).toBeInTheDocument();
  });

  it("shows custom templates, count badge and selects them", async () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(custom));
    const { user, onSelectCustomTemplate } = setup({ selectedCustomTemplateId: "c1" });
    expect(screen.getByText("My Deck")).toBeInTheDocument();
    expect(screen.getByText("HTML file")).toBeInTheDocument();
    expect(screen.getByText("From URL")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /My Deck/ }));
    expect(onSelectCustomTemplate).toHaveBeenCalledWith(expect.objectContaining({ id: "c1" }));
    await user.click(screen.getByRole("button", { name: /Custom/ }));
    expect(screen.getByText("2 custom templates")).toBeInTheDocument();
  });

  it("does not throw when selecting a custom template without a handler", async () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(custom));
    const { user, removeUser } = setup({ onSelectCustomTemplate: undefined });
    await user.click(screen.getByRole("button", { name: /My Deck/ }));
    await removeUser.click(screen.getAllByTitle("Remove")[0]);
    expect(screen.queryByText("My Deck")).not.toBeInTheDocument();
  });

  it("deletes a custom template and clears selection if selected", async () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(custom));
    const { removeUser, onSelectCustomTemplate } = setup({ selectedCustomTemplateId: "c1" });
    await removeUser.click(screen.getAllByTitle("Remove")[0]);
    expect(onSelectCustomTemplate).toHaveBeenCalledWith(null);
    expect(JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "[]")).toHaveLength(1);
  });

  it("deletes an unselected custom template in the Custom tab without clearing selection", async () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(custom));
    const { user, removeUser, onSelectCustomTemplate } = setup({ selectedCustomTemplateId: "c2" });
    await user.click(screen.getByRole("button", { name: /Custom/ }));
    await removeUser.click(screen.getAllByTitle("Remove")[0]);
    expect(onSelectCustomTemplate).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: /My Deck|Remote/ }));
    expect(onSelectCustomTemplate).toHaveBeenCalled();
  });

  it("deletes the selected custom template from the Custom tab", async () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify([custom[0]]));
    const { user, removeUser, onSelectCustomTemplate } = setup({ selectedCustomTemplateId: "c1" });
    await user.click(screen.getByRole("button", { name: /Custom/ }));
    await removeUser.click(screen.getByTitle("Remove"));
    expect(onSelectCustomTemplate).toHaveBeenCalledWith(null);
    expect(screen.getByText("No custom templates yet")).toBeInTheDocument();
    expect(screen.getByText("0 custom templates")).toBeInTheDocument();
  });

  it("filters custom templates by search and shows singular footer", async () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(custom));
    const { user } = setup();
    await user.click(screen.getByRole("button", { name: /Custom/ }));
    await user.type(screen.getByLabelText("Search templates"), "remote");
    expect(screen.queryByText("My Deck")).not.toBeInTheDocument();
    expect(screen.getByText("Remote")).toBeInTheDocument();
    expect(screen.getByText("2 custom templates")).toBeInTheDocument();
  });

  it("selecting a custom template in Custom tab calls handler", async () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify([custom[0]]));
    const { user } = setup({ onSelectCustomTemplate: undefined });
    await user.click(screen.getByRole("button", { name: /Custom/ }));
    await user.click(screen.getByRole("button", { name: /My Deck/ }));
    expect(screen.getByText("1 custom template")).toBeInTheDocument();
  });

  it("opens and closes the upload modal from both entry points", async () => {
    const { user } = setup();
    await user.click(screen.getByRole("button", { name: /Upload custom$/ }));
    expect(screen.getByRole("button", { name: /cancel|close/i })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /cancel|close/i }));
    await user.click(screen.getByRole("button", { name: /Custom/ }));
    await user.click(screen.getByRole("button", { name: /Upload custom template/ }));
    expect(screen.getByRole("button", { name: /cancel|close/i })).toBeInTheDocument();
  });

  it("opens the detail modal, selects a template and closes", async () => {
    const { user, onSelect } = setup();
    await user.click(screen.getByRole("button", { name: /Investor Pitch/ }));
    const dialogTitle = screen.getByRole("heading", { name: "Investor Pitch" });
    expect(dialogTitle).toBeInTheDocument();
    expect(screen.getByText("raise money")).toBeInTheDocument();
    expect(screen.getByText("Loading preview…")).toBeInTheDocument();
    const frame = screen.getByTitle("Investor Pitch");
    expect(frame).toHaveAttribute("sandbox");
    act(() => frame.dispatchEvent(new Event("load")));
    expect(screen.queryByText("Loading preview…")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Use this template" }));
    expect(onSelect).toHaveBeenCalledWith("pitch");
    expect(screen.queryByRole("heading", { name: "Investor Pitch" })).not.toBeInTheDocument();
  });

  it("detail modal shows selected state, design system badge and mode", async () => {
    const { user } = setup({ selectedId: "other" });
    await user.click(screen.getByRole("button", { name: /Plain/ }));
    expect(screen.getByText("Uses design system")).toBeInTheDocument();
    expect(screen.getByText("Selected")).toBeInTheDocument();
  });

  it("detail modal opens preview in a new tab", async () => {
    const open = vi.spyOn(window, "open").mockReturnValue(null);
    const { user } = setup();
    await user.click(screen.getByRole("button", { name: /Investor Pitch/ }));
    expect(screen.getByText("deck", { selector: "span.rounded-full" })).toBeInTheDocument();
    await user.click(screen.getByTitle("Open preview in new tab"));
    expect(open).toHaveBeenCalledWith("/preview/pitch", "_blank");
  });

  it("closes the detail modal with Escape, backdrop and close button", async () => {
    const { user } = setup();
    const heading = () => screen.queryByRole("heading", { name: "Tech Talk" });
    await user.click(screen.getByRole("button", { name: /Tech Talk/ }));
    expect(heading()).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(heading()).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Tech Talk/ }));
    const modalRoot = screen.getByRole("heading", { name: "Tech Talk" }).closest(".fixed") as HTMLElement;
    await user.click(modalRoot.firstElementChild as HTMLElement);
    expect(heading()).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Tech Talk/ }));
    const header = screen.getByRole("heading", { name: "Tech Talk" }).closest(".border-b") as HTMLElement;
    const buttons = within(header).getAllByRole("button");
    await user.click(buttons[buttons.length - 1]);
    expect(heading()).not.toBeInTheDocument();
  });

  it("ignores non-Escape keys in the detail modal", async () => {
    const { user } = setup();
    await user.click(screen.getByRole("button", { name: /Tech Talk/ }));
    await user.keyboard("a");
    expect(screen.getByRole("heading", { name: "Tech Talk" })).toBeInTheDocument();
  });

  describe("card previews", () => {
    it("renders a placeholder until visible, then the thumbnail image", () => {
      setup({ templates: [templates[1]] });
      expect(screen.queryByRole("img")).not.toBeInTheDocument();
      intersectAll();
      const img = screen.getByRole("img", { name: "Tech Talk" });
      expect(img).toHaveAttribute("src", "/thumb/tech.png");
      act(() => img.dispatchEvent(new Event("load")));
      expect(img).toHaveStyle({ opacity: "1" });
    });

    it("ignores non-intersecting entries", () => {
      setup({ templates: [templates[1]] });
      act(() => {
        observers[0].cb([{ isIntersecting: false } as IntersectionObserverEntry], {} as IntersectionObserver);
      });
      expect(screen.queryByRole("img")).not.toBeInTheDocument();
    });

    it("renders an iframe when no thumbnail exists", () => {
      setup({ templates: [templates[0]] });
      intersectAll();
      const frame = screen.getByTitle("Investor Pitch");
      expect(frame).toHaveAttribute("src", "/preview/pitch");
      act(() => frame.dispatchEvent(new Event("load")));
      expect(frame).toHaveStyle({ opacity: "1" });
    });

    it("retries a failed thumbnail once then falls back to the iframe", () => {
      vi.useFakeTimers();
      setup({ templates: [templates[1]] });
      intersectAll();
      const img = screen.getByRole("img", { name: "Tech Talk" });
      act(() => img.dispatchEvent(new Event("error")));
      // second error before timer fires resets pending timer
      act(() => img.dispatchEvent(new Event("error")));
      act(() => { vi.advanceTimersByTime(800); });
      expect(screen.getByRole("img", { name: "Tech Talk" })).toHaveAttribute("src", "/thumb/tech.png?retry=1");
      act(() => screen.getByRole("img", { name: "Tech Talk" }).dispatchEvent(new Event("error")));
      expect(screen.queryByRole("img")).not.toBeInTheDocument();
      expect(screen.getByTitle("Tech Talk")).toHaveAttribute("src", "/preview/tech");
    });

    it("clears a pending retry timer on unmount", () => {
      vi.useFakeTimers();
      const clear = vi.spyOn(globalThis, "clearTimeout");
      const { unmount } = setup({ templates: [templates[1]] });
      intersectAll();
      act(() => screen.getByRole("img").dispatchEvent(new Event("error")));
      unmount();
      expect(clear).toHaveBeenCalled();
      expect(observers[0].disconnect).toHaveBeenCalled();
    });

    it("shows the selected check and mode label on the card", () => {
      setup({ selectedId: "pitch", templates: [templates[0]] });
      expect(screen.getByText("deck")).toBeInTheDocument();
    });
  });
});
