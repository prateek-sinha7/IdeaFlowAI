"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { routes } from "@/lib/routes";
import { AppBuilderPreview, type ParsedFile } from "@/components/preview/AppBuilderPreview";
import { Code2, AlertCircle } from "lucide-react";

interface PreviewPayload {
  files: ParsedFile[];
  projectName: string;
}

type PageState = "checking" | "loading" | "ready" | "quota";

/**
 * `/preview-fullscreen` serves TWO distinct callers:
 *
 * 1. This spec's deep-linkable redirect: `?runId=...` → `/runs/{id}/preview/full`.
 *    Addressable without an opener tab.
 * 2. The live App Builder "Full Screen" button (AppBuilderPreview.handleFullscreen),
 *    which opens this bare path with NO query params (or `?error=quota` if the
 *    session-storage write failed) and passes files via sessionStorage key
 *    "__app_preview__". window.open is called WITHOUT "noopener" so the new tab
 *    shares the opener's browsing context and can read that key.
 *
 * Precedence: a runId always wins (case 1, unchanged). Otherwise this falls back
 * to reading the sessionStorage payload (case 2, restoring pre-015 behavior), and
 * only redirects to run history if that payload is also missing/unparseable.
 */
export default function PreviewFullscreenPage() {
  const router = useRouter();
  const [payload, setPayload] = useState<PreviewPayload | null>(null);
  const [state, setState] = useState<PageState>("checking");

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const runId = params.get("runId");

    if (runId) {
      // Redirect to the new route
      router.replace(routes.runPreviewFull(runId));
      return;
    }

    // Quota error flag from opener. It does NOT short-circuit the payload read
    // below: the quota tab is opened without "noopener", so it shares the
    // opener's sessionStorage, and setItem is atomic — a write that threw leaves
    // an earlier, successful, still-renderable payload intact. Read first, and
    // fall back to the "too large" dead end only if nothing usable is there.
    const quota = params.get("error") === "quota";

    setState("loading");

    // Small delay to ensure sessionStorage write from opener has flushed
    const timer = setTimeout(() => {
      const giveUp = () => {
        if (quota) {
          setState("quota");
          return;
        }
        router.replace(routes.runHistory());
      };
      try {
        const raw = sessionStorage.getItem("__app_preview__");
        if (!raw) {
          giveUp();
          return;
        }
        const data = JSON.parse(raw) as PreviewPayload;
        if (!data.files?.length) {
          giveUp();
          return;
        }
        setPayload(data);
        document.title = `${data.projectName || "Project"} — IDE Preview`;
        setState("ready");
      } catch {
        giveUp();
      }
    }, 100); // 100ms is enough for sessionStorage to be readable

    return () => clearTimeout(timer);
  }, [router]);

  if (state === "loading") {
    return (
      <div className="flex h-screen items-center justify-center bg-[#f5f5f0]">
        <div className="flex flex-col items-center gap-3">
          <Code2 className="h-8 w-8 text-gray-300 animate-pulse" />
          <p className="text-[12px] text-gray-400">Loading preview...</p>
        </div>
      </div>
    );
  }

  if (state === "quota") {
    return (
      <div className="flex h-screen items-center justify-center bg-[#f5f5f0]">
        <div className="flex flex-col items-center gap-4 text-center max-w-sm px-6">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-amber-50 border border-amber-200">
            <AlertCircle className="h-6 w-6 text-amber-500" />
          </div>
          <p className="text-[13px] font-semibold text-gray-700">Project too large for full screen</p>
          <p className="text-[11px] text-gray-400 leading-relaxed">
            The generated project exceeds the browser session storage limit (~5MB).
            Use the <span className="font-medium text-gray-600">Download ZIP</span> button
            in the preview panel to get all files.
          </p>
        </div>
      </div>
    );
  }

  if (state === "ready" && payload) {
    return (
      <div className="h-screen w-screen overflow-hidden">
        <AppBuilderPreview
          files={payload.files}
          projectName={payload.projectName}
          // No onRevise in fullscreen — revisions happen in the main panel
        />
      </div>
    );
  }

  // "checking" (runId redirect in progress) or a not-yet-resolved state —
  // render nothing while a redirect is in flight.
  return null;
}
