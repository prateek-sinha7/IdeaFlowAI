import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";

// DesignPickerModal is the one design-selection surface of the composer. The
// shipped galleries/pickers it hosts are rendered for real; only the API
// modules, the auth token lookup and the IntersectionObserver (absent in
// jsdom) are replaced.

class MockIO {
  observe() {}
  disconnect() {}
  unobserve() {}
  takeRecords() {
    return [];
  }
}
vi.stubGlobal("IntersectionObserver", MockIO as unknown as typeof IntersectionObserver);

const mocks = vi.hoisted(() => ({
  getToken: vi.fn<() => string | null>(),
  listPrototypeTemplates: vi.fn(),
  listDesignSystems: vi.fn(),
  listPPTTemplates: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  getToken: mocks.getToken,
}));
vi.mock("@/lib/prototype-api", () => ({
  listPrototypeTemplates: mocks.listPrototypeTemplates,
  listDesignSystems: mocks.listDesignSystems,
  getDesignSystem: vi.fn().mockResolvedValue({
    id: "acme",
    name: "Acme Brand",
    category: "Brand",
    description: "Acme tokens",
    has_preview: true,
    body: "# Acme Brand\n\nPrimary #112233",
  }),
  getDesignSystemPreviewUrl: (id: string) => `/ds-preview/${id}`,
  getTemplatePreviewUrl: (id: string) => `/preview/${id}`,
  getTemplateThumbnailUrl: (id: string) => `/thumb/${id}`,
}));
vi.mock("@/lib/ppt-api", () => ({
  listPPTTemplates: mocks.listPPTTemplates,
  getPPTTemplatePreviewUrl: (id: string) => `/ppt-preview/${id}`,
  getPPTTemplateThumbnailUrl: (id: string) => `/ppt-thumb/${id}`,
}));

import { DesignPickerModal, type DesignSelection } from "./DesignPickerModal";
import type { DesignMode } from "@/types/index";

const webTemplate = {
  id: "alpha",
  name: "Alpha Dashboard",
  description: "A dashboard",
  mode: "prototype",
  platform: null,
  scenario: "design",
  triggers: [],
  craft_required: [],
  example_prompt: null,
  has_preview: true,
  has_thumbnail: false,
};

const deckTemplate = (id: string, name: string, requires: boolean) => ({
  id,
  name,
  description: `${name} deck`,
  mode: "deck",
  platform: null,
  scenario: "design",
  triggers: [],
  craft_required: [],
  example_prompt: null,
  has_preview: true,
  has_thumbnail: false,
  design_system: { requires },
});

const designSystem = {
  id: "acme",
  name: "Acme Brand",
  category: "Brand",
  description: "Acme tokens",
  has_preview: true,
};

const EMPTY: DesignSelection = { templateId: null, designSystemId: null };

/**
 * Stateful host that applies the modal's React-style updaters exactly like the
 * real parents do, and prints the resulting selection so tests can assert on
 * the end state instead of on call choreography.
 */
function Harness({
  initial = EMPTY,
  designMode = "web",
  open = true,
  onClose = () => {},
}: {
  initial?: DesignSelection;
  designMode?: DesignMode;
  open?: boolean;
  onClose?: () => void;
}) {
  const [value, setValue] = useState<DesignSelection>(initial);
  return (
    <>
      <DesignPickerModal
        open={open}
        onClose={onClose}
        designMode={designMode}
        value={value}
        onChange={setValue}
      />
      <output aria-label="current selection">{JSON.stringify(value)}</output>
    </>
  );
}

function selection(): DesignSelection {
  return JSON.parse(screen.getByLabelText("current selection").textContent ?? "{}");
}

