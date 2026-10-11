/**
 * ChatInput — composer textarea, mode menu, voice input, send button.
 *
 * Boundary mocked: the browser Web Speech API (`window.SpeechRecognition`),
 * which jsdom lacks. The real `useSpeechRecognition` hook runs on top of it.
 */
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ChatInput, type ChatInputProps } from "./ChatInput";

type ResultHandler = (event: { results: { length: number; [i: number]: { 0: { transcript: string } } } }) => void;

class FakeRecognition {
  static last: FakeRecognition | null = null;
  continuous = false;
  interimResults = false;
  lang = "";
  onresult: ResultHandler | null = null;
  onerror: ((e: { error: string }) => void) | null = null;
  onend: (() => void) | null = null;
  onstart: (() => void) | null = null;
  start = vi.fn();
  stop = vi.fn();
  abort = vi.fn();
  constructor() {
    FakeRecognition.last = this;
  }
  emit(text: string) {
    this.onresult?.({ results: { length: 1, 0: { 0: { transcript: text } } } });
  }
}

function setup(props: Partial<ChatInputProps> = {}) {
  const onSendMessage = vi.fn();
  const user = userEvent.setup();
  const utils = render(<ChatInput onSendMessage={onSendMessage} isStreaming={false} {...props} />);
  const textbox = screen.getByRole("textbox", { name: "Chat message input" });
  const send = screen.getByRole("button", { name: "Send message" });
  return { user, onSendMessage, textbox, send, ...utils };
}

afterEach(() => {
  vi.useRealTimers();
  delete (window as unknown as Record<string, unknown>).SpeechRecognition;
  FakeRecognition.last = null;
});

