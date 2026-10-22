"use client";

import { useEffect, useRef, useState } from "react";
import { AlertCircle, FileText, Link2, Loader2, Upload, X, ZoomIn } from "lucide-react";

/** A single PNG/JPEG frame exported from Figma. */
export type FigmaImageFrame = {
  kind: "image";
  file: File;
  description: string;
  previewUrl: string;
};

/** A multi-page PDF exported from Figma (File → Export frames to PDF). */
export type FigmaPdfFrame = {
  kind: "pdf";
  file: File;
  description: string;
};

export type FigmaFrame = FigmaImageFrame | FigmaPdfFrame;

interface FigmaUploadSectionProps {
  frames: FigmaFrame[];
  onChange: (frames: FigmaFrame[]) => void;
}

const MAX_FRAME_BYTES = 4 * 1024 * 1024;   // 4 MB per PNG/JPG
const MAX_PDF_BYTES  = 20 * 1024 * 1024;   // 20 MB for multi-page PDF
const MAX_FRAMES = 20;

function validateFile(
  file: File,
  currentFrames: FigmaFrame[],
): string | null {
  const isPdf = file.type === "application/pdf";

  if (isPdf) {
    // Only one PDF at a time — it already contains all screens
    if (currentFrames.some((f) => f.kind === "pdf")) {
      return "Only one PDF can be uploaded (it already contains all frames). Remove the existing PDF first.";
    }
    if (file.size > MAX_PDF_BYTES) {
      return `PDF too large (max ${MAX_PDF_BYTES / (1024 * 1024)} MB)`;
    }
    return null;
  }

  if (!["image/png", "image/jpeg"].includes(file.type)) {
    return "Please export your screens as PNG from Figma: select a frame → right-click → Export → PNG @ 1×. Or export all frames as PDF via File → Export → Export frames to PDF.";
  }
  if (file.size > MAX_FRAME_BYTES) {
    return "File too large (max 4 MB per frame)";
  }
  const imageCount = currentFrames.filter((f) => f.kind === "image").length;
  if (imageCount >= MAX_FRAMES) {
    return "Maximum 20 frames reached";
  }
  return null;
}