beforeEach(() => {
  localStorage.clear();
  mocks.getToken.mockReturnValue("test-token");
  mocks.listPrototypeTemplates.mockResolvedValue([webTemplate]);
  mocks.listDesignSystems.mockResolvedValue([designSystem]);
  mocks.listPPTTemplates.mockResolvedValue([
    deckTemplate("deck-plain", "Plain Deck", false),
    deckTemplate("deck-ds", "Branded Deck", true),
  ]);
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("DesignPickerModal", () => {
  describe("visibility and catalog loading", () => {
    it("renders nothing and fetches nothing when closed", () => {
      render(<Harness open={false} />);

      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
      expect(mocks.listPrototypeTemplates).not.toHaveBeenCalled();
      expect(mocks.listDesignSystems).not.toHaveBeenCalled();
    });

    it("shows an authentication error and skips the catalog fetch when there is no token", async () => {
      mocks.getToken.mockReturnValue(null);

      render(<Harness />);

      expect(await screen.findByText("Not authenticated.")).toBeInTheDocument();
      expect(mocks.listPrototypeTemplates).not.toHaveBeenCalled();
      expect(mocks.listDesignSystems).not.toHaveBeenCalled();
    });

    it("shows a loading message until the catalog resolves", async () => {
      let resolveTemplates: (v: unknown[]) => void = () => {};
      mocks.listPrototypeTemplates.mockReturnValue(
        new Promise((resolve) => {
          resolveTemplates = resolve;
        }),
      );

      render(<Harness />);

      expect(await screen.findByText("Loading the catalog…")).toBeInTheDocument();
      expect(screen.queryByText("Alpha Dashboard")).not.toBeInTheDocument();

      await act(async () => {
        resolveTemplates([webTemplate]);
      });

      expect(await screen.findByText("Alpha Dashboard")).toBeInTheDocument();
      expect(screen.queryByText("Loading the catalog…")).not.toBeInTheDocument();
    });

    it("shows the rejection message when the catalog fails to load", async () => {
      mocks.listPrototypeTemplates.mockRejectedValue(new Error("503 catalog down"));

      render(<Harness />);

      expect(await screen.findByText("503 catalog down")).toBeInTheDocument();
      expect(screen.queryByText("Loading the catalog…")).not.toBeInTheDocument();
    });

    it("falls back to a generic message when the rejection carries no message", async () => {
      mocks.listDesignSystems.mockRejectedValue({});

      render(<Harness />);

      expect(await screen.findByText("Could not load the design catalog.")).toBeInTheDocument();
    });

    it("lists the web catalog for a web workflow", async () => {
      render(<Harness designMode="web" />);

      expect(await screen.findByText("Alpha Dashboard")).toBeInTheDocument();
      expect(screen.getByText("Page templates")).toBeInTheDocument();
      expect(
        screen.getByText("Optional — leave it unpicked to build on a blank canvas."),
      ).toBeInTheDocument();
      expect(mocks.listPrototypeTemplates).toHaveBeenCalledWith("test-token");
      expect(mocks.listPPTTemplates).not.toHaveBeenCalled();
    });

    it("lists the deck catalog for a deck workflow", async () => {
      render(<Harness designMode="deck" />);

      expect(await screen.findByText("Plain Deck")).toBeInTheDocument();
      expect(screen.getByText("Slide templates")).toBeInTheDocument();
      expect(screen.getByText("Required for a deck.")).toBeInTheDocument();
      expect(mocks.listPPTTemplates).toHaveBeenCalledWith("test-token");
      expect(mocks.listPrototypeTemplates).not.toHaveBeenCalled();
    });

    it("ignores a stale response and shows the new shelf when the design mode changes mid-flight", async () => {
      let resolveWeb: (v: unknown[]) => void = () => {};
      mocks.listPrototypeTemplates.mockReturnValue(
        new Promise((resolve) => {
          resolveWeb = resolve;
        }),
      );
      const { rerender } = render(<Harness designMode="web" />);
      await screen.findByText("Loading the catalog…");

      rerender(<Harness designMode="deck" />);
      expect(await screen.findByText("Plain Deck")).toBeInTheDocument();

      await act(async () => {
        resolveWeb([webTemplate]);
      });

      expect(screen.queryByText("Alpha Dashboard")).not.toBeInTheDocument();
      expect(screen.getByText("Plain Deck")).toBeInTheDocument();
    });

    it("does not surface a late failure after the modal has unmounted", async () => {
      let rejectTemplates: (e: Error) => void = () => {};
      mocks.listPrototypeTemplates.mockReturnValue(
        new Promise((_, reject) => {
          rejectTemplates = reject;
        }),
      );
      const { unmount } = render(<Harness />);
      await screen.findByText("Loading the catalog…");

      unmount();
      await act(async () => {
        rejectTemplates(new Error("late failure"));
      });

      expect(screen.queryByText("late failure")).not.toBeInTheDocument();
    });
  });

  describe("dismissal", () => {
    it("closes on Escape while open", async () => {
      const user = userEvent.setup();
      const onClose = vi.fn();
      render(<Harness onClose={onClose} />);
      await screen.findByText("Alpha Dashboard");

      await user.keyboard("{Escape}");

      expect(onClose).toHaveBeenCalledTimes(1);
    });

    it("ignores other keys", async () => {
      const user = userEvent.setup();
      const onClose = vi.fn();
      render(<Harness onClose={onClose} />);
      await screen.findByText("Alpha Dashboard");

      await user.keyboard("a{Enter}");

      expect(onClose).not.toHaveBeenCalled();
    });

    it("stops listening for Escape once closed", async () => {
      const user = userEvent.setup();
      const onClose = vi.fn();
      const { rerender } = render(<Harness onClose={onClose} />);
      await screen.findByText("Alpha Dashboard");

      rerender(<Harness open={false} onClose={onClose} />);
      await user.keyboard("{Escape}");

      expect(onClose).not.toHaveBeenCalled();
    });

    it("closes from the Close button and the Done button", async () => {
      const user = userEvent.setup();
      const onClose = vi.fn();
      render(<Harness onClose={onClose} />);
      await screen.findByText("Alpha Dashboard");

      await user.click(screen.getByRole("button", { name: "Close" }));
      await user.click(screen.getByRole("button", { name: "Done" }));

      expect(onClose).toHaveBeenCalledTimes(2);
    });

    it("closes on a backdrop click but not on a click inside the panel", async () => {
      const user = userEvent.setup();
      const onClose = vi.fn();
      render(<Harness onClose={onClose} />);
      await screen.findByText("Alpha Dashboard");
      const dialog = screen.getByRole("dialog", { name: "Choose a design" });

      await user.click(screen.getByRole("heading", { name: "Choose a design" }));
      expect(onClose).not.toHaveBeenCalled();

      await user.click(dialog);
      expect(onClose).toHaveBeenCalledTimes(1);
    });
  });

  describe("tabs", () => {
    it("starts on the Template tab and switches to the Design system tab", async () => {
      const user = userEvent.setup();
      render(<Harness />);
      await screen.findByText("Alpha Dashboard");

      expect(screen.getByRole("button", { name: "Template" })).toHaveAttribute(
        "aria-pressed",
        "true",
      );
      expect(screen.getByRole("button", { name: "Design system" })).toHaveAttribute(
        "aria-pressed",
        "false",
      );

      await user.click(screen.getByRole("button", { name: "Design system" }));

      expect(screen.getByRole("button", { name: "Design system" })).toHaveAttribute(
        "aria-pressed",
        "true",
      );
      expect(screen.queryByText("Alpha Dashboard")).not.toBeInTheDocument();
      expect(screen.getByRole("heading", { name: "Choose a design system" })).toBeInTheDocument();
    });

    it("tells a web workflow that a design system is always required", async () => {
      const user = userEvent.setup();
      render(<Harness designMode="web" />);
      await screen.findByText("Alpha Dashboard");

      await user.click(screen.getByRole("button", { name: "Design system" }));

      expect(
        screen.getByText("Required — supplies the colour, type and spacing tokens."),
      ).toBeInTheDocument();
    });

    it("calls a design system optional for a deck whose template does not need one", async () => {
      const user = userEvent.setup();
      render(<Harness designMode="deck" initial={{ templateId: "deck-plain", designSystemId: null }} />);
      await screen.findByText("Plain Deck");

      await user.click(screen.getByRole("button", { name: "Design system" }));

      expect(
        screen.getByText("Optional — this template brings its own styling."),
      ).toBeInTheDocument();
    });

    it("calls a design system required for a deck whose template opts in", async () => {
      const user = userEvent.setup();
      render(<Harness designMode="deck" initial={{ templateId: "deck-ds", designSystemId: null }} />);
      await screen.findByText("Branded Deck");

      await user.click(screen.getByRole("button", { name: "Design system" }));

      expect(
        screen.getByText("Required — supplies the colour, type and spacing tokens."),
      ).toBeInTheDocument();
    });

    it("calls a design system optional for a deck with no template picked yet", async () => {
      const user = userEvent.setup();
      render(<Harness designMode="deck" />);
      await screen.findByText("Plain Deck");

      await user.click(screen.getByRole("button", { name: "Design system" }));

      expect(
        screen.getByText("Optional — this template brings its own styling."),
      ).toBeInTheDocument();
    });
  });

  describe("template selection", () => {
    it("records the picked web template with its display name", async () => {
      const user = userEvent.setup();
      render(<Harness />);

      await user.click(await screen.findByRole("button", { name: /Alpha Dashboard/ }));
      const detail = await screen.findByRole("dialog", { name: "Alpha Dashboard preview" });
      await user.click(within(detail).getByRole("button", { name: "Use this template" }));

      expect(selection()).toMatchObject({
        templateId: "alpha",
        templateName: "Alpha Dashboard",
        customTemplateBody: null,
      });
    });

    it("clears the template and its name when the blank-canvas card is chosen", async () => {
      const user = userEvent.setup();
      render(
        <Harness
          initial={{ templateId: "alpha", designSystemId: null, templateName: "Alpha Dashboard" }}
        />,
      );

      await user.click(await screen.findByRole("button", { name: /Default Template/ }));

      expect(selection()).toMatchObject({
        templateId: null,
        templateName: null,
        customTemplateBody: null,
      });
    });

    it("keeps the other half of the selection when a template is picked", async () => {
      const user = userEvent.setup();
      render(<Harness initial={{ templateId: null, designSystemId: "acme", designSystemName: "Acme Brand" }} />);

      await user.click(await screen.findByRole("button", { name: /Alpha Dashboard/ }));
      await user.click(
        within(await screen.findByRole("dialog", { name: "Alpha Dashboard preview" })).getByRole(
          "button",
          { name: "Use this template" },
        ),
      );

      expect(selection()).toMatchObject({
        templateId: "alpha",
        designSystemId: "acme",
        designSystemName: "Acme Brand",
      });
    });

    it("records the picked deck template with its display name", async () => {
      const user = userEvent.setup();
      render(<Harness designMode="deck" />);

      await user.click(await screen.findByRole("button", { name: /Branded Deck/ }));
      await user.click(await screen.findByRole("button", { name: "Use this template" }));

      expect(selection()).toMatchObject({
        templateId: "deck-ds",
        templateName: "Branded Deck",
      });
    });

    it("selects an uploaded custom template and stores its body without losing the id", async () => {
      const user = userEvent.setup();
      localStorage.setItem(
        "prototype.customTemplates",
        JSON.stringify([
          {
            id: "custom-1",
            name: "My Landing",
            body: "<html>landing</html>",
            source: "file",
            sourceRef: "landing.html",
          },
        ]),
      );
      render(<Harness />);

      await user.click(await screen.findByRole("button", { name: /My Landing/ }));

      expect(selection()).toMatchObject({
        templateId: "custom-1",
        templateName: "My Landing",
        customTemplateBody: "<html>landing</html>",
      });
    });

    it("drops an uploaded template body along with its id when the blank-canvas card is chosen", async () => {
      const user = userEvent.setup();
      render(
        <Harness
          initial={{
            templateId: "custom-1",
            designSystemId: null,
            customTemplateBody: "<html>landing</html>",
          }}
        />,
      );

      await user.click(await screen.findByRole("button", { name: /Default Template/ }));

      expect(selection()).toMatchObject({ templateId: null, customTemplateBody: null });
    });
  });

  describe("design system selection", () => {
    async function openSystemTab(user: ReturnType<typeof userEvent.setup>) {
      await screen.findByText("Alpha Dashboard");
      await user.click(screen.getByRole("button", { name: "Design system" }));
    }

    it("records the picked design system with its display name", async () => {
      const user = userEvent.setup();
      render(<Harness />);
      await openSystemTab(user);

      await user.click(await screen.findByRole("button", { name: "Select Acme Brand" }));

      expect(selection()).toMatchObject({
        designSystemId: "acme",
        designSystemName: "Acme Brand",
        customDsBody: null,
      });
    });

    it("clears the design system and its name through the picker's Clear selection control", async () => {
      const user = userEvent.setup();
      render(
        <Harness
          initial={{
            templateId: "alpha",
            designSystemId: "acme",
            designSystemName: "Acme Brand",
          }}
        />,
      );
      await openSystemTab(user);

      await user.click(await screen.findByRole("button", { name: "Clear selection" }));

      expect(selection()).toMatchObject({
        templateId: "alpha",
        designSystemId: null,
        designSystemName: null,
        customDsBody: null,
      });
    });

    it("stores an uploaded custom design system's id, name and body", async () => {
      const user = userEvent.setup();
      render(<Harness />);
      await openSystemTab(user);

      await user.click(await screen.findByRole("button", { name: "Upload custom" }));
      const dialog = await screen.findByRole("dialog", { name: "Add custom design system" });
      await user.type(within(dialog).getByLabelText(/^Name/), "Zeta Brand");
      const body = "# Zeta Brand\n\nA complete design system with enough content to pass validation.";
      await user.click(within(dialog).getByLabelText(/DESIGN\.md content/));
      await user.paste(body);
      await user.click(within(dialog).getByRole("button", { name: "Add design system" }));

      await waitFor(() =>
        expect(selection()).toMatchObject({
          designSystemId: "custom:zeta-brand",
          designSystemName: "Zeta Brand",
          customDsBody: body,
        }),
      );
    });

    it("clears only the uploaded body when the custom system is deselected", async () => {
      const user = userEvent.setup();
      localStorage.setItem(
        "flowin.custom_design_systems",
        JSON.stringify([
          { id: "custom:zeta", name: "Zeta", body: "# Zeta", createdAt: 1 },
        ]),
      );
      render(
        <Harness
          initial={{
            templateId: "alpha",
            designSystemId: "custom:zeta",
            designSystemName: "Zeta",
            customDsBody: "# Zeta",
          }}
        />,
      );
      await openSystemTab(user);

      await user.click(await screen.findByRole("button", { name: /^Zeta$/ }));

      expect(selection()).toMatchObject({
        templateId: "alpha",
        designSystemId: null,
        designSystemName: null,
        customDsBody: null,
      });
    });
  });
});
