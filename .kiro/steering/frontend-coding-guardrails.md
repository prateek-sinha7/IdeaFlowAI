---
inclusion: always
---

# Frontend Coding Guardrails — React · Next.js · CSS

Mandatory design and coding rules for frontend work (React 19, Next.js 16 App
Router, TypeScript, Tailwind/CSS). When a request conflicts with a rule here,
flag the conflict and propose a compliant alternative instead of silently
breaking it. These complement `code-security`, `structure`, and `tech`; they do
not override them.

---

## 1. Low-Level Design (LLD) for UI

- **Separate concerns**: presentation (dumb/UI components), state & side effects
  (hooks/context), data access (fetch/query layer), and domain types. A visual
  tweak must not force a data-layer change.
- **Component contracts are explicit.** Every component has a typed props
  interface. Props flow down, events flow up. No reaching into a child's
  internals or relying on hidden globals.
- **Colocation.** Keep a component's markup, styles, tests, and local hooks near
  each other. Group by feature/route, not by file type.
- **Container vs presentational split.** Isolate data-fetching/stateful logic
  from pure rendering so presentational components stay reusable and testable.
- **Custom hooks are the unit of reuse for behavior**; small components are the
  unit of reuse for UI. Extract a hook when logic repeats or a component juggles
  multiple concerns.
- **Make illegal UI states unrepresentable** with discriminated-union types
  (e.g. `loading | error | ready`) instead of scattered boolean flags.

## 2. SOLID Applied to the Frontend

- **S — Single Responsibility.** One component/hook, one job. A component that
  fetches, transforms, and renders three sections should be split.
- **O — Open/Closed.** Extend via composition, `children`, and props (render
  props / slots) rather than editing a component with ever-growing conditional
  branches.
- **L — Liskov Substitution.** A specialized component must honor the base
  component's prop contract so it can be swapped without breaking callers.
- **I — Interface Segregation.** Keep props interfaces small and focused. Don't
  force consumers to pass props they don't use; split "god components".
- **D — Dependency Inversion.** Depend on abstractions: inject data via
  props/context/hooks and pass callbacks in, rather than hardcoding fetch calls
  or concrete services inside presentational components.

## 3. Core Design Principles (DRY · KISS · YAGNI)

- **DRY** — extract a shared component/hook/util once real duplication of
  *meaning* appears. Don't over-abstract superficially similar JSX that will
  diverge.
- **KISS** — reach for the simplest tool first: local `useState` before context,
  context before a global store, a CSS class before a JS animation. Add
  complexity only when the simple option demonstrably fails.
- **YAGNI** — don't build configurable "mega components" or premature abstraction
  layers for requirements that don't exist yet.
- **Single source of truth** — derive state, don't duplicate it. Compute values
  during render instead of syncing copies with effects.

## 4. React Standards

- **Function components + hooks only.** Follow the Rules of Hooks: call hooks at
  the top level, never conditionally or in loops.
- **Keep components pure.** No side effects during render. Side effects live in
  event handlers or `useEffect`; effects must clean up (subscriptions, timers,
  listeners).
- **`useEffect` is a last resort.** Don't use it to transform data for rendering
  (derive inline) or to sync state that could be lifted or computed. Use it only
  for true external synchronization.
- **Stable, meaningful `key`s** for lists — never the array index for dynamic/
  reorderable lists.
- **Lift state to the lowest common ancestor**; colocate state as close to where
  it's used as possible to limit re-render scope.
- **Memoize deliberately, not reflexively.** Reach for `useMemo`/`useCallback`/
  `React.memo` to fix a measured re-render or expensive-compute problem, not by
  default. Measure with the Profiler first.
- **Controlled inputs** with validation; avoid unnecessary state duplication.
- **Error boundaries** around risky subtrees; `Suspense` for async UI.
- **Accessibility is not optional** (see §7).

## 5. Next.js (App Router) Standards

- **Server-first.** Default to Server Components. Add `'use client'` only where
  you need interactivity, browser APIs, state, or effects — and push it as far
  down the tree (leaf components) as possible to keep bundles small.
- **Fetch data on the server** in Server Components / route handlers; keep secrets
  and heavy logic server-side. Never expose API keys or server-only env vars to
  the client (only `NEXT_PUBLIC_*` is client-safe).
- **Choose rendering intentionally**: static by default, dynamic only where
  required; use streaming and `Suspense` boundaries for perceived performance.
- **Mutations via Server Actions / route handlers** with input validation and
  auth checks server-side — never trust the client. Revalidate caches explicitly
  after writes.
