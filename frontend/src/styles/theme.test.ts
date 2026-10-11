import { describe, expect, it } from "vitest";
import { colors, theme } from "./theme";
import type { ThemeAnimation, ThemeColors } from "./theme";

describe("colors", () => {
  it("exposes the four base palette entries with exact hex values", () => {
    expect(colors).toEqual({
      navy: "#001f3f",
      white: "#FFFFFF",
      grey: "#AAAAAA",
      black: "#000000",
    });
  });

  it.each(Object.entries(colors))("uses a 6-digit hex literal for %s", (_name, value) => {
    expect(value).toMatch(/^#[0-9a-fA-F]{6}$/);
  });
});

describe("theme.colors", () => {
  it("maps every semantic role to the expected base palette entry", () => {
    expect(theme.colors).toEqual({
      primary: "#001f3f",
      background: "#000000",
      foreground: "#FFFFFF",
      muted: "#AAAAAA",
      surface: "#001f3f",
      border: "#AAAAAA",
    });
  });

  it("resolves every semantic role to a value present in the base palette", () => {
    const palette = Object.values(colors) as string[];

    for (const value of Object.values(theme.colors)) {
      expect(palette).toContain(value);
    }
  });

  it("keeps background and foreground distinct so text stays legible", () => {
    expect(theme.colors.background).not.toBe(theme.colors.foreground);
  });
});

describe("theme.animation", () => {
  it("defines the three animation durations with exact values", () => {
    expect(theme.animation).toEqual({
      typingDuration: "1.4s",
      fadeInDuration: "0.3s",
      tabTransitionDuration: "0.2s",
    });
  });

  it.each(Object.entries(theme.animation))("formats %s as a CSS seconds duration", (_name, value) => {
    expect(value).toMatch(/^\d+(\.\d+)?s$/);
  });
});

describe("theme type aliases", () => {
  it("describe the same keys as the runtime theme sections", () => {
    const colorKeys: Array<keyof ThemeColors> = [
      "primary",
      "background",
      "foreground",
      "muted",
      "surface",
      "border",
    ];
    const animationKeys: Array<keyof ThemeAnimation> = [
      "typingDuration",
      "fadeInDuration",
      "tabTransitionDuration",
    ];

    expect(Object.keys(theme.colors).sort()).toEqual([...colorKeys].sort());
    expect(Object.keys(theme.animation).sort()).toEqual([...animationKeys].sort());
  });
});
