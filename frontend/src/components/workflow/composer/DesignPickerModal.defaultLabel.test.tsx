import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

// ISS-731 — sibling of ISS-694: DesignPickerModal's Web design-mode step
// reuses TemplateGallery, so the same blank-canvas card mislabel ("No
// template" instead of "Default Template") reaches the composer's shared
// design picker (opened from IdeaInputPage and ComposerPage), not just the
// prototype wizard. Pins the correct copy for that reuse path.

class MockIO {
  observe() {}
  disconnect() {}
  unobserve() {}
  takeRecords() {
    return [];
  }
}
vi.stubGlobal("IntersectionObserver", MockIO as unknown as typeof IntersectionObserver);

vi.mock("@/lib/api", () => ({
  getToken: () => "test-token",
}));
vi.mock("@/lib/prototype-api", () => ({
  listPrototypeTemplates: vi.fn().mockResolvedValue([
    { id: "alpha", name: "Alpha Dashboard", scenario: "design", has_preview: true },
  ]),
  listDesignSystems: vi.fn().mockResolvedValue([]),
  getTemplatePreviewUrl: (id: string) => `/preview/${id}`,
  getTemplateThumbnailUrl: (id: string) => `/thumb/${id}`,
}));
vi.mock("@/lib/ppt-api", () => ({
  listPPTTemplates: vi.fn().mockResolvedValue([]),
}));

import { DesignPickerModal } from "./DesignPickerModal";

describe("DesignPickerModal — Web design-mode blank-canvas card label (ISS-731)", () => {
  it("labels the blank-canvas card 'Default Template', not 'No template'", async () => {
    render(
      <DesignPickerModal
        open={true}
        onClose={vi.fn()}
        designMode="web"
        value={{ templateId: null, designSystemId: null }}
        onChange={vi.fn()}
      />,
    );

    await waitFor(() => expect(screen.getByText("Alpha Dashboard")).toBeInTheDocument());

    expect(screen.getByText("Default Template")).toBeInTheDocument();
    expect(screen.queryByText("No template")).not.toBeInTheDocument();
  });
});
