import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

/**
 * ESLint flat config.
 *
 * We extend the project's existing Next.js presets unchanged and ADD a
 * custom `no-restricted-syntax` rule banning hardcoded localhost / 127.0.0.1
 * URLs inside `fetch(...)` and `axios.*(...)` arguments.
 *
 * Why this rule:
 *   The project standard is `ENV.API_URL` (defined in `src/lib/env.ts`).
 *   In production builds, hardcoded `http://localhost:8000` strings ship to
 *   the browser and break every deployed environment. Multiple regressions
 *   have shipped this way; the most recent (May 2026) affected
 *   `PPTPreview.tsx` and `FilesTab.tsx`.
 *
 * Why `no-restricted-syntax` instead of a custom plugin:
 *   The project doesn't currently load any custom ESLint plugins. AST
 *   selector strings are expressive enough for this check and add zero
 *   dependencies.
 *
 * Why two selectors instead of one:
 *   AST selectors don't have a clean way to union "fetch call" with
 *   "axios call" while also matching the argument literal. Two rules with
 *   distinct messages also produce better error output.
 *
 * Why we do NOT match template literals:
 *   `` `${ENV.API_URL}/api/...` `` is the correct idiom. Banning all
 *   templates that mention localhost would catch the env.ts fallback,
 *   which is the intended single source of truth.
 *
 * Why we do NOT match generic Literal nodes (without the call wrapper):
 *   `env.ts` and `api.ts` legitimately mention localhost as a dev fallback.
 *   The bug pattern is specifically calling a network function with a
 *   hardcoded URL.
 */
const HARDCODED_URL_RULES = [
  {
    // fetch("http://localhost...") or fetch("http://127.0.0.1...")
    selector:
      "CallExpression[callee.name='fetch'] > Literal[value=/^https?:\\/\\/(localhost|127\\.0\\.0\\.1)/]",
    message:
      "Hardcoded localhost URL in fetch(). Use `ENV.API_URL` from `@/lib/env` (or a template literal built from it). See src/lib/env.ts.",
  },
  {
    // axios("http://localhost..."), axios.get(...), axios.post(...), etc.
    // Matches both `axios(...)` (Identifier callee) and `axios.method(...)`
    // (MemberExpression callee with axios as the object).
    selector:
      "CallExpression[callee.type='Identifier'][callee.name='axios'] > Literal[value=/^https?:\\/\\/(localhost|127\\.0\\.0\\.1)/]",
    message:
      "Hardcoded localhost URL in axios(). Use `ENV.API_URL` from `@/lib/env`.",
  },
  {
    selector:
      "CallExpression[callee.type='MemberExpression'][callee.object.name='axios'] > Literal[value=/^https?:\\/\\/(localhost|127\\.0\\.0\\.1)/]",
    message:
      "Hardcoded localhost URL in axios.* call. Use `ENV.API_URL` from `@/lib/env`.",
  },
];

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Override default ignores of eslint-config-next.
  //
  // NOTE: declaring `globalIgnores` REPLACES eslint-config-next's defaults, so
  // every generated directory has to be listed here explicitly — ESLint itself
  // only ignores `node_modules` and dotfiles out of the box. Being gitignored is
  // not enough; ESLint does not read .gitignore.
  //
  // `coverage/**` was missing, and that made `npm run lint` order-dependent:
  // the v8/istanbul reporters emit their own `block-navigation.js`,
  // `prettify.js` and `sorter.js` (each carrying an `/* eslint-disable */`
  // header), so ESLint reported "Unused eslint-disable directive" against
  // vendored report scaffolding and `--max-warnings 0` turned that into a
  // failure. It only passed in CI because Lint happens to run BEFORE Test;
  // any developer who ran the tests first — or any future reordering of those
  // steps — saw lint fail on files nobody wrote.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    // Generated test/coverage output (gitignored; not source):
    "coverage/**",
    "e2e/.report/**",
    "test-results/**",
  ]),
  // Project-specific rules.
  {
    name: "flowin/no-hardcoded-localhost-urls",
    files: ["src/**/*.{ts,tsx,js,jsx,mjs,cjs}"],
    rules: {
      "no-restricted-syntax": ["error", ...HARDCODED_URL_RULES],
    },
  },
  // `_`-prefixed identifiers are the codebase's existing "deliberately unused"
  // convention (`_token`, `_range`, `_runId`, `_payload`, `_callback`, ...), but
  // the convention was never declared to the rule, so every one of them was
  // reported. Declaring it here is not a relaxation — an unused binding that is
  // NOT `_`-prefixed still fails.
  //
  // Severity is `error`, not `warn`. `npm run lint` is `--max-warnings 0`, so a
  // warning already fails the build — but a WARNING cannot be recorded in
  // `eslint-suppressions.json` (ESLint's ledger tracks errors only). Leaving
  // this at `warn` therefore meant "fails CI, but is untrackable and
  // unattributable". Promoting it to `error` is strictly stronger: the debt
  // becomes per-file/per-count visible in the ledger and prunable as it is
  // burned down, and genuinely new unused code fails immediately.
  {
    name: "flowin/unused-vars-underscore-convention",
    files: ["**/*.{ts,tsx,js,jsx,mjs,cjs}"],
    rules: {
      "@typescript-eslint/no-unused-vars": [
        "error",
        {
          argsIgnorePattern: "^_",
          varsIgnorePattern: "^_",
          caughtErrorsIgnorePattern: "^_",
          destructuredArrayIgnorePattern: "^_",
        },
      ],
    },
  },
  // react-hooks rules are enforced at `error` REPO-WIDE. The pre-existing
  // violations are NOT handled by downgrading these rules (that would stop
  // gating new code); they are held in `eslint-suppressions.json` — ESLint's
  // native bulk-suppression ledger (`eslint --suppress-all`, ESLint >= 9.24).
  //
  // Why a suppressions file rather than the per-directory `warn`/`error`
  // ratchet this comment used to describe: the directory ratchet requires
  // editing this config on every burn-down step and silently permits NEW
  // violations in any directory not yet promoted. The suppressions ledger
  // inverts that — every rule is at full strength everywhere immediately, and
  // only the specific, enumerated, git-tracked pre-existing violations are
  // excused. CI runs `--prune-suppressions`, so a fixed violation cannot be
  // silently re-introduced and a stale entry cannot linger.
  //
  // Burn-down: fix violations, then `npx eslint --prune-suppressions` to shrink
  // the ledger. These rules are the React Compiler's correctness gate
  // (eslint-plugin-react-hooks v7), so clearing them is the precondition for
  // enabling automatic memoization — hence they stay at `error`, never `warn`.
  {
    name: "flowin/react-hooks-overrides",
    files: ["src/**/*.{ts,tsx,js,jsx}"],
    rules: {
      "react-hooks/exhaustive-deps": "error",
      "react-hooks/set-state-in-effect": "error",
      "react-hooks/static-components": "error",
      "react-hooks/preserve-manual-memoization": "error",
    },
  },
]);

export default eslintConfig;
