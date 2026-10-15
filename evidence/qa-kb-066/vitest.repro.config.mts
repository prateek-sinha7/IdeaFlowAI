// Scratch vitest config for the QA-KB-066 analysis proof. Lives in evidence/, NOT in frontend/,
// so no application source, test or config file is touched. It points vitest at the frontend
// root (aliases, setup file, jsdom) but collects ONLY the proof file next to it.
//
// PATCHED=<variant> swaps `@/components/preview/PreviewPanel` for patched/PreviewPanel.<variant>.tsx (a
// copy of the working-tree file with a candidate fix applied) so the SAME proof can be re-run against it:
//   fixed  - one effClarifications beside effRunInput, keyed on the pin        (recommended)
//   sketch - BUGS.md triage sketch: pipelineState?.clarifications -> effPipelineState?.clarifications
//   naive  - viewingVersion?.clarifications ?? clarifications ?? pipelineState?.clarifications (the trap)
//
// Run (needs evidence/qa-kb-066/node_modules -> ../../frontend/node_modules symlink so the bare
// imports resolve; the analysis removes the symlink again afterwards):
//   cd frontend && npx vitest --run --config ../evidence/qa-kb-066/vitest.repro.config.mts
//   cd frontend && PATCHED=fixed npx vitest --run --config ../evidence/qa-kb-066/vitest.repro.config.mts
import { defineConfig } from "vitest/config";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FRONTEND = path.resolve(HERE, "../../frontend");
const SRC = path.join(FRONTEND, "src");

export default defineConfig({
  root: FRONTEND,
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: [path.join(FRONTEND, "vitest.setup.ts")],
    include: [path.join(HERE, "*.repro.test.tsx")],
  },
  resolve: {
    alias: [
      ...(process.env.PATCHED
        ? [{ find: /^@\/components\/preview\/PreviewPanel$/, replacement: path.join(HERE, `patched/PreviewPanel.${process.env.PATCHED}.tsx`) }]
        : []),
      { find: /^@\//, replacement: SRC + "/" },
    ],
  },
});
