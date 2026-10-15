"use client";

import { useEffect, useState, type ReactNode } from "react";
import { Loader2 } from "lucide-react";
import { getRunSandboxFileBlob, getToken, resolveRunDeliverable } from "@/lib/api";

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
 *  with no file request. */
export function SandboxPdfPreview({ runId, path, selectedRef, fallback }: { runId: string; path: string; selectedRef?: string | null; fallback: ReactNode }) {
  const [state, setState] = useState<{ url: string } | "loading" | "missing">("loading");

  useEffect(() => {
    if (selectedRef === null) return;
    let url: string | null = null;
    let cancelled = false;
    void (async () => {
      setState("loading");
      try {
        const token = getToken() || "";
        const hit = await resolveRunDeliverable(token, runId, path, selectedRef);
        if (cancelled) return;
        if (!hit) { setState("missing"); return; }
        const blob = await getRunSandboxFileBlob(token, runId, hit.path, hit.ref ?? selectedRef);
        if (cancelled) return;
        url = URL.createObjectURL(new Blob([blob], { type: "application/pdf" }));
        setState({ url });
      } catch { if (!cancelled) setState("missing"); }
    })();
    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [runId, path, selectedRef]);

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
