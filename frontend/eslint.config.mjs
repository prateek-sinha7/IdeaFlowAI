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
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
  ]),
  // Project-specific rules.
  {
    name: "flowin/no-hardcoded-localhost-urls",
    files: ["src/**/*.{ts,tsx,js,jsx,mjs,cjs}"],
    rules: {
      "no-restricted-syntax": ["error", ...HARDCODED_URL_RULES],
    },
  },
  // Downgrade setState-in-effect to warning (pre-existing pattern in codebase).
  {
    name: "flowin/react-hooks-overrides",
    files: ["src/**/*.{ts,tsx,js,jsx}"],
    rules: {
      "react-hooks/exhaustive-deps": "warn",
      "react-hooks/set-state-in-effect": "warn",
      "react-hooks/static-components": "warn",
      "react-hooks/preserve-manual-memoization": "warn",
    },
  },
]);

export default eslintConfig;
