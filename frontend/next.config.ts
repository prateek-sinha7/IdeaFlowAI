import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  devIndicators: false,
  output: "standalone",
  // Pin the roots to this folder. Without this Next infers the root from the
  // nearest lockfile; a lockfile higher up the tree (the repo root) moves
  // `server.js` to `.next/standalone/frontend/server.js`, which breaks the CI
  // bundle step, the e2e server command, and the Docker CMD.
  outputFileTracingRoot: path.resolve(__dirname),
  turbopack: { root: path.resolve(__dirname) },
  // Build type-checks app code only; tests are gated once by `npm run typecheck`.
  typescript: { tsconfigPath: "tsconfig.build.json" },
  rewrites: async () => [
    // Public share route: /s/{token} → FastAPI backend GET /s/{token}.
    // Next.js serves port 3000; FastAPI serves port 8000.  Without this
    // rewrite Next.js catches the path and shows a 404 before FastAPI can
    // respond.  In production both are behind the same reverse proxy, so
    // the rewrite is only needed for local dev (NEXT_PUBLIC_API_URL absent
    // or empty → falls through to the default :8000 backend URL).
    {
      source: "/s/:token",
      destination: `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/s/:token`,
    },
    // OAuth redirect target for Connectors. The providers redirect the popup to
    // APP_BASE_URL + /api/connectors/oauth/callback, which locally is the Next
    // server on :3000. The backend handles it and answers 303 to the relative
    // /connectors/oauth-complete. Rewrites in the array form run after the
    // filesystem and before dynamic routes, so the [...view] catch-all cannot
    // shadow this path. Query strings are forwarded automatically. Deployed,
    // nginx sends /api/ to the backend before Next sees it, so this is inert.
    {
      source: "/api/connectors/oauth/callback",
      destination: `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/connectors/oauth/callback`,
    },
  ],
  redirects: async () => [
    // Post-close amendment (015-frontend-routing, 2026-08-21): the 3
    // library list screens merged into one path (/library?tab=&category=) —
    // /library is now the real canonical screen, not a stub needing a
    // redirect. These 3 rules keep old bookmarked/shared list URLs working.
    {
      source: "/library/agents",
      destination: "/library",
      permanent: false,
    },
    {
      source: "/library/skills",
      destination: "/library?tab=skills",
      permanent: false,
    },
    {
      source: "/library/hooks",
      destination: "/library?tab=hooks",
      permanent: false,
    },
    {
      source: "/settings",
      destination: "/settings/profile",
      permanent: false,
    },
  ],
};

export default nextConfig;
