import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FigmaUploadSection, type FigmaFrame } from "./FigmaUploadSection";

// Mock jszip to avoid the dynamic import in FigmaUploadSection
vi.mock("jszip", () => ({
  default: class MockJSZip {
    files: Record<string, { dir: boolean; async: (type: string) => Promise<Blob> }> = {};
    static loadAsync() { return Promise.resolve(new MockJSZip()); }
  },
}));

// ─────────────────────────────────────────────────────────────────
// Stubs for URL.createObjectURL / URL.revokeObjectURL
// ─────────────────────────────────────────────────────────────────

const mockObjectURL = "blob:http://localhost/mock-preview";

function makeFile(name: string, type: string, sizeBytes = 100): File {
  return new File([new Uint8Array(sizeBytes)], name, { type });
}

function renderSection(frames: FigmaFrame[] = [], onChange = vi.fn()) {
  return { onChange, ...render(<FigmaUploadSection frames={frames} onChange={onChange} />) };
}

// ─────────────────────────────────────────────────────────────────
// Tests
// ─────────────────────────────────────────────────────────────────

describe("FigmaUploadSection", () => {
  beforeEach(() => {
    // Stub only the specific methods — replacing the whole URL global breaks the runner
    global.URL.createObjectURL = vi.fn(() => mockObjectURL);
    global.URL.revokeObjectURL = vi.fn();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });
  it("renders_dashed_empty_state_when_frames_is_empty", () => {
    renderSection();
    expect(screen.getByText(/Drop Figma screens here/i)).toBeDefined();
    expect(screen.getByRole("button", { name: /Browse files/i })).toBeDefined();
  });

  it("calls_onChange_with_new_frame_when_valid_png_dropped", async () => {
    const { onChange } = renderSection();
    const file = makeFile("screen.png", "image/png");
    const input = document.querySelector('input[type="file"][accept=".png,.jpg,.jpeg"]') as HTMLInputElement;
    await userEvent.upload(input, file);
    expect(onChange).toHaveBeenCalledOnce();
    const frames = onChange.mock.calls[0][0] as FigmaFrame[];
    expect(frames).toHaveLength(1);
    expect(frames[0].file.name).toBe("screen.png");
  });

  it("calls_onChange_when_valid_jpg_uploaded_via_file_input", async () => {
    const { onChange } = renderSection();
    const file = makeFile("screen.jpg", "image/jpeg");
    const input = document.querySelector('input[type="file"][accept=".png,.jpg,.jpeg"]') as HTMLInputElement;
    await userEvent.upload(input, file);
    expect(onChange).toHaveBeenCalledOnce();
    const frames = onChange.mock.calls[0][0] as FigmaFrame[];
    expect(frames[0].file.name).toBe("screen.jpg");
  });

  it("shows_fig_rejection_error_when_fig_file_dropped", async () => {
    renderSection();
    const file = makeFile("design.fig", "application/octet-stream");
    const input = document.querySelector('input[type="file"][accept=".png,.jpg,.jpeg"]') as HTMLInputElement;
    await userEvent.upload(input, file);
    expect(screen.getByText(/export your screens as PNG from Figma/i)).toBeDefined();
  });

  it("shows_size_error_when_file_exceeds_4mb", async () => {
    renderSection();
    const bigFile = makeFile("big.png", "image/png", 4 * 1024 * 1024 + 1);
    const input = document.querySelector('input[type="file"][accept=".png,.jpg,.jpeg"]') as HTMLInputElement;
    await userEvent.upload(input, bigFile);
    expect(screen.getByText(/too large/i)).toBeDefined();
  });

  it("shows_count_error_when_21st_frame_added", async () => {
    // Seed 20 frames
    const existingFrames: FigmaFrame[] = Array.from({ length: 20 }, (_, i) => ({
      file: makeFile(`frame-${i}.png`, "image/png"),
      description: "",
      previewUrl: `blob:http://localhost/mock-${i}`,
    }));
    renderSection(existingFrames);
    const file = makeFile("extra.png", "image/png");
    const input = document.querySelector('input[type="file"][accept=".png,.jpg,.jpeg"]') as HTMLInputElement;
    await userEvent.upload(input, file);
    expect(screen.getByText(/Maximum 20 frames reached/i)).toBeDefined();
  });

  it("calls_revokeObjectURL_and_onChange_when_frame_removed", async () => {
    const user = userEvent.setup();
    const frame: FigmaFrame = {
      file: makeFile("s.png", "image/png"),
      description: "",
      previewUrl: mockObjectURL,
    };
    const onChange = vi.fn();
    render(<FigmaUploadSection frames={[frame]} onChange={onChange} />);

    // Hover the card to reveal X button then click it
    const removeBtn = screen.getByTitle("Remove frame");
    await user.click(removeBtn);

    expect((URL.revokeObjectURL as ReturnType<typeof vi.fn>)).toHaveBeenCalledWith(mockObjectURL);
    expect(onChange).toHaveBeenCalledWith([]);
  });

  it("shows_N_of_20_badge_when_frames_present", () => {
    const frames: FigmaFrame[] = Array.from({ length: 3 }, (_, i) => ({
      file: makeFile(`f${i}.png`, "image/png"),
      description: "",
      previewUrl: `blob:http://localhost/${i}`,
    }));
    renderSection(frames);
    expect(screen.getByText(/3 \/ 20 frames/i)).toBeDefined();
  });

  it("calls_onChange_with_empty_array_when_clear_all_clicked", async () => {
    const user = userEvent.setup();
    const frames: FigmaFrame[] = [
      { file: makeFile("a.png", "image/png"), description: "", previewUrl: mockObjectURL },
      { file: makeFile("b.png", "image/png"), description: "", previewUrl: "blob:http://localhost/b" },
    ];
    const onChange = vi.fn();
    render(<FigmaUploadSection frames={frames} onChange={onChange} />);
    await user.click(screen.getByRole("button", { name: /Clear all/i }));
    expect(onChange).toHaveBeenCalledWith([]);
  });

  it("calls_onChange_when_clipboard_paste_fires_with_image_png_item", async () => {
    const onChange = vi.fn();
    render(<FigmaUploadSection frames={[]} onChange={onChange} />);

    // Build a synthetic paste event with a PNG clipboard item
    const blob = new Blob([new Uint8Array(100)], { type: "image/png" });
    const mockItem = {
      type: "image/png",
      getAsFile: () => blob as File,
    };
    fireEvent.paste(window, {
      clipboardData: {
        items: [mockItem],
      },
    });

    await waitFor(() => {
      expect(onChange).toHaveBeenCalled();
    });
  });

  it("calls_onChange_after_url_fetch_returns_image_png_content_type", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const blob = new Blob([new Uint8Array(100)], { type: "image/png" });
    vi.stubGlobal("fetch", vi.fn(() =>
      Promise.resolve({
        ok: true,
        headers: { get: () => "image/png" },
        blob: () => Promise.resolve(blob),
      }),
    ));

    render(<FigmaUploadSection frames={[]} onChange={onChange} />);

    const input = screen.getByPlaceholderText(/https:\/\//i);
    await user.type(input, "https://example.com/screen.png");
    await user.click(screen.getByRole("button", { name: /Add URL/i }));

    await waitFor(() => {
      expect(onChange).toHaveBeenCalled();
    });
  });

  it("shows_error_when_url_fetch_returns_non_image_content_type", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("fetch", vi.fn(() =>
      Promise.resolve({
        ok: true,
        headers: { get: () => "text/html" },
        blob: () => Promise.resolve(new Blob(["<html>"], { type: "text/html" })),
      }),
    ));

    render(<FigmaUploadSection frames={[]} onChange={vi.fn()} />);

    const input = screen.getByPlaceholderText(/https:\/\//i);
    await user.type(input, "https://example.com/page.html");
    await user.click(screen.getByRole("button", { name: /Add URL/i }));

    await waitFor(() => {
      expect(screen.getByText(/URL did not return a PNG or JPEG image/i)).toBeDefined();
    });
  });
});
