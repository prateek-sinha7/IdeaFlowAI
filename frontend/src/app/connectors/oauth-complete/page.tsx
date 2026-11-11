import { Suspense } from "react";
import type { Metadata } from "next";

import { OAuthCompleteClient } from "./OAuthCompleteClient";

/**
 * Landing page for the OAuth callback redirect (popup or tab).
 *
 * Public, static and API-free: the result in the query string is only a hint,
 * and the Connectors page always re-reads its state from GET /api/connectors.
 * It must not be indexed.
 */
export const metadata: Metadata = {
  title: "Connecting your account",
  robots: { index: false, follow: false },
};

export default function OAuthCompletePage() {
  // useSearchParams in a prerendered route needs a Suspense boundary, otherwise the build fails.
  return (
    <Suspense fallback={null}>
      <OAuthCompleteClient />
    </Suspense>
  );
}