export function FigmaUploadSection({ frames, onChange }: FigmaUploadSectionProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [urlInput, setUrlInput] = useState("");
  const [urlLoading, setUrlLoading] = useState(false);
  const [dragSrcIdx, setDragSrcIdx] = useState<number | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const pdfInputRef  = useRef<HTMLInputElement>(null);
  const zipInputRef  = useRef<HTMLInputElement>(null);

  // Cleanup image object URLs on unmount
  useEffect(() => {
    return () => {
      frames.forEach((f) => {
        if (f.kind === "image") URL.revokeObjectURL(f.previewUrl);
      });
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Clipboard paste — images only (PDF can't be pasted from Figma clipboard)
  useEffect(() => {
    const handler = (e: ClipboardEvent) => {
      const items = Array.from(e.clipboardData?.items ?? []);
      for (const item of items) {
        if (item.type === "image/png" || item.type === "image/jpeg") {
          const blob = item.getAsFile();
          if (blob) {
            processSingleFile(
              new File([blob], `pasted-image.${item.type === "image/png" ? "png" : "jpg"}`, { type: item.type })
            );
          }
        }
      }
    };
    window.addEventListener("paste", handler);
    return () => window.removeEventListener("paste", handler);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [frames, onChange]);

  const processSingleFile = (file: File) => {
    const err = validateFile(file, frames);
    if (err) { setError(err); return; }
    setError(null);
    if (file.type === "application/pdf") {
      const pdfFrame: FigmaPdfFrame = { kind: "pdf", file, description: "" };
      onChange([...frames, pdfFrame]);
    } else {
      const previewUrl = URL.createObjectURL(file);
      const imgFrame: FigmaImageFrame = { kind: "image", file, description: "", previewUrl };
      onChange([...frames, imgFrame]);
    }
  };

  // Batch-process multiple files into ONE onChange call (prevents state-closure bug)
  const processFiles = (list: FileList | File[]) => {
    const incoming = Array.from(list);
    const newFrames: FigmaFrame[] = [];
    let firstError: string | null = null;
    // Working copy for validation — includes already-added frames + newFrames so far
    const working = [...frames];

    for (const file of incoming) {
      const err = validateFile(file, working);
      if (err) {
        if (!firstError) firstError = err;
        continue;
      }
      if (file.type === "application/pdf") {
        const f: FigmaPdfFrame = { kind: "pdf", file, description: "" };
        newFrames.push(f);
        working.push(f);
      } else {
        const previewUrl = URL.createObjectURL(file);
        const f: FigmaImageFrame = { kind: "image", file, description: "", previewUrl };
        newFrames.push(f);
        working.push(f);
      }
    }

    if (firstError) setError(firstError);
    else setError(null);
    if (newFrames.length > 0) onChange([...frames, ...newFrames]);
  };

  const removeFrame = (idx: number) => {
    const f = frames[idx];
    if (f.kind === "image") URL.revokeObjectURL(f.previewUrl);
    onChange(frames.filter((_, i) => i !== idx));
  };

  const clearAll = () => {
    frames.forEach((f) => { if (f.kind === "image") URL.revokeObjectURL(f.previewUrl); });
    onChange([]);
  };

  const handleUrlAdd = async () => {
    const url = urlInput.trim();
    if (!url) return;
    setUrlLoading(true);
    setError(null);
    try {
      const res = await fetch(url);
      const ct = res.headers.get("content-type") ?? "";
      if (!ct.startsWith("image/png") && !ct.startsWith("image/jpeg")) {
        setError("URL did not return a PNG or JPEG image");
        return;
      }
      const blob = await res.blob();
      const fname = url.split("/").pop()?.split("?")[0] ?? "frame.png";
      processSingleFile(new File([blob], fname, { type: blob.type }));
      setUrlInput("");
    } catch {
      setError("Could not fetch URL");
    } finally {
      setUrlLoading(false);
    }
  };

  const handleZipChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const JSZip = (await import("jszip")).default;
      const zip = await JSZip.loadAsync(file);
      const zipFiles: File[] = [];
      for (const [path, entry] of Object.entries(zip.files)) {
        if (entry.dir) continue;
        const ext = path.split(".").pop()?.toLowerCase();
        if (ext === "png" || ext === "jpg" || ext === "jpeg") {
          const blob = await entry.async("blob");
          const fname = path.split("/").pop() ?? path;
          const mime = ext === "png" ? "image/png" : "image/jpeg";
          zipFiles.push(new File([blob], fname, { type: mime }));
        }
      }
      if (zipFiles.length > 0) processFiles(zipFiles);
    } catch {
      setError("Could not read ZIP file");
    }
    e.target.value = "";
  };

  const handleDragOver = (e: React.DragEvent) => { e.preventDefault(); setIsDragging(true); };
  const handleDragLeave = (e: React.DragEvent) => { e.preventDefault(); setIsDragging(false); };
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    processFiles(e.dataTransfer.files);
  };

  const handleCardDragStart = (idx: number) => setDragSrcIdx(idx);
  const handleCardDrop = (idx: number) => {
    if (dragSrcIdx === null || dragSrcIdx === idx) return;
    const arr = [...frames];
    const [moved] = arr.splice(dragSrcIdx, 1);
    arr.splice(idx, 0, moved);
    onChange(arr);
    setDragSrcIdx(null);
  };

  const updateDescription = (idx: number, description: string) => {
    const arr = [...frames];
    arr[idx] = { ...arr[idx], description };
    onChange(arr);
  };

  const isEmpty = frames.length === 0;
  const imageCount = frames.filter((f) => f.kind === "image").length;
  const hasPdf = frames.some((f) => f.kind === "pdf");

  return (
    <div className="flex flex-col gap-3">

      {/* ── Empty state ────────────────────────────────────────────────── */}
      {isEmpty ? (
        <div
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          className={`flex flex-col items-center justify-center gap-3 rounded-[var(--radius-card)] border-2 border-dashed p-8 transition-colors ${
            isDragging ? "border-brand bg-brand-fill" : "border-line-control bg-surface-warm"
          }`}
        >
          <div className="flex h-12 w-12 items-center justify-center rounded-xl border border-dashed border-line-control bg-surface-white">
            <svg className="h-6 w-6 text-ink-400" viewBox="0 0 38 57" fill="currentColor" aria-hidden="true">
              <path d="M19 28.5a9.5 9.5 0 1 1 19 0 9.5 9.5 0 0 1-19 0z" />
              <path d="M0 47.5A9.5 9.5 0 0 1 9.5 38H19v9.5a9.5 9.5 0 0 1-19 0z" />
              <path d="M19 0v19h9.5a9.5 9.5 0 0 0 0-19H19z" />
              <path d="M0 9.5A9.5 9.5 0 0 1 9.5 0H19v19H9.5A9.5 9.5 0 0 1 0 9.5z" />
              <path d="M0 28.5A9.5 9.5 0 0 1 9.5 19H19v19H9.5A9.5 9.5 0 0 1 0 28.5z" />
            </svg>
          </div>
          <div className="text-center">
            <p className="text-[13px] font-medium text-ink-700">Drop Figma screens here</p>
            <p className="mt-0.5 text-[11px] text-ink-400">PNG / JPEG frames or a multi-page PDF — all screens in one file</p>
          </div>

          {/* Method buttons */}
          <div className="flex flex-wrap items-center justify-center gap-2">
            <button type="button" onClick={() => fileInputRef.current?.click()}
              className="inline-flex items-center gap-1.5 rounded-[var(--radius-button)] border border-line-control bg-surface-white px-3 py-1.5 text-[11px] font-medium text-ink-700 transition-colors hover:border-brand hover:text-brand">
              <Upload className="h-3 w-3" />PNG / JPEG
            </button>
            <button type="button" onClick={() => pdfInputRef.current?.click()}
              className="inline-flex items-center gap-1.5 rounded-[var(--radius-button)] border border-line-control bg-surface-white px-3 py-1.5 text-[11px] font-medium text-ink-700 transition-colors hover:border-brand hover:text-brand">
              <FileText className="h-3 w-3" />Upload PDF
            </button>
            <button type="button" onClick={() => setError("Press Ctrl+V / ⌘+V to paste an image from your clipboard")}
              className="inline-flex items-center gap-1.5 rounded-[var(--radius-button)] border border-line-control bg-surface-white px-3 py-1.5 text-[11px] font-medium text-ink-700 transition-colors hover:border-brand hover:text-brand">
              <ZoomIn className="h-3 w-3" />Paste image
            </button>
            <button type="button" onClick={() => zipInputRef.current?.click()}
              className="inline-flex items-center gap-1.5 rounded-[var(--radius-button)] border border-line-control bg-surface-white px-3 py-1.5 text-[11px] font-medium text-ink-700 transition-colors hover:border-brand hover:text-brand">
              <Upload className="h-3 w-3" />From ZIP
            </button>
          </div>

          {/* URL import */}
          <div className="flex w-full max-w-md items-center gap-2">
            <div className="relative flex-1">
              <Link2 className="pointer-events-none absolute left-2.5 top-1/2 h-3 w-3 -translate-y-1/2 text-ink-400" />
              <input type="url" value={urlInput} onChange={(e) => setUrlInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleUrlAdd()}
                placeholder="https://…/frame.png"
                className="w-full rounded-[var(--radius-button)] border border-line-border bg-surface-white py-1.5 pl-7 pr-3 text-[11px] text-ink-900 placeholder:text-ink-400 focus:border-line-control focus:outline-none" />
            </div>
            <button type="button" onClick={handleUrlAdd} disabled={urlLoading || !urlInput.trim()}
              className="inline-flex items-center gap-1.5 rounded-[var(--radius-button)] bg-brand px-3 py-1.5 text-[11px] font-semibold text-white transition-colors hover:bg-brand-pressed disabled:cursor-not-allowed disabled:opacity-40">
              {urlLoading ? <Loader2 className="h-3 w-3 animate-spin" /> : null}Add URL
            </button>
          </div>
        </div>

      ) : (
        /* ── Filled state ────────────────────────────────────────────────── */
        <div>
          <div className="mb-2 flex items-center justify-between">
            <span className="text-[10px] text-ink-400">
              {hasPdf ? "1 PDF (all screens)" : `${imageCount} / 20 frames`}
            </span>
            <div className="flex items-center gap-2">
              {!hasPdf && (
                <>
                  <button type="button" onClick={() => fileInputRef.current?.click()}
                    className="inline-flex items-center gap-1 text-[10px] font-medium text-brand hover:underline">
                    <Upload className="h-3 w-3" />Add more
                  </button>
                  <span className="text-ink-300">·</span>
                  <button type="button" onClick={() => pdfInputRef.current?.click()}
                    className="text-[10px] font-medium text-ink-500 hover:text-ink-800">
                    Add PDF
                  </button>
                  <span className="text-ink-300">·</span>
                  <button type="button" onClick={() => zipInputRef.current?.click()}
                    className="text-[10px] font-medium text-ink-500 hover:text-ink-800">
                    From ZIP
                  </button>
                  <span className="text-ink-300">·</span>
                </>
              )}
              <button type="button" onClick={clearAll}
                className="text-[10px] font-medium text-status-failed hover:underline">
                Clear all
              </button>
            </div>
          </div>

          <div
            onDragOver={handleDragOver} onDragLeave={handleDragLeave} onDrop={handleDrop}
            className={`rounded-[var(--radius-card)] border-2 border-dashed p-2 transition-colors ${isDragging ? "border-brand bg-brand-fill" : "border-transparent"}`}>
            <div className="grid gap-2" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(130px, 1fr))" }}>
              {frames.map((frame, idx) => (
                <div key={`${frame.kind}-${frame.file.name}-${idx}`}
                  draggable={frame.kind === "image"}
                  onDragStart={() => frame.kind === "image" && handleCardDragStart(idx)}
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={() => frame.kind === "image" && handleCardDrop(idx)}
                  className="group relative flex flex-col overflow-hidden rounded-lg border border-line-border bg-surface-white">

                  {/* Remove button */}
                  <button type="button" onClick={() => removeFrame(idx)}
                    className="absolute right-1 top-1 z-10 hidden h-5 w-5 items-center justify-center rounded-full bg-surface-white/90 text-ink-400 shadow-sm hover:text-status-failed group-hover:flex"
                    title="Remove">
                    <X className="h-3 w-3" />
                  </button>

                  {frame.kind === "image" ? (
                    /* Image thumbnail */
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={frame.previewUrl} alt={frame.file.name}
                      className="h-[80px] w-full object-cover object-top" />
                  ) : (
                    /* PDF card */
                    <div className="flex h-[80px] flex-col items-center justify-center gap-1 bg-gradient-to-br from-red-50 to-orange-50">
                      <FileText className="h-8 w-8 text-red-400" />
                      <span className="text-[9px] font-medium text-ink-500 uppercase tracking-wide">PDF</span>
                    </div>
                  )}

                  <div className="px-1.5 py-1">
                    {frame.kind === "pdf" ? (
                      <span className="block truncate text-[10px] text-ink-600" title={frame.file.name}>
                        {frame.file.name}
                      </span>
                    ) : (
                      <input type="text" value={frame.description}
                        onChange={(e) => updateDescription(idx, e.target.value)}
                        placeholder="Label…"
                        className="w-full rounded border-0 bg-transparent p-0 text-[10px] text-ink-600 placeholder:text-ink-300 focus:outline-none" />
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* URL import (images only, not for PDF) */}
          {!hasPdf && (
            <div className="mt-2 flex items-center gap-2">
              <div className="relative flex-1">
                <Link2 className="pointer-events-none absolute left-2.5 top-1/2 h-3 w-3 -translate-y-1/2 text-ink-400" />
                <input type="url" value={urlInput} onChange={(e) => setUrlInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleUrlAdd()}
                  placeholder="Add from URL…"
                  className="w-full rounded-[var(--radius-button)] border border-line-border bg-surface-warm py-1.5 pl-7 pr-3 text-[11px] text-ink-900 placeholder:text-ink-400 focus:border-line-control focus:outline-none" />
              </div>
              <button type="button" onClick={handleUrlAdd} disabled={urlLoading || !urlInput.trim()}
                className="inline-flex items-center gap-1.5 rounded-[var(--radius-button)] bg-brand px-3 py-1.5 text-[11px] font-semibold text-white transition-colors hover:bg-brand-pressed disabled:cursor-not-allowed disabled:opacity-40">
                {urlLoading ? <Loader2 className="h-3 w-3 animate-spin" /> : null}Add
              </button>
            </div>
          )}
        </div>
      )}

      {/* Error */}
      {error && (
        <p className="mt-1 flex items-center gap-1.5 text-[11px] text-status-failed">
          <AlertCircle className="h-3.5 w-3.5 flex-shrink-0" />{error}
        </p>
      )}

      {/* Tip */}
      <p className="text-[11px] text-ink-400">
        Tip: export PNG frames (right-click → Export → PNG @ 1×) or the full PDF (File → Export → Export frames to PDF).
      </p>

      {/* Hidden inputs */}
      <input ref={fileInputRef} type="file" accept=".png,.jpg,.jpeg" multiple className="hidden"
        onChange={(e) => { if (e.target.files) processFiles(e.target.files); e.target.value = ""; }} />
      <input ref={pdfInputRef} type="file" accept=".pdf" className="hidden"
        onChange={(e) => { if (e.target.files?.[0]) processSingleFile(e.target.files[0]); e.target.value = ""; }} />
      <input ref={zipInputRef} type="file" accept=".zip" className="hidden"
        onChange={handleZipChange} />
    </div>
  );
}
