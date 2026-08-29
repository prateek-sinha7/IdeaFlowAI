"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ChevronRight, ChevronDown, File, Folder, FolderOpen,
  Copy, Check, Download, X, Search, Code2, Package,
  FileText, FileCode, FileJson, Settings, Globe,
  RefreshCw, FolderDown, Maximize2,
} from "lucide-react";
import { useClipboardCopy } from "@/hooks/useClipboardCopy";
import { utf8Bytes } from "@/lib/byteSize";

// ─── Types ────────────────────────────────────────────────────────────────────

export interface ParsedFile {
  path: string;
  name: string;
  ext: string;
  content: string;
  language: string;
}

interface TreeNode {
  name: string;
  path: string;
  type: "file" | "folder";
  children?: TreeNode[];
  file?: ParsedFile;
}

interface OpenTab {
  path: string;
  name: string;
}

// ─── Color palette — theme tokens (see globals.css), not literal hex ──────────
// Background:   bg-surface-warm
// Sidebar:      bg-surface-white
// Active row:   bg-brand-fill
// Border:       border-line-control / border-line-divider
// Text primary: text-ink-900
// Text muted:   text-ink-500
// Text dim:     text-ink-300
// Accent:       text-brand / bg-brand
// Code bg:      bg-surface-card
// Line nums:    text-ink-300

// ─── Language map (used by parseAppBuilderFilesForIDE in PreviewPanel) ───────
// eslint-disable-next-line @typescript-eslint/no-unused-vars
const LANG_MAP: Record<string, string> = {
  ts: "typescript", tsx: "typescript", js: "javascript", jsx: "javascript",
  py: "python", json: "json", md: "markdown", yml: "yaml", yaml: "yaml",
  css: "css", html: "html", sh: "bash", bash: "bash", sql: "sql",
  dockerfile: "dockerfile", env: "bash", toml: "toml", prisma: "typescript",
  graphql: "graphql", rs: "rust", go: "go", java: "java", cs: "csharp",
  rb: "ruby", php: "php", swift: "swift", kt: "kotlin", txt: "plaintext",
  xml: "xml", gitignore: "bash", lock: "plaintext",
};

// ─── File icon helper (monochrome gray — enterprise) ──────────────────────────

function getFileIcon(ext: string): typeof File {
  const map: Record<string, typeof File> = {
    ts: FileCode, tsx: FileCode, js: FileCode, jsx: FileCode,
    py: FileCode, json: FileJson, md: FileText, yml: Settings,
    yaml: Settings, css: FileCode, html: Globe, sh: FileCode,
    dockerfile: Package, env: Settings, sql: FileCode,
  };
  return map[ext.toLowerCase()] || File;
}

// ─── Tree builder ─────────────────────────────────────────────────────────────

function buildTree(files: ParsedFile[]): TreeNode[] {
  const root: TreeNode[] = [];
  const map = new Map<string, TreeNode>();

  const sorted = [...files].sort((a, b) => a.path.localeCompare(b.path));

  for (const file of sorted) {
    const parts = file.path.split("/");
    let current = root;
    let currentPath = "";

    for (let i = 0; i < parts.length - 1; i++) {
      currentPath = currentPath ? `${currentPath}/${parts[i]}` : parts[i];
      if (!map.has(currentPath)) {
        const folder: TreeNode = { name: parts[i], path: currentPath, type: "folder", children: [] };
        map.set(currentPath, folder);
        current.push(folder);
      }
      current = map.get(currentPath)!.children!;
    }

    current.push({ name: file.name, path: file.path, type: "file", file });
  }

  return root;
}

// ─── Search matching ──────────────────────────────────────────────────────────

function fileMatchesQuery(name: string, query: string): boolean {
  return !query || name.toLowerCase().includes(query.toLowerCase());
}

