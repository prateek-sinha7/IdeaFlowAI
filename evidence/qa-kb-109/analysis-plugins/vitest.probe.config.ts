// Standalone vitest config for the QA-KB-109 probe. The repo's vitest.config.ts only collects
// src/**; this one points at the probe in evidence/ and reuses the repo's setup file and the
// `@/` alias. No application source or existing test is touched.
//
// Run (one file, offline) from frontend/, after `ln -s ../../../frontend/node_modules
// ../evidence/qa-kb-109/analysis-plugins/node_modules` (remove the link afterwards):
//   ./node_modules/.bin/vitest run --config ../evidence/qa-kb-109/analysis-plugins/vitest.probe.config.ts
//   PROBE_TARGET=fixed ./node_modules/.bin/vitest run --config ...            (probe vs the reference fix)
//   PROBE_TARGET=fixed PROBE_SUITE=existing ./node_modules/.bin/vitest run --config ...  (repo's admin tests vs the reference fix)
import { defineConfig } from "vitest/config";
import path from "path";

const FRONTEND = path.resolve(__dirname, "../../../frontend");

// PROBE_TARGET=fixed  swaps the admin page for page.reference-fix.tsx (mutation probe, app source untouched).
// PROBE_SUITE=existing runs the repo's own admin tests (src/app/admin/*.test.tsx) instead of the probe.
const FIXED = process.env.PROBE_TARGET === "fixed";
const EXISTING = process.env.PROBE_SUITE === "existing";
const PATCHED = path.join(__dirname, "page.reference-fix.tsx");

export default defineConfig({
  root: FRONTEND,
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: [path.join(FRONTEND, "vitest.setup.ts")],
    include: EXISTING ? ["src/app/admin/*.test.tsx"] : ["../evidence/qa-kb-109/analysis-plugins/*.probe.test.tsx"],
    reporters: ["verbose"],
  },
  resolve: {
    alias: [
      ...(FIXED
        ? [
            { find: /^@\/app\/admin\/page$/, replacement: PATCHED },
            { find: /^\.\/page$/, replacement: PATCHED },
          ]
        : []),
      { find: /^@\//, replacement: path.join(FRONTEND, "src") + "/" },
    ],
  },
});
