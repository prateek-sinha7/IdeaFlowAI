import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  devIndicators: false,
  output: "standalone",
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
