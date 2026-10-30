"use client";

import { useEffect, useState, type ReactNode } from "react";
import { Loader2 } from "lucide-react";
import { getRunSandboxFileBlob, getToken, resolveRunDeliverable } from "@/lib/api";
import { pdfCacheKey, peekCachedPdfUrl, readCachedPdfUrl, storeCachedPdfUrl } from "@/lib/pdfObjectUrlCache";

/** Shows a PDF from the run's workspace in the browser's own PDF viewer.
 *
 *  The file endpoint needs the bearer token, which an iframe cannot send, so the
 *  bytes are fetched first and shown through an object URL. The endpoint serves
 *  binaries as octet-stream; re-typing the blob as application/pdf is what lets
 *  the viewer open it inline. Any failure (no such file yet, 404, network)
 *  renders `fallback` — the preview the run would have shown without a PDF.
 *
 *  ISS-973 — `selectedRef` is the version tag the shown member's PDF lives at:
 *  a revision family shares ONE sandbox whose live tree (undefined) is the
 *  NEWEST member's. Null = an older member with no tag, which has no snapshot to
 *  read, so `fallback` renders rather than another member's PDF.
 *
 *  ISS-1073 — `path` is the DECLARED name, which a tag may not hold at the root
 *  (the root copy is gitignored; a tag carries `.chain/<name>` or no PDF at all).
 *  So it resolves against the listing AT the ref first, like every other reader
 *  of the deliverable, and reads the resolved path; nothing listed → `fallback`
 *  with no file request.
 *
 *  `cacheable` — RCA item 9: a finished run's PDF never changes, yet every Preview
 *  tab re-entry remounted this component and re-downloaded it. When the run is
 *  finished, a cached object URL is reused with no request, and a fetched one is
 *  kept in the cache (not revoked on unmount). The cache is scoped to the
 *  signed-in account and holds nothing for a token without an account id; see
 *  `@/lib/pdfObjectUrlCache`. Omitted/false keeps the fetch-per-mount behaviour. */
export function SandboxPdfPreview({
  runId,
  path,
  selectedRef,
  fallback,
  cacheable = false,
}: {
  runId: string;
  path: string;
  selectedRef?: string | null;
  fallback: ReactNode;
  cacheable?: boolean;
}) {
  const [state, setState] = useState<{ url: string } | "loading" | "missing">(() => {
    if (!cacheable || selectedRef === null) return "loading";
    const key = pdfCacheKey(runId, path, selectedRef);
    const cached = key ? peekCachedPdfUrl(key) : undefined;
    return cached ? { url: cached } : "loading";
  });

  useEffect(() => {
    if (selectedRef === null) return;
    let url: string | null = null;
    let stored = false;
    let cancelled = false;
    void (async () => {
      const token = getToken() || "";
      // No key (not cacheable, or no account id to scope an entry to) means nothing is read or kept.
      const key = cacheable ? pdfCacheKey(runId, path, selectedRef) : null;
      const cached = key ? readCachedPdfUrl(key) : undefined;
      if (cached) {
        setState((prev) => (typeof prev === "object" && prev.url === cached ? prev : { url: cached }));
        return;
      }
      setState("loading");
      try {
        const hit = await resolveRunDeliverable(token, runId, path, selectedRef);
        if (cancelled) return;
        if (!hit) { setState("missing"); return; }
        const blob = await getRunSandboxFileBlob(token, runId, hit.path, hit.ref ?? selectedRef);
        if (cancelled) return;
        url = URL.createObjectURL(new Blob([blob], { type: "application/pdf" }));
        // Refused when the account signed out mid-download; the URL is then revoked on unmount like an uncached one.
        if (key) stored = storeCachedPdfUrl(key, url);
        setState({ url });
      } catch { if (!cancelled) setState("missing"); }
    })();
    return () => {
      cancelled = true;
      if (url && !stored) URL.revokeObjectURL(url);
    };
  }, [runId, path, selectedRef, cacheable]);

  if (state === "missing" || selectedRef === null) return <>{fallback}</>;
  if (state === "loading") {
    return (
      <div className="flex h-full items-center justify-center gap-2 text-sm text-ink-500" data-testid="sandbox-pdf-loading">
        <Loader2 className="h-4 w-4 animate-spin" /> Loading PDF…
      </div>
    );
  }
  return <iframe title={path} src={state.url} className="h-full w-full border-0" data-testid="sandbox-pdf-preview" />;
}
