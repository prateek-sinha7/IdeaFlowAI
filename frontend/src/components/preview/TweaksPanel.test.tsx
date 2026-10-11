import { afterEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { DEFAULT_TOKENS, FONT_OPTIONS, TweaksPanel, type TokenMap } from "./TweaksPanel";

function makeProps(overrides: Partial<React.ComponentProps<typeof TweaksPanel>> = {}) {
  return {
    tokens: { ...DEFAULT_TOKENS } as TokenMap,
    editHtml: "<html><body>base</body></html>",
    onTokenChange: vi.fn(),
    onApplyPreset: vi.fn(),
    onApplyHtml: vi.fn(),
    onReset: vi.fn(),
    onClose: vi.fn(),
    ...overrides,
  };
}

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("TweaksPanel — header actions", () => {
  it("calls onClose when the close button is clicked", async () => {
    const user = userEvent.setup();
    const props = makeProps();
    render(<TweaksPanel {...props} />);

    await user.click(screen.getByRole("button", { name: "Close tweaks" }));

    expect(props.onClose).toHaveBeenCalledTimes(1);
  });

  it("calls onReset when the reset button is clicked", async () => {
    const user = userEvent.setup();
    const props = makeProps();
    render(<TweaksPanel {...props} />);

    await user.click(screen.getByRole("button", { name: "Reset all tweaks" }));

    expect(props.onReset).toHaveBeenCalledTimes(1);
  });

  it("restores the HTML editor to the parent's editHtml when reset is clicked", async () => {
    const user = userEvent.setup();
    render(<TweaksPanel {...makeProps()} />);
    await user.click(screen.getByRole("button", { name: "Edit HTML" }));
    const textarea = screen.getByLabelText("Edit HTML directly");

    await user.type(textarea, "EXTRA");
    expect(textarea).toHaveValue("<html><body>base</body></html>EXTRA");

    await user.click(screen.getByRole("button", { name: "Reset all tweaks" }));

    expect(textarea).toHaveValue("<html><body>base</body></html>");
    expect(screen.getByRole("button", { name: "Apply changes" })).toBeDisabled();
  });
});

describe("TweaksPanel — theme presets", () => {
  it.each([
    ["Light", { "--bg": "#ffffff", "--fg": "#0f172a", "--accent": "#2563eb" }],
    ["Dark", { "--bg": "#0f172a", "--fg": "#f1f5f9", "--accent": "#3b82f6" }],
    ["Sepia", { "--bg": "#fdf6e3", "--fg": "#3c3836", "--accent": "#b57614" }],
    ["Contrast", { "--bg": "#000000", "--fg": "#ffffff", "--accent": "#facc15" }],
  ])("applies the %s preset tokens", async (label, expected) => {
    const user = userEvent.setup();
    const props = makeProps();
    render(<TweaksPanel {...props} />);

    await user.click(screen.getByRole("button", { name: label }));

    expect(props.onApplyPreset).toHaveBeenCalledTimes(1);
    expect(props.onApplyPreset).toHaveBeenCalledWith(expect.objectContaining(expected));
  });

  it("hides and re-shows the preset buttons when the Theme section header is toggled", async () => {
    const user = userEvent.setup();
    render(<TweaksPanel {...makeProps()} />);

    await user.click(screen.getByRole("button", { name: "Theme" }));
    expect(screen.queryByRole("button", { name: "Dark" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Theme" }));
    expect(screen.getByRole("button", { name: "Dark" })).toBeInTheDocument();
  });
});

describe("TweaksPanel — color tokens", () => {
  it("shows each token's current hex value in a labelled input", () => {
    render(<TweaksPanel {...makeProps()} />);

    expect(screen.getByLabelText("Background hex value")).toHaveValue("#ffffff");
    expect(screen.getByLabelText("Text hex value")).toHaveValue("#0f172a");
    expect(screen.getByLabelText("Accent / Primary hex value")).toHaveValue("#2563eb");
    expect(screen.getByLabelText("Muted text hex value")).toHaveValue("#64748b");
  });

  it("reports a valid typed hex edit through onTokenChange", async () => {
    const user = userEvent.setup();
    const props = makeProps();
    render(<TweaksPanel {...props} />);

    await user.type(screen.getByLabelText("Background hex value"), "a");

    expect(props.onTokenChange).toHaveBeenCalledWith("--bg", "#ffffffa");
  });

  it("rejects a non-hex character typed into the hex input", async () => {
    const user = userEvent.setup();
    const props = makeProps();
    render(<TweaksPanel {...props} />);

    await user.type(screen.getByLabelText("Background hex value"), "z");

    expect(props.onTokenChange).not.toHaveBeenCalled();
  });

  it("rejects a hex value longer than 8 digits", async () => {
    const user = userEvent.setup();
    const props = makeProps({ tokens: { ...DEFAULT_TOKENS, "--bg": "#ffffffff" } });
    render(<TweaksPanel {...props} />);

    await user.type(screen.getByLabelText("Background hex value"), "a");

    expect(props.onTokenChange).not.toHaveBeenCalled();
  });

  it("shows a read-only dash for a token that is not a hex color", () => {
    render(<TweaksPanel {...makeProps({ tokens: { ...DEFAULT_TOKENS, "--bg": "transparent" } })} />);

    const input = screen.getByLabelText("Background hex value");
    expect(input).toHaveValue("—");
    expect(input).toHaveAttribute("readonly");
  });

  it("opens the native color picker when the swatch is clicked", async () => {
    const user = userEvent.setup();
    const clickSpy = vi.spyOn(HTMLInputElement.prototype, "click");
    render(<TweaksPanel {...makeProps()} />);

    await user.click(screen.getByRole("button", { name: "Change Background" }));

    // jsdom has no color picker UI; the boundary is the hidden input's click().
    expect(clickSpy).toHaveBeenCalledTimes(1);
    expect(clickSpy.mock.contexts[0]).toHaveProperty("type", "color");
  });

  it("reports a value chosen in the native color picker through onTokenChange", () => {
    const props = makeProps();
    const { container } = render(<TweaksPanel {...props} />);
    const pickers = container.querySelectorAll('input[type="color"]');

    // fireEvent: user-event cannot drive a native <input type="color"> dialog.
    fireEvent.change(pickers[0], { target: { value: "#123456" } });

    expect(props.onTokenChange).toHaveBeenCalledWith("--bg", "#123456");
  });
});

describe("TweaksPanel — typography", () => {
  it("lists every font option", () => {
    render(<TweaksPanel {...makeProps()} />);

    for (const opt of FONT_OPTIONS) {
      expect(screen.getByRole("button", { name: opt.label })).toBeInTheDocument();
    }
  });

  it("reports the selected font family through onTokenChange", async () => {
    const user = userEvent.setup();
    const props = makeProps();
    render(<TweaksPanel {...props} />);

    await user.click(screen.getByRole("button", { name: "Inter" }));

    expect(props.onTokenChange).toHaveBeenCalledWith("--font-sans", "'Inter', ui-sans-serif, sans-serif");
  });
});

describe("TweaksPanel — Edit HTML", () => {
  it("keeps the HTML editor collapsed until its section header is opened", async () => {
    const user = userEvent.setup();
    render(<TweaksPanel {...makeProps()} />);

    expect(screen.queryByLabelText("Edit HTML directly")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Edit HTML" }));

    expect(screen.getByLabelText("Edit HTML directly")).toHaveValue("<html><body>base</body></html>");
  });

  it("keeps Apply disabled until the HTML is edited", async () => {
    const user = userEvent.setup();
    render(<TweaksPanel {...makeProps()} />);
    await user.click(screen.getByRole("button", { name: "Edit HTML" }));

    expect(screen.getByRole("button", { name: "Apply changes" })).toBeDisabled();

    await user.type(screen.getByLabelText("Edit HTML directly"), "x");

    expect(screen.getByRole("button", { name: "Apply changes" })).toBeEnabled();
  });

  it("applies the edited HTML, shows 'Applied', then reverts after two seconds", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const props = makeProps();
    render(<TweaksPanel {...props} />);
    await user.click(screen.getByRole("button", { name: "Edit HTML" }));
    await user.type(screen.getByLabelText("Edit HTML directly"), "<!--e-->");

    await user.click(screen.getByRole("button", { name: "Apply changes" }));

    expect(props.onApplyHtml).toHaveBeenCalledWith("<html><body>base</body></html><!--e-->");
    expect(screen.getByRole("button", { name: "Applied" })).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(2000);
    });

    expect(screen.getByRole("button", { name: "Apply changes" })).toBeDisabled();
  });

  it("restarts the 'Applied' timer when Apply is clicked again before it expires", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const props = makeProps();
    render(<TweaksPanel {...props} />);
    await user.click(screen.getByRole("button", { name: "Edit HTML" }));
    await user.type(screen.getByLabelText("Edit HTML directly"), "a");
    await user.click(screen.getByRole("button", { name: "Apply changes" }));

    act(() => {
      vi.advanceTimersByTime(1500);
    });
    await user.click(screen.getByRole("button", { name: "Applied" }));
    act(() => {
      vi.advanceTimersByTime(1500);
    });

    // 3000ms since the first click, but only 1500ms since the second.
    expect(screen.getByRole("button", { name: "Applied" })).toBeInTheDocument();
    expect(props.onApplyHtml).toHaveBeenCalledTimes(2);

    act(() => {
      vi.advanceTimersByTime(500);
    });
    expect(screen.getByRole("button", { name: "Apply changes" })).toBeInTheDocument();
  });

  it("clears the pending 'Applied' timer on unmount", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const { unmount } = render(<TweaksPanel {...makeProps()} />);
    await user.click(screen.getByRole("button", { name: "Edit HTML" }));
    await user.type(screen.getByLabelText("Edit HTML directly"), "a");
    await user.click(screen.getByRole("button", { name: "Apply changes" }));

    unmount();

    expect(vi.getTimerCount()).toBe(0);
  });

  it("replaces the editor text and clears the dirty state when the parent's editHtml changes", async () => {
    const user = userEvent.setup();
    const props = makeProps();
    const { rerender } = render(<TweaksPanel {...props} />);
    await user.click(screen.getByRole("button", { name: "Edit HTML" }));
    await user.type(screen.getByLabelText("Edit HTML directly"), "dirty");
    expect(screen.getByRole("button", { name: "Apply changes" })).toBeEnabled();

    rerender(<TweaksPanel {...props} editHtml="<html>new run</html>" />);

    expect(screen.getByLabelText("Edit HTML directly")).toHaveValue("<html>new run</html>");
    expect(screen.getByRole("button", { name: "Apply changes" })).toBeDisabled();
  });
});

describe("TweaksPanel — unsafe HTML is inert in the editor", () => {
  it("shows a script payload as text in the textarea without creating a script element", async () => {
    const payload = '<script>window.__pwned=true</script><a href="javascript:alert(1)">x</a>';
    const user = userEvent.setup();
    const { container } = render(<TweaksPanel {...makeProps({ editHtml: payload })} />);

    await user.click(screen.getByRole("button", { name: "Edit HTML" }));

    expect(screen.getByLabelText("Edit HTML directly")).toHaveValue(payload);
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector('a[href^="javascript:" i]')).toBeNull();
  });
});
