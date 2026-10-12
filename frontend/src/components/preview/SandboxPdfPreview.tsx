"use client";

import { useEffect, useState, type ReactNode } from "react";
import { Loader2 } from "lucide-react";
import { getRunSandboxFileBlob, getToken } from "@/lib/api";

/** Shows a PDF from the run's workspace in the browser's own PDF viewer.
 *
 *  The file endpoint needs the bearer token, which an iframe cannot send, so the
 *  bytes are fetched first and shown through an object URL. The endpoint serves
 *  binaries as octet-stream; re-typing the blob as application/pdf is what lets
 *  the viewer open it inline. Any failure (no such file yet, 404, network)
 *  renders `fallback` — the preview the run would have shown without a PDF. */
export function SandboxPdfPreview({ runId, path, fallback }: { runId: string; path: string; fallback: ReactNode }) {
  const [state, setState] = useState<{ url: string } | "loading" | "missing">("loading");

  useEffect(() => {
    let url: string | null = null;
    let cancelled = false;
    getRunSandboxFileBlob(getToken() || "", runId, path)
      .then((blob) => {
        if (cancelled) return;
        url = URL.createObjectURL(new Blob([blob], { type: "application/pdf" }));
        setState({ url });
      })
      .catch(() => { if (!cancelled) setState("missing"); });
    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [runId, path]);

  if (state === "missing") return <>{fallback}</>;
  if (state === "loading") {
    return (
      <div className="flex h-full items-center justify-center gap-2 text-sm text-ink-500" data-testid="sandbox-pdf-loading">
        <Loader2 className="h-4 w-4 animate-spin" /> Loading PDF…
      </div>
    );
  }
  return <iframe title={path} src={state.url} className="h-full w-full border-0" data-testid="sandbox-pdf-preview" />;
}
