import type { Config } from "tailwindcss";

/**
 * Tailwind CSS configuration for the AI SaaS Platform.
 *
 * Note: With Tailwind CSS v4, theme customization is primarily done via
 * the @theme directive in CSS (see src/styles/globals.css). This config
 * file serves as a reference for the enterprise-dark palette and extends
 * the theme for any plugins or tooling that read tailwind.config.ts.
 */
const config: Config = {
  content: [
    "./src/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        navy: "#001f3f",
        white: "#FFFFFF",
        grey: "#AAAAAA",
        black: "#000000",
        background: "#000000",
        foreground: "#FFFFFF",
        surface: "#001f3f",
        muted: "#AAAAAA",
        border: "#AAAAAA",
      },
      animation: {
        typing: "typing 1.4s steps(3, end) infinite",
        "fade-in": "fade-in 0.3s ease-out forwards",
        "fade-in-up": "fade-in-up 0.3s ease-out forwards",
      },
      keyframes: {
        typing: {
          "0%": { opacity: "0.2" },
          "20%": { opacity: "1" },
          "100%": { opacity: "0.2" },
        },
        "fade-in": {
          from: { opacity: "0" },
          to: { opacity: "1" },
        },
        "fade-in-up": {
          from: { opacity: "0", transform: "translateY(8px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
      },
    },
  },
  plugins: [],
};

export default config;
