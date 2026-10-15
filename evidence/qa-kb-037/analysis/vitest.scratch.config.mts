import { defineConfig } from "vitest/config";
const FE = "/Users/bilala/Developer/Projects/VELOCITY-AI-worktrees/feat-user-stories-v2/frontend";
export default defineConfig({
  root: "/private/tmp/claude-502/-Users-bilala-Developer-Projects-VELOCITY-AI-worktrees-feat-user-stories-v2/2d1a1575-310a-48fd-8155-2763a084604d/scratchpad/repro37",
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: [FE + "/vitest.setup.ts"],
    include: ["*.test.tsx", "reg_*/*.test.tsx"],
  },
  resolve: { alias: { "@": FE + "/src" } },
});
