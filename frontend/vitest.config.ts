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
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
});
