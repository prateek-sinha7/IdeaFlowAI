// QA-KB-110 analysis probe runner. Mirrors frontend/vitest.config.ts (jsdom, globals, the same
// setup file, the same "@" alias) but collects ONLY the probe next to this file, so nothing is
// added to frontend/src and the repo's own include glob is untouched.
//
// Run (one file, offline, no server, no browser):
//   cd <this dir>   # needs a node_modules symlink -> <repo>/frontend/node_modules
//   ./node_modules/.bin/vitest run --config vitest.probe.config.ts                      # today's behaviour
//   QA_KB_110_MUTATE=1 ./node_modules/.bin/vitest run --config vitest.probe.config.ts   # candidate-fix shape
//
// QA_KB_110_MUTATE=1 applies two anchored string replacements to DashboardLayout.tsx IN MEMORY, during
// the vite transform. The file on disk is never written. If either anchor stops matching (the source
// moved on) the transform throws instead of silently testing the unmutated code.
import { defineConfig } from "vitest/config";

const FRONTEND = process.env.QA_KB_110_FRONTEND ??
  "/Users/bilala/Developer/Projects/VELOCITY-AI-worktrees/feat-user-stories-v2/frontend";

const ANCHOR_STATE =
  'const [pendingHomeBrief, setPendingHomeBrief] = useState<string | undefined>(undefined);';
const ANCHOR_SLOT = 'ppt: "ppt.draft", ppt_v2: "ppt.draft" }[reviseBase];';

// 1. the destination reads a one-shot sessionStorage draft when it mounts (read-only initializer, so
//    StrictMode's double invoke cannot lose it) and clears it in an effect once it has been shown;
// 2. handleEditBrief stages the brief there for every destination that has no wizard slot.
const MUTATED_STATE = `const [pendingHomeBrief, setPendingHomeBrief] = useState<string | undefined>(() => {
    if (typeof window === "undefined") return undefined;
    try { return JSON.parse(sessionStorage.getItem("idea.draft") ?? "null")?.brief || undefined; } catch { return undefined; }
  });
  useEffect(() => { sessionStorage.removeItem("idea.draft"); }, []);`;
const MUTATED_SLOT = 'ppt: "ppt.draft", ppt_v2: "ppt.draft" }[reviseBase] ?? "idea.draft";';

export default defineConfig({
  root: __dirname,
  plugins: [
    {
      name: "qa-kb-110-mutation",
      enforce: "pre",
      transform(code, id) {
        if (process.env.QA_KB_110_MUTATE !== "1") return null;
        if (!id.endsWith("/components/layout/DashboardLayout.tsx")) return null;
        for (const a of [ANCHOR_STATE, ANCHOR_SLOT]) {
          if (!code.includes(a)) throw new Error(`QA-KB-110 mutation anchor not found: ${a}`);
        }
        return { code: code.replace(ANCHOR_STATE, MUTATED_STATE).replace(ANCHOR_SLOT, MUTATED_SLOT), map: null };
      },
    },
  ],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: [`${FRONTEND}/vitest.setup.ts`],
    include: ["*.probe.test.tsx"],
    coverage: { enabled: false },
  },
  resolve: { alias: { "@": `${FRONTEND}/src` } },
  server: { fs: { strict: false } },
});
