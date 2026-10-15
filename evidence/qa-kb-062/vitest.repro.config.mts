// Scratch vitest config for the QA-KB-062 analysis proof. Lives in evidence/, NOT in frontend/,
// so no application source, test or config file is touched. It points vitest at the frontend
// root (aliases, setup file, jsdom) but collects ONLY the proof file next to it.
//
// Run (needs evidence/qa-kb-062/node_modules -> ../../frontend/node_modules symlink so the bare
// imports resolve; the analysis removes the symlink again afterwards):
//   cd frontend && npx vitest --run --config ../evidence/qa-kb-062/vitest.repro.config.mts
import { defineConfig } from "vitest/config";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FRONTEND = path.resolve(HERE, "../../frontend");

export default defineConfig({
  root: FRONTEND,
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: [path.join(FRONTEND, "vitest.setup.ts")],
    include: [path.join(HERE, "*.repro.test.tsx")],
  },
  resolve: {
    alias: { "@": path.join(FRONTEND, "src") },
  },
});
