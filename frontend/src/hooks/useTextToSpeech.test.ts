import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { useTextToSpeech } from "./useTextToSpeech";

class FakeUtterance {
  text: string;
  voice: SpeechSynthesisVoice | null = null;
  rate = 0;
  pitch = 0;
  volume = 0;
  onstart: (() => void) | null = null;
  onend: (() => void) | null = null;
  onerror: (() => void) | null = null;
  constructor(text: string) {
    this.text = text;
  }
}

const voice = (name: string, lang: string) =>
  ({ name, lang }) as SpeechSynthesisVoice;

let voices: SpeechSynthesisVoice[];
let spoken: FakeUtterance[];
const synth = {
  cancel: vi.fn(),
  speak: vi.fn((u: FakeUtterance) => {
    spoken.push(u);
  }),
  getVoices: vi.fn(() => voices),
};

function install() {
  Object.defineProperty(window, "speechSynthesis", {
    value: synth,
    configurable: true,
    writable: true,
  });
  vi.stubGlobal("SpeechSynthesisUtterance", FakeUtterance);
}

describe("useTextToSpeech", () => {
  beforeEach(() => {
    voices = [];
    spoken = [];
    vi.clearAllMocks();
    install();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    delete (window as unknown as Record<string, unknown>).speechSynthesis;
  });

  it("reports supported and idle when speechSynthesis exists", () => {
    const { result } = renderHook(() => useTextToSpeech());
    expect(result.current.isSupported).toBe(true);
    expect(result.current.isSpeaking).toBe(false);
  });

  it("reports unsupported and ignores speak/stop when speechSynthesis is absent", () => {
    delete (window as unknown as Record<string, unknown>).speechSynthesis;
    const { result } = renderHook(() => useTextToSpeech());
    expect(result.current.isSupported).toBe(false);
    act(() => {
      result.current.speak("hello");
      result.current.stop();
    });
    expect(synth.speak).not.toHaveBeenCalled();
    expect(synth.cancel).not.toHaveBeenCalled();
  });

  it("does not speak when text is blank", () => {
    const { result } = renderHook(() => useTextToSpeech());
    act(() => result.current.speak("   "));
    expect(synth.speak).not.toHaveBeenCalled();
  });

  it("strips markdown and cancels prior speech before speaking", () => {
    const { result } = renderHook(() => useTextToSpeech());
    act(() =>
      result.current.speak(
        "# Title\n\n**bold** and *em* [link](http://x.io) `code` <b>tag</b><thinking>hidden</thinking>\nnext",
      ),
    );
    expect(synth.cancel).toHaveBeenCalledTimes(1);
    expect(spoken).toHaveLength(1);
    expect(spoken[0].text).toBe("Title. bold and em link  tag next");
    expect([spoken[0].rate, spoken[0].pitch, spoken[0].volume]).toEqual([1, 1, 1]);
  });

  it("leaves utterance voice unset when no voices are available", () => {
    const { result } = renderHook(() => useTextToSpeech());
    act(() => result.current.speak("hi"));
    expect(spoken[0].voice).toBeNull();
  });

  it("prefers a named natural voice over earlier English voices", () => {
    const preferred = voice("Samantha (Enhanced)", "en-US");
    voices = [voice("Other", "en-GB"), preferred];
    const { result } = renderHook(() => useTextToSpeech());
    act(() => result.current.speak("hi"));
    expect(spoken[0].voice).toBe(preferred);
  });

  it("falls back to the first English voice when no preferred name matches", () => {
    const english = voice("Plain", "en-AU");
    voices = [voice("Hola", "es-ES"), english];
    const { result } = renderHook(() => useTextToSpeech());
    act(() => result.current.speak("hi"));
    expect(spoken[0].voice).toBe(english);
  });

  it("falls back to the first voice when none are English", () => {
    const first = voice("Hola", "es-ES");
    voices = [first, voice("Bonjour", "fr-FR")];
    const { result } = renderHook(() => useTextToSpeech());
    act(() => result.current.speak("hi"));
    expect(spoken[0].voice).toBe(first);
  });

  it("tracks isSpeaking through start, end and error events", () => {
    const { result } = renderHook(() => useTextToSpeech());
    act(() => result.current.speak("hi"));
    act(() => spoken[0].onstart?.());
    expect(result.current.isSpeaking).toBe(true);
    act(() => spoken[0].onend?.());
    expect(result.current.isSpeaking).toBe(false);
    act(() => spoken[0].onstart?.());
    act(() => spoken[0].onerror?.());
    expect(result.current.isSpeaking).toBe(false);
  });

  it("stop cancels speech and clears isSpeaking", () => {
    const { result } = renderHook(() => useTextToSpeech());
    act(() => result.current.speak("hi"));
    act(() => spoken[0].onstart?.());
    synth.cancel.mockClear();
    act(() => result.current.stop());
    expect(synth.cancel).toHaveBeenCalledTimes(1);
    expect(result.current.isSpeaking).toBe(false);
  });

  it("cancels speech on unmount", () => {
    const { unmount } = renderHook(() => useTextToSpeech());
    synth.cancel.mockClear();
    unmount();
    expect(synth.cancel).toHaveBeenCalledTimes(1);
  });
});
