// Standalone vitest config for the QA-KB-116 probe. The repo's vitest.config.ts only collects
// src/**; this one points at the probe in evidence/ and reuses the repo's setup file and the
// `@/` alias. No application source or existing test is touched.
//
// Run (one file, offline) from frontend/, after `ln -s ../../../frontend/node_modules
// ../evidence/qa-kb-116/analysis-plugins/node_modules` (remove the link afterwards):
//   ./node_modules/.bin/vitest run --config ../evidence/qa-kb-116/analysis-plugins/vitest.probe.config.ts
import { defineConfig } from "vitest/config";
import path from "path";

const FRONTEND = path.resolve(__dirname, "../../../frontend");

export default defineConfig({
  root: FRONTEND,
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: [path.join(FRONTEND, "vitest.setup.ts")],
    include: ["../evidence/qa-kb-116/analysis-plugins/*.probe.test.{ts,tsx}"],
    reporters: ["verbose"],
  },
  resolve: {
    alias: [{ find: /^@\//, replacement: path.join(FRONTEND, "src") + "/" }],
  },
});
