import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  devIndicators: false,
  output: "standalone",
  rewrites: async () => [
    // Public share route: /s/{token} → FastAPI backend GET /s/{token}.
    // Next.js serves port 3000; FastAPI serves port 8000.  Without this
    // rewrite Next.js catches the path and shows a 404 before FastAPI can
    // respond.  In production both are behind the same reverse proxy, so
    // the rewrite is only needed for local dev (NEXT_PUBLIC_API_URL absent
    // → falls through to the default :8000 backend URL).
    {
      source: "/s/:token",
      destination: `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/s/:token`,
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