function hasMatchingDescendant(node: TreeNode, query: string): boolean {
  if (node.type === "file") return fileMatchesQuery(node.name, query);
  return (node.children || []).some(child => hasMatchingDescendant(child, query));
}

// ─── Syntax highlighting (highlight.js — GitHub light theme) ─────────────────

declare global {
  interface Window {
    hljs?: {
      highlight: (code: string, opts: { language: string }) => { value: string };
      highlightAuto: (code: string) => { value: string };
      getLanguage: (lang: string) => unknown;
    };
  }
}

let hlLoaded = false;
let hlLoading = false;
const hlCallbacks: Array<() => void> = [];

function loadHighlightJs(cb: () => void) {
  if (hlLoaded) { cb(); return; }
  hlCallbacks.push(cb);
  if (hlLoading) return;
  hlLoading = true;

  // GitHub light theme — clean, professional, matches our UI
  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = "https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github.min.css";
  document.head.appendChild(link);

  const script = document.createElement("script");
  script.src = "https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js";
  script.onload = () => {
    hlLoaded = true;
    hlCallbacks.forEach(fn => fn());
    hlCallbacks.length = 0;
  };
  document.head.appendChild(script);
}

function highlightCode(code: string, lang: string): string {
  if (!window.hljs) return escapeHtml(code);
  try {
    const supported = window.hljs.getLanguage(lang);
    if (supported) return window.hljs.highlight(code, { language: lang }).value;
    return window.hljs.highlightAuto(code).value;
  } catch {
    return escapeHtml(code);
  }
}

function escapeHtml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

// ─── FileTreeNode ─────────────────────────────────────────────────────────────

