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
    // Coverage configuration: collect coverage for all src files
    coverage: {
      provider: "v8",
      // Reporters: text (console), html (browsable), json (for tooling),
      // xml (Cobertura for SonarCloud), lcov (alternative XML format).
      // v8 provider generates all formats from a single run.
      reporter: ["text", "text-summary", "html", "json", "json-summary", "xml", "lcov"],
      // Coverage report output directory (default: coverage/)
      reportsDirectory: "./coverage",
      // `include` is what makes coverage span every source file, not only the
      // ones a test happened to import. It replaces the old `coverage.all: true`
      // flag, which is no longer part of `CoverageOptions` (TS2769) and is
      // ignored at runtime.
      include: ["src/**/*.{ts,tsx}"],
      exclude: [
        "node_modules/",
        "src/**/*.test.{ts,tsx}",
        "src/**/*.spec.{ts,tsx}",
        "src/**/test/",
        "src/test/",
      ],
      // Vitest >=2 nests the percentage gates under `thresholds`; declaring them
      // at the top level of `coverage` is not part of `CoverageOptions` (TS2769) and fails
      // the typecheck (TS2769) while also being silently ignored at runtime.
      thresholds: {
        lines: 80,
        functions: 80,
        branches: 80,
        statements: 80,
      },
    },
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
});