describe("ChatInput sending", () => {
  it("test_send_disabled_when_input_empty_or_whitespace", async () => {
    const { user, textbox, send, onSendMessage } = setup();
    expect(send).toBeDisabled();
    await user.type(textbox, "   ");
    expect(send).toBeDisabled();
    await user.type(textbox, "{Enter}");
    expect(onSendMessage).not.toHaveBeenCalled();
  });

  it("test_send_calls_onSendMessage_with_trimmed_text_and_clears_when_button_clicked", async () => {
    const { user, textbox, send, onSendMessage } = setup();
    await user.type(textbox, "  hello world  ");
    expect(send).toBeEnabled();
    await user.click(send);
    expect(onSendMessage).toHaveBeenCalledTimes(1);
    expect(onSendMessage).toHaveBeenCalledWith("hello world");
    expect(textbox).toHaveValue("");
    expect(send).toBeDisabled();
  });

  it("test_send_submits_when_enter_pressed", async () => {
    const { user, textbox, onSendMessage } = setup();
    await user.type(textbox, "hi{Enter}");
    expect(onSendMessage).toHaveBeenCalledWith("hi");
    expect(textbox).toHaveValue("");
  });

  it("test_keydown_inserts_newline_when_shift_enter_pressed", async () => {
    const { user, textbox, onSendMessage } = setup();
    await user.type(textbox, "a{Shift>}{Enter}{/Shift}b");
    expect(onSendMessage).not.toHaveBeenCalled();
    expect(textbox).toHaveValue("a\nb");
  });

  it("test_input_disabled_and_no_send_when_streaming", async () => {
    const onSendMessage = vi.fn();
    const user = userEvent.setup();
    const { rerender } = render(<ChatInput onSendMessage={onSendMessage} isStreaming={false} />);
    const textbox = screen.getByRole("textbox", { name: "Chat message input" });
    await user.type(textbox, "pending");
    rerender(<ChatInput onSendMessage={onSendMessage} isStreaming />);
    expect(textbox).toBeDisabled();
    expect(screen.getByRole("button", { name: "Send message" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Start voice input" })).toBeDisabled();
    expect(textbox).toHaveValue("pending");
    expect(onSendMessage).not.toHaveBeenCalled();
  });

  it("test_footer_shows_keyboard_hint", () => {
    setup();
    expect(screen.getByText("Enter to send · Shift+Enter for new line")).toBeInTheDocument();
  });
});

describe("ChatInput mode menu", () => {
  it("test_menu_lists_modes_and_add_files_when_plus_clicked", async () => {
    const { user } = setup();
    await waitFor(() => expect(screen.queryByRole("button", { name: /Thinking/ })).not.toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Open mode menu" }));
    for (const label of ["Thinking", "Deep Research", "Web Search", "Quizzes", "Add Files"]) {
      expect(screen.getByRole("button", { name: new RegExp(label) })).toBeInTheDocument();
    }
  });

  it("test_menu_closes_when_plus_toggled_again", async () => {
    const { user } = setup();
    const plus = screen.getByRole("button", { name: "Open mode menu" });
    await user.click(plus);
    await user.click(plus);
    await waitFor(() => expect(screen.queryByRole("button", { name: /Quizzes/ })).not.toBeInTheDocument());
  });

  it("test_menu_closes_when_clicking_outside", async () => {
    const { user } = setup();
    await user.click(screen.getByRole("button", { name: "Open mode menu" }));
    await user.click(screen.getByText("Enter to send · Shift+Enter for new line"));
    await waitFor(() => expect(screen.queryByRole("button", { name: /Quizzes/ })).not.toBeInTheDocument());
  });

  it("test_menu_stays_open_when_clicking_inside", async () => {
    const { user } = setup();
    await user.click(screen.getByRole("button", { name: "Open mode menu" }));
    await user.click(screen.getByText("Interactive learning quiz").parentElement!.parentElement!.parentElement!);
    expect(screen.getByRole("button", { name: /Quizzes/ })).toBeInTheDocument();
  });

  it("test_mode_select_shows_badge_focuses_input_and_sends_with_mode", async () => {
    const onSendMessageWithMode = vi.fn();
    const { user, textbox, onSendMessage } = setup({ onSendMessageWithMode });
    await user.click(screen.getByRole("button", { name: "Open mode menu" }));
    await user.click(screen.getByRole("button", { name: /Deep Research/ }));
    await waitFor(() => expect(screen.queryByText("Comprehensive research report")).not.toBeInTheDocument());
    expect(screen.getByText("Deep Research")).toBeInTheDocument();
    expect(screen.getByText("🔬")).toBeInTheDocument();
    expect(textbox).toHaveFocus();
    await user.type(textbox, " topic {Enter}");
    expect(onSendMessageWithMode).toHaveBeenCalledWith("topic", "deep_research");
    expect(onSendMessage).not.toHaveBeenCalled();
    // mode resets after send
    await waitFor(() => expect(screen.queryByRole("button", { name: "Remove mode" })).not.toBeInTheDocument());
  });

  it("test_mode_falls_back_to_onSendMessage_when_no_mode_callback", async () => {
    const { user, textbox, onSendMessage } = setup();
    await user.click(screen.getByRole("button", { name: "Open mode menu" }));
    await user.click(screen.getByRole("button", { name: /Quizzes/ }));
    await user.type(textbox, "q{Enter}");
    expect(onSendMessage).toHaveBeenCalledWith("q");
  });

  it("test_default_mode_uses_onSendMessage_even_when_mode_callback_given", async () => {
    const onSendMessageWithMode = vi.fn();
    const { user, textbox, onSendMessage } = setup({ onSendMessageWithMode });
    await user.type(textbox, "plain{Enter}");
    expect(onSendMessage).toHaveBeenCalledWith("plain");
    expect(onSendMessageWithMode).not.toHaveBeenCalled();
  });

  it("test_remove_mode_clears_badge_when_x_clicked", async () => {
    const onSendMessageWithMode = vi.fn();
    const { user, textbox, onSendMessage } = setup({ onSendMessageWithMode });
    await user.click(screen.getByRole("button", { name: "Open mode menu" }));
    await user.click(screen.getByRole("button", { name: /Thinking/ }));
    await user.click(screen.getByRole("button", { name: "Remove mode" }));
    await user.type(textbox, "x{Enter}");
    expect(onSendMessage).toHaveBeenCalledWith("x");
    expect(onSendMessageWithMode).not.toHaveBeenCalled();
  });

  it("test_add_files_shows_coming_soon_toast_then_hides_after_timeout", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<ChatInput onSendMessage={vi.fn()} isStreaming={false} />);
    await user.click(screen.getByRole("button", { name: "Open mode menu" }));
    await user.click(screen.getByRole("button", { name: /Add Files/ }));
    expect(screen.getByText("📎 File uploads coming soon")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole("button", { name: /Quizzes/ })).not.toBeInTheDocument());
    await act(async () => {
      vi.advanceTimersByTime(2400);
    });
    expect(screen.getByText("📎 File uploads coming soon")).toBeInTheDocument();
    await act(async () => {
      vi.advanceTimersByTime(3000);
    });
    await waitFor(() => expect(screen.queryByText("📎 File uploads coming soon")).not.toBeInTheDocument());
  });
});

describe("ChatInput voice input", () => {
  it("test_mic_disabled_with_unsupported_title_when_api_missing", () => {
    setup();
    const mic = screen.getByRole("button", { name: "Start voice input" });
    expect(mic).toBeDisabled();
    expect(mic).toHaveAttribute("title", "Speech recognition not supported");
  });

  describe("with speech API", () => {
    beforeEach(() => {
      (window as unknown as Record<string, unknown>).SpeechRecognition = FakeRecognition;
    });

    it("test_mic_disabled_when_streaming_even_if_supported", () => {
      render(<ChatInput onSendMessage={vi.fn()} isStreaming />);
      expect(screen.getByRole("button", { name: "Start voice input" })).toBeDisabled();
    });

    it("test_mic_toggles_listening_and_transcript_fills_input", async () => {
      const { user, textbox } = setup();
      const mic = screen.getByRole("button", { name: "Start voice input" });
      expect(mic).toBeEnabled();
      expect(mic).toHaveAttribute("title", "Voice input");
      await user.click(mic);
      expect(FakeRecognition.last!.start).toHaveBeenCalledTimes(1);
      const stop = screen.getByRole("button", { name: "Stop listening" });
      expect(stop).toHaveAttribute("title", "Stop listening");
      expect(textbox).toHaveAttribute("placeholder", "🎙️ Listening...");
      act(() => FakeRecognition.last!.emit("spoken words"));
      expect(textbox).toHaveValue("spoken words");
      await user.click(stop);
      expect(FakeRecognition.last!.stop).toHaveBeenCalledTimes(1);
      expect(screen.getByRole("button", { name: "Start voice input" })).toBeInTheDocument();
      expect(textbox).toHaveAttribute("placeholder", "Message VelocityAI...");
    });
  });
});