- **Use `next/image`, `next/font`, and `next/link`** for images, fonts, and
  navigation. Code-split heavy client-only widgets with `next/dynamic`.
- **Respect caching semantics** deliberately (fetch cache, `revalidate`, tags);
  don't disable caching blindly.
- **Follow the project layout** (`src/app` routes, `components`, `hooks`, `lib`,
  `context`, `types`). Standalone output; keep config secure (no debug/verbose
  errors in production, no permissive CORS).

## 6. Styling / CSS (Tailwind) Standards

- **Tailwind utility-first**, consistent with the enterprise-dark theme. Use
  design tokens / theme values — no magic hex colors or arbitrary pixel values
  scattered inline.
- **Extract repeated utility clusters** into a component (preferred) or a small
  shared class; don't copy long class strings across files.
- **Mobile-first, responsive** with Tailwind breakpoints; test at multiple
  widths. Layout with Flexbox/Grid, not floats or absolute positioning hacks.
- **Theme through configuration** (spacing, color, typography scales) rather than
  one-off overrides, so styling stays consistent and changeable in one place.
- **Prefer CSS/Tailwind for transitions**; reach for the JS animation library
  only for orchestrated/interactive motion. Respect `prefers-reduced-motion`.
- **No layout shift**: reserve space for images/async content (CLS).
- **Keep specificity low and predictable**; avoid deep selector nesting and
  `!important`.

## 7. Accessibility (a11y)

- **Semantic HTML first** (`button`, `nav`, `main`, `label`) before ARIA. Use
  ARIA only to fill gaps, and use it correctly.
- **Keyboard operable**: every interactive element is focusable, reachable in a
  logical tab order, and has a visible focus state. No keyboard traps.
- **Labels & alt text**: all form controls have associated labels; images have
  meaningful `alt` (empty `alt` for decorative).
- **Sufficient color contrast** for text and UI; never rely on color alone to
  convey meaning.
- Note: full WCAG conformance requires manual testing with assistive tech and
  expert review — automated checks are necessary but not sufficient.

## 8. Performance

- **Ship less JavaScript**: server components, code-splitting, lazy-loading, and
  tree-shakeable imports. Watch bundle size.
- **Prevent unnecessary re-renders**: stable references, correct `key`s,
  appropriate memoization, and narrow state scope.
- **Optimize assets**: `next/image`, modern formats, correct sizing, font
  subsetting via `next/font`.
- **Virtualize long lists**; paginate or stream large data sets.
- **Measure before optimizing** — use the React Profiler and web-vitals; optimize
  the proven bottleneck, not guesses.

## 9. TypeScript & Testing

- **Strict typing.** No implicit/undocumented `any`; type props, hook returns,
  and API responses. Prefer discriminated unions and `type`/`interface` over
  loose object shapes. Validate external/API data at the boundary.
- **Test user-visible behavior** with Vitest + React Testing Library — query by
  role/label/text, not implementation details. Add property tests (`fast-check`)
  for pure logic.
- **E2E with Playwright** for critical flows (use the `mocked` project by
  default). Run tests single-pass (`npm run test`, i.e. `vitest --run`) — never
  watch mode in automation.
- After changes, run `npm run build`, `npm run lint`, and tests before declaring
  done. Never launch `next dev`/`next start` through automation — recommend the
  user run those manually.

## 10. State Management

- **Pick the smallest scope that works**: local `useState` → lifted state →
  context → a dedicated store. Don't reach for global state to solve a local
  problem.
- **Separate server state from client state.** Data fetched from an API is
  *server state* — manage it with a data-fetching/caching layer (React Query /
  SWR, or Next.js server fetching + revalidation), not by dumping it into a
  global store or context and hand-syncing it.
- **Context is for low-frequency global concerns** (auth, theme, locale,
  settings) — not high-frequency or large state. Split providers by concern to
  avoid "provider hell" and to keep re-renders narrow; a context update
  re-renders all consumers.
- **Derive, don't duplicate.** Compute values during render instead of storing
  copies and syncing them with effects. One source of truth per piece of state.

## 11. Data Fetching & Async UI

- **Prefer server fetching** (Server Components / route handlers) for initial
  data; use a client cache library only for interactive/client-owned data.
- **Avoid request waterfalls.** Fetch in parallel, colocate queries with the
  components that need them, and prefetch predictable navigations.
- **Always model the three states** — loading, error, empty/success — with real
  UI for each. Use `Suspense` + skeletons and retry/backoff for transient
  failures. Never leave a dead spinner on error.
