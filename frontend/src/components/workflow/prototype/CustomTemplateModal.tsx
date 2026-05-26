"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { X, Upload, Link, FileText, CheckCircle2, AlertCircle, Loader2 } from "lucide-react";
import { getToken } from "@/lib/api";
import { ENV } from "@/lib/env";

export interface CustomTemplate {
  id: string;
  name: string;
  body: string;
  source: "file" | "url";
  sourceRef: string;
}

const STORAGE_KEY = "prototype.customTemplates";

export function loadCustomTemplates(): CustomTemplate[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as CustomTemplate[]) : [];
  } catch {
    return [];
  }
}

export function saveCustomTemplate(ct: CustomTemplate): void {
  const existing = loadCustomTemplates().filter((t) => t.id !== ct.id);
  localStorage.setItem(STORAGE_KEY, JSON.stringify([ct, ...existing]));
}

export function deleteCustomTemplate(id: string): void {
  const existing = loadCustomTemplates().filter((t) => t.id !== id);
  localStorage.setItem(STORAGE_KEY, JSON.stringify(existing));
}

interface CustomTemplateModalProps {
  onConfirm: (ct: CustomTemplate) => void;
  onClose: () => void;
}

type Tab = "file" | "url";

export function CustomTemplateModal({ onConfirm, onClose }: CustomTemplateModalProps) {
  const [tab, setTab] = useState<Tab>("file");
  const [name, setName] = useState("");
  const [htmlBody, setHtmlBody] = useState<string | null>(null);
  const [sourceRef, setSourceRef] = useState("");
  const [source, setSource] = useState<"file" | "url">("file");

  // File upload state
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [fileName, setFileName] = useState<string | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);

  // URL fetch state
  const [urlInput, setUrlInput] = useState("");
  const [urlLoading, setUrlLoading] = useState(false);
  const [urlError, setUrlError] = useState<string | null>(null);
  const [urlFetched, setUrlFetched] = useState(false);

  const canConfirm = Boolean(name.trim() && htmlBody);

  const handleFileChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setFileError(null);
    setFileName(file.name);
    setSource("file");
    setSourceRef(file.name);
    const reader = new FileReader();
    reader.onload = (ev) => {
      const text = ev.target?.result as string;
      if (!text) {
        setFileError("Could not read file content.");
        return;
      }
      if (text.length > 2 * 1024 * 1024) {
        setFileError("File is too large (max 2 MB).");
        return;
      }
      setHtmlBody(text);
      // Auto-fill name from filename if empty
      if (!name) {
        setName(file.name.replace(/\.(html?)/i, "").replace(/[-_]/g, " "));
      }
    };
    reader.onerror = () => setFileError("Failed to read file.");
    reader.readAsText(file);
  }, [name]);

  const handleFetchUrl = useCallback(async () => {
    const url = urlInput.trim();
    if (!url) return;
    setUrlError(null);
    setUrlLoading(true);
    setUrlFetched(false);
    try {
      const token = getToken();
      const res = await fetch(
        `${ENV.API_URL}/api/prototype/fetch-url?url=${encodeURIComponent(url)}`,
        { headers: { Authorization: `Bearer ${token}` } },
      );
      const data = await res.json();
      if (!res.ok || data.error) {
        setUrlError(data.detail || data.error || "Failed to fetch URL.");
        return;
      }
      setHtmlBody(data.html as string);
      setSource("url");
      setSourceRef(url);
      setUrlFetched(true);
      // Auto-fill name from URL hostname if empty
      if (!name) {
        try {
          const hostname = new URL(url).hostname.replace(/^www\./, "");
          setName(hostname);
        } catch {
          // ignore
        }
      }
    } catch (err) {
      setUrlError("Network error — could not reach the server.");
    } finally {
      setUrlLoading(false);
    }
  }, [urlInput, name]);

  const handleConfirm = useCallback(() => {
    if (!canConfirm || !htmlBody) return;
    const ct: CustomTemplate = {
      id: `custom-${Date.now()}`,
      name: name.trim(),
      body: htmlBody,
      source,
      sourceRef,
    };
    saveCustomTemplate(ct);
    onConfirm(ct);
  }, [canConfirm, htmlBody, name, source, sourceRef, onConfirm]);

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={onClose} />

      {/* Modal */}
      <div className="relative z-10 w-full max-w-lg rounded-2xl border border-gray-200 bg-white shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-gray-100 px-5 py-4">
          <div>
            <h2 className="text-[14px] font-semibold text-gray-900">Upload custom template</h2>
            <p className="mt-0.5 text-[11px] text-gray-500">
              Use your own HTML file or a website as a starting point
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="flex h-7 w-7 items-center justify-center rounded-lg text-gray-400 hover:bg-gray-100 hover:text-gray-700"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-gray-100 px-5">
          {(["file", "url"] as Tab[]).map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => { setTab(t); setHtmlBody(null); setFileError(null); setUrlError(null); setUrlFetched(false); }}
              className={`flex items-center gap-1.5 border-b-2 px-3 py-2.5 text-[12px] font-medium transition-colors ${
                tab === t
                  ? "border-[#1B2A4A] text-[#1B2A4A]"
                  : "border-transparent text-gray-500 hover:text-gray-800"
              }`}
            >
              {t === "file" ? <Upload className="h-3.5 w-3.5" /> : <Link className="h-3.5 w-3.5" />}
              {t === "file" ? "Upload HTML file" : "From URL"}
            </button>
          ))}
        </div>

        {/* Body */}
        <div className="space-y-4 px-5 py-4">
          {/* Tab content */}
          {tab === "file" ? (
            <div>
              <input
                ref={fileInputRef}
                type="file"
                accept=".html,.htm"
                className="hidden"
                onChange={handleFileChange}
              />
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                className="flex w-full flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed border-gray-200 bg-gray-50 px-4 py-6 text-center transition-colors hover:border-gray-300 hover:bg-white"
              >
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-white border border-gray-200 shadow-sm">
                  <FileText className="h-5 w-5 text-gray-400" />
                </div>
                <div>
                  <p className="text-[12px] font-medium text-gray-700">
                    {fileName ? fileName : "Click to choose an HTML file"}
                  </p>
                  <p className="text-[10px] text-gray-400">.html or .htm, max 2 MB</p>
                </div>
              </button>
              {fileError && (
                <p className="mt-2 flex items-center gap-1.5 text-[11px] text-red-600">
                  <AlertCircle className="h-3.5 w-3.5 flex-shrink-0" />
                  {fileError}
                </p>
              )}
              {htmlBody && !fileError && (
                <p className="mt-2 flex items-center gap-1.5 text-[11px] text-green-600">
                  <CheckCircle2 className="h-3.5 w-3.5 flex-shrink-0" />
                  Loaded {(htmlBody.length / 1024).toFixed(1)} KB
                </p>
              )}
            </div>
          ) : (
            <div>
              <div className="flex gap-2">
                <input
                  type="url"
                  value={urlInput}
                  onChange={(e) => { setUrlInput(e.target.value); setUrlFetched(false); setUrlError(null); }}
                  onKeyDown={(e) => { if (e.key === "Enter") handleFetchUrl(); }}
                  placeholder="https://example.com"
                  className="flex-1 rounded-lg border border-gray-200 bg-white px-3 py-2 text-[12px] text-gray-900 placeholder:text-gray-400 focus:border-gray-400 focus:outline-none"
                />
                <button
                  type="button"
                  onClick={handleFetchUrl}
                  disabled={!urlInput.trim() || urlLoading}
                  className="flex items-center gap-1.5 rounded-lg bg-[#1B2A4A] px-3 py-2 text-[12px] font-medium text-white disabled:opacity-50 hover:bg-[#0F1B33]"
                >
                  {urlLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Link className="h-3.5 w-3.5" />}
                  Fetch
                </button>
              </div>
              {urlError && (
                <p className="mt-2 flex items-center gap-1.5 text-[11px] text-red-600">
                  <AlertCircle className="h-3.5 w-3.5 flex-shrink-0" />
                  {urlError}
                </p>
              )}
              {urlFetched && htmlBody && (
                <p className="mt-2 flex items-center gap-1.5 text-[11px] text-green-600">
                  <CheckCircle2 className="h-3.5 w-3.5 flex-shrink-0" />
                  Fetched {(htmlBody.length / 1024).toFixed(1)} KB from {new URL(urlInput).hostname}
                </p>
              )}
            </div>
          )}

          {/* Name input */}
          <div>
            <label className="block text-[11px] font-medium text-gray-700 mb-1">
              Template name <span className="text-red-400">*</span>
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. My Company Dashboard"
              className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-[12px] text-gray-900 placeholder:text-gray-400 focus:border-gray-400 focus:outline-none"
            />
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 border-t border-gray-100 px-5 py-3">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg px-4 py-2 text-[12px] font-medium text-gray-600 hover:bg-gray-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleConfirm}
            disabled={!canConfirm}
            className="rounded-lg bg-[#1B2A4A] px-4 py-2 text-[12px] font-semibold text-white disabled:opacity-40 hover:bg-[#0F1B33]"
          >
            Use this template
          </button>
        </div>
      </div>
    </div>
  );
}
