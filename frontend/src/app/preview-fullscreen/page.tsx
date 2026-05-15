"use client";

// ─── Full-screen App Builder IDE ──────────────────────────────────────────────
// Opened in a new tab by AppBuilderPreview's "Full Screen" button.
// Files are passed via sessionStorage key "__app_preview__".
//
// Why sessionStorage works:
//   window.open("/preview-fullscreen", "_blank") — WITHOUT "noopener" —
//   keeps the new tab in the same browsing context group, so it can read
//   sessionStorage written by the opener tab. Adding "noopener" would sever
//   that link and the read would always return null.

import { useEffect, useState } from "react";
import { AppBuilderPreview, type ParsedFile } from "@/components/preview/AppBuilderPreview";
import { Code2, AlertCircle } from "lucide-react";

interface PreviewPayload {
  files: ParsedFile[];
  projectName: string;
}

type PageState = "loading" | "ready" | "error" | "quota";

export default function PreviewFullscreenPage() {
  const [payload, setPayload] = useState<PreviewPayload | null>(null);
  const [state, setState] = useState<PageState>("loading");

  useEffect(() => {
    // Check for quota error flag from opener
    const params = new URLSearchParams(window.location.search);
    if (params.get("error") === "quota") {
      setState("quota");
      return;
    }

    // Small delay to ensure sessionStorage write from opener has flushed
    const timer = setTimeout(() => {
      try {
        const raw = sessionStorage.getItem("__app_preview__");
        if (!raw) {
          setState("error");
          return;
        }
        const data = JSON.parse(raw) as PreviewPayload;
        if (!data.files?.length) {
          setState("error");
          return;
        }
        setPayload(data);
        document.title = `${data.projectName || "Project"} — IDE Preview`;
        setState("ready");
      } catch {
        setState("error");
      }
    }, 100); // 100ms is enough for sessionStorage to be readable

    return () => clearTimeout(timer);
  }, []);

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

  if (state === "error" || !payload) {
    return (
      <div className="flex h-screen items-center justify-center bg-[#f5f5f0]">
        <div className="flex flex-col items-center gap-4 text-center max-w-sm px-6">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-gray-100 border border-gray-200">
            <AlertCircle className="h-6 w-6 text-gray-400" />
          </div>
          <p className="text-[13px] font-semibold text-gray-700">No preview data found</p>
          <p className="text-[11px] text-gray-400 leading-relaxed">
            Click the <span className="font-medium text-gray-600">Full Screen</span> button
            in the App Builder preview panel — don&apos;t navigate here directly.
          </p>
          <button
            onClick={() => window.close()}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#1B2A4A] text-white text-[11px] font-medium hover:bg-[#243656] transition-colors"
          >
            Close tab
          </button>
        </div>
      </div>
    );
  }

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
