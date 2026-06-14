import { defineConfig } from "vitest/config";
import path from "path";

// Minimal vitest config: jsdom so DOM/Testing-Library tests can run; the
// `@/` path alias mirrors tsconfig so tests import the same way the
// source does.
export default defineConfig({
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    // Vitest owns the src unit tests ONLY. The Playwright E2E suite lives under
    // e2e/ (*.spec.ts using @playwright/test) — scope vitest to src so it never
    // tries to collect those (they'd report as failed "0 test" files).
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
    exclude: ["e2e/**", "node_modules/**", "dist/**", ".next/**"],
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
});
