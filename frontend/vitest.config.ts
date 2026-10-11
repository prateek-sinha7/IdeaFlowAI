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
    // The full suite runs ~300 jsdom files in parallel under V8 coverage; the
    // 5s default made unrelated heavy tests (Composer, LaunchWizard, Account
    // settings) time out nondeterministically though each passes in ~1s alone.
    testTimeout: 30_000,
    // Vitest owns the src unit tests ONLY. The Playwright E2E suite lives under
    // e2e/ (*.spec.ts using @playwright/test) — scope vitest to src so it never
    // tries to collect those (they'd report as failed "0 test" files).
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
    exclude: ["e2e/**", "node_modules/**", "dist/**", ".next/**"],
    // Coverage configuration: collect coverage for all src files
    coverage: {
      provider: "v8",
      // Reporters: text/text-summary (console), html (browsable), json +
      // json-summary (for tooling and the threshold ratchet), lcov (what
      // SonarCloud consumes for JS/TS via sonar.javascript.lcov.reportPaths,
      // written to coverage/lcov.info).
      //
      // There is deliberately NO "xml" reporter. It is not a valid coverage
      // reporter name here — the list is passed through to istanbul-reports,
      // whose `xml` entry is a Cobertura-adjacent reporter that fails to load
      // its own `xml` module under this toolchain. The symptom was nasty
      // precisely because it is not a test failure: all 1,111 tests passed, the
      // console printed a full green summary, and THEN `npm run test` exited 1
      // while writing the reports. Sonar wants LCOV for JS/TS anyway, so the
      // XML was never needed. (`cobertura` is the correct name if XML is ever
      // genuinely required.)
      reporter: ["text", "text-summary", "html", "json", "json-summary", "lcov"],
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
      //
      // 80% mandatory coverage threshold enforced on all code.
      // This is a hard gate: `npm run test` will fail if coverage drops below 80%.
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