- **Cache and revalidate intentionally**: choose static + ISR (`revalidate`) for
  high-traffic content, dynamic only when genuinely time-sensitive, and use
  stale-while-revalidate. After mutations, invalidate the right tags/paths — and
  purge the CDN if on-demand revalidation must propagate.

## 12. Forms & Validation

- **Controlled inputs with clear validation** and inline, accessible error
  messages tied to fields (`aria-describedby`).
- **Validate on the client for UX, re-validate on the server for trust.** Never
  rely on client validation for security — Server Actions/handlers must validate
  and authorize independently.
- **Manage submission state** (pending, success, error), disable double-submit,
  and preserve user input on failure. Prefer a schema (e.g. Zod) shared between
  form and server boundary where practical.

## 13. Frontend Security

- **Never trust or inject raw HTML.** Avoid `dangerouslySetInnerHTML`; if
  unavoidable, sanitize with a vetted library first. React escapes by default —
  don't defeat it. This is the primary XSS defense.
- **No secrets in the client bundle.** Only `NEXT_PUBLIC_*` env vars reach the
  browser; keep API keys and server-only config server-side. Assume anything
  shipped to the client is public.
- **Set security headers** (CSP, `X-Content-Type-Options`, frame options,
  referrer policy) via Next.js config/middleware to reduce XSS, clickjacking,
  and MIME-sniffing risk.
- **Validate/encode untrusted data** before rendering into `href`, `src`, or
  style. Guard against open redirects; avoid `javascript:` URLs.
- **Auth checks belong on the server.** Client-side route guards are UX only, not
  a security boundary; middleware/handlers enforce the real check.

## 14. SEO & Metadata

- **Use the App Router Metadata API** (static `metadata` or `generateMetadata`)
  for titles, descriptions, canonical URLs, and Open Graph/Twitter tags — set per
  route to match intent.
- **Server-render indexable content.** Don't hide primary content behind
  client-only rendering; match the rendering mode (static/ISR/dynamic) to the
  route's traffic and freshness needs.
- **Provide structured data (JSON-LD), a sitemap, and robots rules** via the
  file conventions. Keep Core Web Vitals (LCP, CLS, INP) healthy — they are
  ranking and UX signals.

## 15. Conventions & Anti-Patterns

- **Consistent naming**: `PascalCase` component files/exports, `useX` for hooks,
  `camelCase` for functions/vars. Colocate component + styles + test + local
  hooks; group by feature/route.
- **Avoid known anti-patterns**: storing derived values in state, using effects
  for synchronous/derivable work, using array index as `key` for dynamic lists,
  wrapping everything in `useCallback`/`useMemo` reflexively, prop-drilling deep
  trees, and silencing dependency-array warnings.
- **Keep components focused and files small.** Extract when a component grows
  multiple concerns; don't build configurable mega-components (YAGNI).

---

## References

Content below was researched from public sources and rephrased for compliance
with licensing restrictions.

- [React & Next.js modern best practices (2025)](https://strapi.io/blog/react-and-nextjs-in-2025-modern-best-practices)
- [Next.js production checklist](https://nextjs.org/docs/app/building-your-application/deploying/production-checklist)
- [The server-first era of React with Next.js](https://gianna-song.medium.com/the-server-first-era-of-react-in-2025-a-deep-dive-into-rsc-with-next-js-ab5e93787ebb)
- [Vercel Labs — React best practices skill](https://github.com/vercel-labs/agent-skills/blob/main/skills/react-best-practices/SKILL.md)
- [React performance optimization (2025)](https://www.growin.com/blog/react-performance-optimization-2025/)
- [SOLID, Clean Code, DRY, KISS, YAGNI with React/TypeScript](https://www.gperrucci.com/blog/engineering/solid-clean-yagni-kiss)
- [DRY, KISS, YAGNI for cleaner code](https://minifyn.com/blog/mastering-core-javascript-design-principles-dry-kiss-and-yagni-explained)
- [Frontend state management — data flow & scalability](https://techgenyz.com/frontend-state-management-explained-react-redux/)
- [20 React anti-patterns that quietly break your app](https://substack.com/home/post/p-204741223)
- [Next.js — Incremental Static Regeneration (ISR)](https://nextjs.org/docs/app/building-your-application/data-fetching/incremental-static-regeneration)
- [Using Next.js security headers to strengthen app security](https://blog.logrocket.com/using-next-js-security-headers/)
- [Mitigating XSS vulnerabilities (Salesforce Trailhead)](https://trailhead.salesforce.com/content/learn/modules/secure-clientside-development/mitigate-crosssite-scripting)
- [Next.js SEO guide — metadata & optimization](https://www.digitalapplied.com/blog/nextjs-seo-guide)