function FileTreeNode({
  node, depth, activeFile, onSelect, expandedPaths, onToggle, searchQuery,
}: {
  node: TreeNode;
  depth: number;
  activeFile: string | null;
  onSelect: (file: ParsedFile) => void;
  expandedPaths: Set<string>;
  onToggle: (path: string) => void;
  searchQuery: string;
}) {
  const isExpanded = expandedPaths.has(node.path) || !!searchQuery;
  const isActive = node.type === "file" && activeFile === node.path;
  const indent = depth * 14;

  if (node.type === "folder") {
    if (!hasMatchingDescendant(node, searchQuery)) return null;
    return (
      <div>
        <button
          onClick={() => onToggle(node.path)}
          className="w-full flex items-center gap-1 py-[3px] text-left hover:bg-surface-warm transition-colors"
          style={{ paddingLeft: `${10 + indent}px`, paddingRight: "8px" }}
        >
          <span className="text-ink-400 flex-shrink-0 w-3">
            {isExpanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
          </span>
          <span className="text-ink-400 flex-shrink-0">
            {isExpanded ? <FolderOpen className="h-3.5 w-3.5" /> : <Folder className="h-3.5 w-3.5" />}
          </span>
          <span className="text-[11px] font-medium text-ink-700 truncate ml-1">{node.name}</span>
        </button>
        {isExpanded && node.children?.map(child => (
          <FileTreeNode
            key={child.path}
            node={child}
            depth={depth + 1}
            activeFile={activeFile}
            onSelect={onSelect}
            expandedPaths={expandedPaths}
            onToggle={onToggle}
            searchQuery={searchQuery}
          />
        ))}
      </div>
    );
  }

  const Icon = getFileIcon(node.file?.ext || "");
  if (!fileMatchesQuery(node.name, searchQuery)) return null;

  return (
    <button
      onClick={() => node.file && onSelect(node.file)}
      className={`w-full flex items-center gap-1.5 py-[3px] text-left transition-colors border-l-2 ${
        isActive
          ? "bg-brand-fill border-l-brand"
          : "border-l-transparent hover:bg-surface-warm"
      }`}
      style={{ paddingLeft: `${10 + indent}px`, paddingRight: "8px" }}
    >
      <Icon className={`h-3.5 w-3.5 flex-shrink-0 ${isActive ? "text-brand" : "text-ink-400"}`} />
      <span className={`text-[11px] truncate ${isActive ? "text-brand font-medium" : "text-ink-600"}`}>
        {node.name}
      </span>
    </button>
  );
}

// ─── CodeViewer ───────────────────────────────────────────────────────────────

function CodeViewer({ file }: { file: ParsedFile | null }) {
  const [highlighted, setHighlighted] = useState("");
  const { copied, failed, copy } = useClipboardCopy();
  const [hlReady, setHlReady] = useState(hlLoaded);

  useEffect(() => {
    if (!hlReady) loadHighlightJs(() => setHlReady(true));
  }, [hlReady]);

  useEffect(() => {
    if (!file) { setHighlighted(""); return; }
    if (hlReady) setHighlighted(highlightCode(file.content, file.language));
    else setHighlighted(escapeHtml(file.content));
  }, [file, hlReady]);

  const handleCopy = () => {
    if (file) void copy(file.content);
  };

  const handleDownload = () => {
    if (!file) return;
    const blob = new Blob([file.content], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = file.name;
    a.click();
    URL.revokeObjectURL(url);
  };

  if (!file) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center bg-surface-card">
        <Code2 className="h-10 w-10 text-ink-200 mb-3" />
        <p className="text-[12px] text-ink-400 font-medium">Select a file to view its contents</p>
        <p className="text-[11px] text-ink-300 mt-1">Click any file in the explorer</p>
      </div>
    );
  }

  const lines = file.content.split("\n");

  return (
    <div className="flex-1 flex flex-col bg-surface-white min-w-0 overflow-hidden">
      {/* File header bar */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-line-divider bg-surface-white flex-shrink-0">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-[11px] text-ink-500 truncate font-mono">{file.path}</span>
          <span className="text-[9px] px-1.5 py-0.5 rounded bg-line-faint-row text-ink-500 font-semibold uppercase flex-shrink-0">
            {file.ext || "txt"}
          </span>
          <span className="text-[9px] text-ink-400 flex-shrink-0">{lines.length} lines</span>
        </div>
        <div className="flex items-center gap-1 flex-shrink-0">
          <button
            onClick={handleCopy}
            className="flex items-center gap-1 px-2.5 py-1 rounded-lg text-[10px] font-medium text-ink-500 hover:text-ink-800 hover:bg-line-faint-row border border-line-control transition-all"
          >
            {copied ? <Check className="h-3 w-3 text-status-done" /> : <Copy className="h-3 w-3" />}
            {copied ? "Copied" : failed ? "Copy failed" : "Copy"}
          </button>
          <button
            onClick={handleDownload}
            className="flex items-center gap-1 px-2.5 py-1 rounded-lg text-[10px] font-medium text-ink-500 hover:text-ink-800 hover:bg-line-faint-row border border-line-control transition-all"
          >
            <Download className="h-3 w-3" />
            Download
          </button>
        </div>
      </div>

      {/* Code area */}
      <div className="flex-1 overflow-auto bg-surface-card">
        <div className="flex min-w-max">
          {/* Line numbers */}
          <div
            className="select-none text-right pr-4 pl-4 py-4 text-[11px] font-mono leading-[1.65] text-ink-300 bg-surface-white border-r border-line-divider flex-shrink-0"
            style={{ minWidth: `${String(lines.length).length * 8 + 32}px` }}
          >
            {lines.map((_, i) => (
              <div key={i}>{i + 1}</div>
            ))}
          </div>
          {/* Highlighted code */}
          <pre
            className="flex-1 py-4 pl-5 pr-8 text-[12px] font-mono leading-[1.65] bg-surface-card overflow-visible"
            style={{ margin: 0, whiteSpace: "pre" }}
            dangerouslySetInnerHTML={{ __html: highlighted || escapeHtml(file.content) }}
          />
        </div>
      </div>
    </div>
  );
}

// ─── Main AppBuilderPreview ───────────────────────────────────────────────────

interface AppBuilderPreviewProps {
  files: ParsedFile[];
  onRevise?: (instruction: string) => void;
  projectName?: string;
}

export function AppBuilderPreview({ files, onRevise, projectName = "Project" }: AppBuilderPreviewProps) {
  const [activeFile, setActiveFile] = useState<ParsedFile | null>(null);
  const [openTabs, setOpenTabs] = useState<OpenTab[]>([]);
  const [expandedPaths, setExpandedPaths] = useState<Set<string>>(new Set());
  const [searchQuery, setSearchQuery] = useState("");
  const [sidebarWidth, setSidebarWidth] = useState(220);
  const [isDragging, setIsDragging] = useState(false);
  const [revisionText, setRevisionText] = useState("");
  const [isZipping, setIsZipping] = useState(false);
  const dragRef = useRef<number>(0);

  const tree = useMemo(() => buildTree(files), [files]);
  const visibleFiles = useMemo(
    () => (searchQuery ? files.filter(f => fileMatchesQuery(f.name, searchQuery)) : files),
    [files, searchQuery],
  );

  // Auto-expand top-level folders, select first file
  useEffect(() => {
    if (files.length === 0) return;
    const topFolders = new Set<string>();
    files.forEach(f => {
      const parts = f.path.split("/");
      if (parts.length > 1) topFolders.add(parts[0]);
    });
    setExpandedPaths(topFolders);
    if (files.length > 0 && !activeFile) {
      setActiveFile(files[0]);
      setOpenTabs([{ path: files[0].path, name: files[0].name }]);
    }
  }, [files]);

  const handleSelectFile = useCallback((file: ParsedFile) => {
    setActiveFile(file);
    setOpenTabs(prev => {
      if (prev.find(t => t.path === file.path)) return prev;
      return [...prev, { path: file.path, name: file.name }];
    });
  }, []);

  const handleCloseTab = useCallback((path: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setOpenTabs(prev => {
      const next = prev.filter(t => t.path !== path);
      if (activeFile?.path === path) {
        const idx = prev.findIndex(t => t.path === path);
        const newActive = next[Math.min(idx, next.length - 1)];
        setActiveFile(newActive ? (files.find(f => f.path === newActive.path) || null) : null);
      }
      return next;
    });
  }, [activeFile, files]);

  const handleToggleFolder = useCallback((path: string) => {
    setExpandedPaths(prev => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path); else next.add(path);
      return next;
    });
  }, []);

  // Resize drag
  const handleMouseDown = (e: React.MouseEvent) => {
    setIsDragging(true);
    dragRef.current = e.clientX - sidebarWidth;
    e.preventDefault();
  };

  useEffect(() => {
    if (!isDragging) return;
    const onMove = (e: MouseEvent) => setSidebarWidth(Math.max(160, Math.min(380, e.clientX - dragRef.current)));
    const onUp = () => setIsDragging(false);
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => { window.removeEventListener("mousemove", onMove); window.removeEventListener("mouseup", onUp); };
  }, [isDragging]);

  // Open full IDE in a new tab
  const handleFullscreen = () => {
    try {
      // sessionStorage is per-browsing-context. The new tab must share the
      // same origin context — do NOT use "noopener" which severs that link.
      sessionStorage.setItem(
        "__app_preview__",
        JSON.stringify({ files, projectName })
      );
      window.open("/preview-fullscreen", "_blank");
    } catch (e) {
      // sessionStorage quota exceeded (files too large) — open with a flag
      // and let the fullscreen page show a graceful message.
      console.warn("sessionStorage write failed, files may be too large:", e);
      window.open("/preview-fullscreen?error=quota", "_blank");
    }
  };

  // Download ZIP
  const handleDownloadZip = async () => {
    setIsZipping(true);
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      if (!(window as any).JSZip) {
        await new Promise<void>((resolve, reject) => {
          const s = document.createElement("script");
          s.src = "https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js";
          s.onload = () => resolve();
          s.onerror = reject;
          document.head.appendChild(s);
        });
      }
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const JSZip = (window as any).JSZip;
      const zip = new JSZip();
      files.forEach(f => zip.file(f.path, f.content));
      const blob = await zip.generateAsync({ type: "blob" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${projectName.replace(/[^a-zA-Z0-9]/g, "-").toLowerCase()}.zip`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      alert("Failed to generate ZIP. Please try downloading files individually.");
    } finally {
      setIsZipping(false);
    }
  };

  if (files.length === 0) {
    return (
      <div className="flex items-center justify-center h-full bg-surface-warm">
        <div className="text-center">
          <Code2 className="h-10 w-10 text-ink-300 mx-auto mb-3" />
          <p className="text-[12px] text-ink-400">No files generated yet</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full bg-surface-warm overflow-hidden">
      {/* Top bar */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-line-control bg-surface-white flex-shrink-0">
        <div className="flex items-center gap-2">
          <Code2 className="h-4 w-4 text-brand" />
          <span className="text-[12px] font-semibold text-ink-900">{projectName}</span>
          <span className="text-[10px] text-ink-400 bg-line-faint-row px-1.5 py-0.5 rounded font-medium">{files.length} files</span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleFullscreen}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-surface-white hover:bg-surface-warm border border-line-control text-[11px] font-medium text-ink-600 hover:text-ink-900 transition-colors"
            title="Open in full screen (new tab)"
          >
            <Maximize2 className="h-3.5 w-3.5" />
            Full Screen
          </button>
          <button
            onClick={handleDownloadZip}
            disabled={isZipping}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-brand hover:bg-brand-pressed text-[11px] font-semibold text-white transition-colors disabled:opacity-50 shadow-sm"
          >
            {isZipping
              ? <><span className="h-3 w-3 border border-white/40 border-t-white rounded-full animate-spin" />Zipping...</>
              : <><FolderDown className="h-3.5 w-3.5" />Download ZIP</>
            }
          </button>
        </div>
      </div>

      {/* Main layout */}
      <div className="flex flex-1 min-h-0 overflow-hidden">
        {/* Sidebar */}
        <div
          className="flex flex-col bg-surface-white border-r border-line-control flex-shrink-0 overflow-hidden"
          style={{ width: `${sidebarWidth}px` }}
        >
          {/* Search */}
          <div className="px-3 py-2 border-b border-line-divider">
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3 w-3 text-ink-400" />
              <input
                aria-label="Search files"
                name="file-search"
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                placeholder="Search files..."
                className="w-full pl-7 pr-2 py-1.5 text-[11px] bg-surface-warm border border-line-control rounded-lg text-ink-700 placeholder-ink-400 focus:outline-none focus:border-brand transition-colors"
              />
            </div>
          </div>

          {/* Explorer header */}
          <div className="px-3 py-2 flex items-center justify-between border-b border-line-divider">
            <span className="text-[9px] font-semibold text-ink-400 uppercase tracking-wider">Explorer</span>
            <button
              onClick={() => {
                const allPaths = new Set<string>();
                files.forEach(f => {
                  const parts = f.path.split("/");
                  for (let i = 1; i < parts.length; i++) allPaths.add(parts.slice(0, i).join("/"));
                });
                setExpandedPaths(prev => prev.size === allPaths.size ? new Set() : allPaths);
              }}
              className="text-[9px] text-ink-400 hover:text-ink-600 transition-colors font-medium"
            >
              {expandedPaths.size > 0 ? "Collapse all" : "Expand all"}
            </button>
          </div>

          {/* File tree */}
          <div className="flex-1 overflow-y-auto py-1">
            {searchQuery && visibleFiles.length === 0 ? (
              <p className="px-3 py-2 text-[11px] text-ink-400">No files match your search</p>
            ) : tree.map(node => (
              <FileTreeNode
                key={node.path}
                node={node}
                depth={0}
                activeFile={activeFile?.path || null}
                onSelect={handleSelectFile}
                expandedPaths={expandedPaths}
                onToggle={handleToggleFolder}
                searchQuery={searchQuery}
              />
            ))}
          </div>

          {/* Footer stats */}
          <div className="px-3 py-2 border-t border-line-divider bg-surface-warm">
            <p className="text-[9px] text-ink-400">
              {visibleFiles.length} files · {(visibleFiles.reduce((s, f) => s + utf8Bytes(f.content), 0) / 1024).toFixed(1)} KB total
            </p>
          </div>
        </div>

        {/* Resize handle */}
        <div
          onMouseDown={handleMouseDown}
          className="w-[3px] bg-line-control hover:bg-brand cursor-col-resize flex-shrink-0 transition-colors"
        />

        {/* Editor area */}
        <div className="flex-1 flex flex-col min-w-0 overflow-hidden bg-surface-white">
          {/* Tab bar */}
          {openTabs.length > 0 && (
            <div className="flex items-end bg-surface-warm border-b border-line-control overflow-x-auto flex-shrink-0" style={{ scrollbarWidth: "none" }}>
              {openTabs.map(tab => {
                const isActive = activeFile?.path === tab.path;
                const file = files.find(f => f.path === tab.path);
                const Icon = getFileIcon(file?.ext || "");
                return (
                  <button
                    key={tab.path}
                    onClick={() => { const f = files.find(f => f.path === tab.path); if (f) setActiveFile(f); }}
                    className={`flex items-center gap-1.5 px-3 py-2 text-[11px] border-r border-line-control flex-shrink-0 group transition-all ${
                      isActive
                        ? "bg-surface-white text-ink-900 font-medium border-t-2 border-t-brand -mb-px"
                        : "bg-surface-warm text-ink-500 hover:text-ink-700 border-t-2 border-t-transparent"
                    }`}
                  >
                    <Icon className={`h-3 w-3 flex-shrink-0 ${isActive ? "text-brand" : "text-ink-400"}`} />
                    <span className="max-w-[120px] truncate">{tab.name}</span>
                    <span
                      onClick={e => handleCloseTab(tab.path, e)}
                      className="ml-1 opacity-0 group-hover:opacity-100 hover:text-ink-900 transition-opacity cursor-pointer"
                    >
                      <X className="h-2.5 w-2.5" />
                    </span>
                  </button>
                );
              })}
            </div>
          )}

          {/* Code viewer */}
          <CodeViewer file={activeFile} />
        </div>
      </div>

      {/* Revision bar */}
      {onRevise && (
        <div className="flex-shrink-0 border-t border-line-control bg-surface-white px-4 py-3 flex items-center gap-3">
          <input
            type="text"
            aria-label="Revision instructions"
            name="app-revision"
            value={revisionText}
            onChange={e => setRevisionText(e.target.value)}
            onKeyDown={e => {
              if (e.key === "Enter" && revisionText.trim()) {
                onRevise(revisionText.trim());
                setRevisionText("");
              }
            }}
            placeholder='Request changes, e.g. "Add authentication middleware" or "Switch to PostgreSQL"'
            className="flex-1 text-[12px] bg-surface-warm border border-line-control rounded-lg px-3 py-2 text-ink-700 placeholder-ink-400 focus:outline-none focus:border-brand transition-colors"
          />
          <button
            onClick={() => { if (revisionText.trim()) { onRevise(revisionText.trim()); setRevisionText(""); } }}
            disabled={!revisionText.trim()}
            className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-brand hover:bg-brand-pressed text-[11px] font-semibold text-white transition-colors disabled:opacity-40 flex-shrink-0"
          >
            <RefreshCw className="h-3.5 w-3.5" /> Revise
          </button>
        </div>
      )}
    </div>
  );
}
