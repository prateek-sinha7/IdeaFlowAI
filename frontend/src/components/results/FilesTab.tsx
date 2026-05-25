"use client";

import { useCallback, useMemo, useState } from "react";
import { motion } from "motion/react";
import {
  Download, FileText, Presentation, Layout, Code, Package,
  BookOpen, Settings, Shield, Palette, Database, TestTube,
  GitBranch, Server, FileCode,
} from "lucide-react";
import { exportUserStories } from "@/lib/exporters/storyExporter";
import { ENV } from "@/lib/env";
import type { WorkflowType } from "@/types/index";

interface FilesTabProps {
  workflowType: WorkflowType;
  userStoryContent?: string;
  pptContent?: string;
  prototypeContent?: string;
  // Per-agent outputs: each agent's full text becomes a downloadable .md.
  // For live runs the parent derives this from pipelineState.agents (only
  // entries with non-empty output should be passed). For history runs the
  // parent passes WorkflowRun.agentOutputs which the API already returns.
  agentOutputs?: AgentOutputItem[];
}

export interface AgentOutputItem {
  name: string;
  role?: string;
  output: string;
  agentId?: string;
}

interface FileItem {
  id: string;
  name: string;
  type: string;
  icon: typeof FileText;
  size: string;
  format: string;
  content: string;
  mimeType: string;
}

// ─── Agent ID → documentation metadata ───────────────────────────────────────
// Maps each app_builder agent to a human-readable doc name and icon.
// Agents that produce code files (code-generator, infra-generator, feature-impl,
// test-impl) are handled separately — their ```filename: ... ``` blocks are
// parsed into individual code files.
const APP_BUILDER_DOC_META: Record<string, { label: string; filename: string; icon: typeof FileText }> = {
  "material-analyzer":        { label: "Architecture Overview",      filename: "01-architecture.md",          icon: BookOpen },
  "app-user-stories":         { label: "User Stories & Epics",       filename: "02-user-stories.md",          icon: FileText },
  "app-system-design":        { label: "System Design & ADRs",       filename: "03-system-design.md",         icon: Settings },
  "app-security-architecture":{ label: "Security Architecture",      filename: "04-security-architecture.md", icon: Shield },
  "app-ux-design":            { label: "UX & UI Design",             filename: "05-ux-design.md",             icon: Palette },
  "app-api-design":           { label: "API Contracts (OpenAPI)",    filename: "06-api-contracts.md",         icon: FileCode },
  "app-database-design":      { label: "Data Model & Migrations",    filename: "07-database-design.md",       icon: Database },
  "app-code-compliance":      { label: "Code Compliance & SAST",     filename: "11-code-compliance.md",       icon: Shield },
  "app-test-compliance":      { label: "Test Strategy & Coverage",   filename: "13-test-compliance.md",       icon: TestTube },
  "app-devops":               { label: "DevOps & CI/CD Pipeline",    filename: "14-devops.md",                icon: GitBranch },
  "app-sdlc-governance":      { label: "SDLC Governance & Runbooks", filename: "15-governance.md",            icon: BookOpen },
};

// Agents whose output contains ```filename: ... ``` code blocks to parse
const CODE_PRODUCING_AGENTS = new Set([
  "app-code-generator",
  "app-feature-implementation",
  "app-infra-generator",
  "app-test-implementation",
]);

// ─── Parse ```filename: path ``` blocks from markdown ────────────────────────
// Also handles ### path/to/file + fenced block format used by some agents.
function parseCodeFiles(markdown: string): FileItem[] {
  const files: FileItem[] = [];
  const seen = new Set<string>();

  const mimeMap: Record<string, string> = {
    ts: "text/typescript", tsx: "text/typescript", js: "text/javascript",
    jsx: "text/javascript", py: "text/x-python", json: "application/json",
    md: "text/markdown", yml: "text/yaml", yaml: "text/yaml",
    env: "text/plain", txt: "text/plain", sh: "text/x-sh",
    dockerfile: "text/plain", css: "text/css", html: "text/html",
    sql: "text/x-sql", prisma: "text/plain", toml: "text/plain",
    java: "text/x-java", cs: "text/x-csharp", rb: "text/x-ruby",
    go: "text/x-go", rs: "text/x-rust", kt: "text/x-kotlin",
  };
  const iconMap: Record<string, typeof FileText> = {
    ts: Code, tsx: Code, js: Code, jsx: Code, py: Code,
    json: FileText, md: FileText, yml: Settings, yaml: Settings,
    dockerfile: Server, sh: Code, css: Code, html: Layout,
    sql: Database, java: Code, cs: Code, rb: Code, go: Code,
    rs: Code, kt: Code,
  };

  const addFile = (filePath: string, content: string) => {
    filePath = filePath.trim();
    if (!filePath || !content.trim() || seen.has(filePath)) return;
    const name = filePath.split("/").pop() || filePath;
    const hasDot = name.includes(".");
    const isKnownExtensionless = /^(Dockerfile|Makefile|Procfile|Gemfile|Rakefile)$/i.test(name);
    if (!hasDot && !isKnownExtensionless) return;
    seen.add(filePath);
    const ext = name.includes(".") ? name.split(".").pop()?.toLowerCase() || "txt" : "txt";
    files.push({
      id: `file-${files.length}-${filePath.replace(/[^a-z0-9]/gi, "-")}`,
      name,
      type: filePath,
      icon: iconMap[ext] || FileText,
      size: formatSize(content.length),
      format: ext.toUpperCase(),
      content,
      mimeType: mimeMap[ext] || "text/plain",
    });
  };

  // Format 1: ```filename: path/to/file.ext\n[content]\n```
  const filenameRegex = /```(?:filename:\s*([^\n]+)\n)([\s\S]*?)```/g;
  let m: RegExpExecArray | null;
  while ((m = filenameRegex.exec(markdown)) !== null) addFile(m[1], m[2]);

  // Format 2: ### path/to/file.ext\n```[lang]\n[content]\n```
  const headerRegex = /###\s+([\w./\-@][^\n]*\.\w+)\s*\n```[^\n]*\n([\s\S]*?)```/g;
  while ((m = headerRegex.exec(markdown)) !== null) addFile(m[1], m[2]);

  // Format 3: **`path/to/file.ext`** followed by ```
  const boldRegex = /\*\*`?([\w./\-@][^\n`*]*\.\w+)`?\*\*\s*\n```[^\n]*\n([\s\S]*?)```/g;
  while ((m = boldRegex.exec(markdown)) !== null) addFile(m[1], m[2]);

  return files;
}

// ─── Same parser used by AppBuilderPreview (alias) ───────────────────────────
function parseAppBuilderFiles(markdown: string): FileItem[] {
  return parseCodeFiles(markdown);
}

// ─── SectionHeader — defined outside FilesTab to avoid "component created during render" lint error ──
function SectionHeader({ label, count }: { label: string; count: number }) {
  return (
    <div className="flex items-center justify-between mb-2 mt-5 first:mt-0">
      <p className="text-[10px] uppercase tracking-wider text-gray-400 font-semibold">{label}</p>
      <span className="text-[9px] text-gray-400 bg-gray-100 px-1.5 py-0.5 rounded font-medium">{count}</span>
    </div>
  );
}

export function FilesTab({ workflowType, userStoryContent, pptContent, prototypeContent, agentOutputs }: FilesTabProps) {
  const [downloadingId, setDownloadingId] = useState<string | null>(null);

  // ── App Builder: split agent outputs into docs + code files (memoized) ───
  const { appBuilderDocFiles, appBuilderCodeFiles } = useMemo(() => {
    const docFiles: FileItem[] = [];
    const codeFiles: FileItem[] = [];
    if ((workflowType === "app_builder" || workflowType === "app_builder_revision") && agentOutputs) {
      for (const agent of agentOutputs) {
        if (!agent.output?.trim()) continue;
        const agentId = agent.agentId || "";
        if (CODE_PRODUCING_AGENTS.has(agentId)) {
          codeFiles.push(...parseCodeFiles(agent.output));
        } else {
          const meta = agentId ? APP_BUILDER_DOC_META[agentId] : undefined;
          const slug = (agent.name || "agent").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 50);
          const idx = String((agentOutputs.indexOf(agent) + 1)).padStart(2, "0");
          docFiles.push({
            id: `doc-${agentId || slug}`,
            name: meta?.filename || `${idx}-${slug}.md`,
            type: agent.role || agent.name,
            icon: meta?.icon || FileText,
            size: formatSize(agent.output.length),
            format: "Markdown (.md)",
            content: agent.output,
            mimeType: "text/markdown",
          });
        }
      }
    }
    return { appBuilderDocFiles: docFiles, appBuilderCodeFiles: codeFiles };
  }, [workflowType, agentOutputs]);

  // ── Generic agent files for non-app-builder pipelines (memoized) ─────────
  const genericAgentFiles = useMemo<FileItem[]>(() => {
    if (workflowType === "app_builder" || workflowType === "app_builder_revision") return [];
    return (agentOutputs ?? [])
      .filter(a => a.output?.trim())
      .map((a, i) => {
        const slug = (a.name || "agent").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 60);
        const idx = String(i + 1).padStart(2, "0");
        return {
          id: `agent-${a.agentId || slug}`,
          name: `${idx}-${slug}.md`,
          type: a.role || "Agent output",
          icon: FileText,
          size: formatSize(a.output.length),
          format: "Markdown (.md)",
          content: a.output,
          mimeType: "text/markdown",
        };
      });
  }, [workflowType, agentOutputs]);

  const files: FileItem[] = [];

  // ── User Stories ──────────────────────────────────────────────────────────
  if ((workflowType === "user_stories" || workflowType === "user_stories_revision") && userStoryContent) {
    let name = "user-stories";
    const h = userStoryContent.match(/^#\s+(.+)/m);
    if (h) name = h[1].replace(/[^a-zA-Z0-9\s]/g, "").trim().replace(/\s+/g, "-").toLowerCase().slice(0, 40);
    files.push({ id: "user-stories-md", name: `${name}.md`, type: "Markdown", icon: FileText, size: formatSize(userStoryContent.length), format: "Markdown (.md)", content: userStoryContent, mimeType: "text/markdown" });
  }

  // ── App Builder final output: ZIP of all code files ───────────────────────
  if ((workflowType === "app_builder" || workflowType === "app_builder_revision") && userStoryContent) {
    // Also parse the final compiled output for any code files not caught by agent outputs
    const finalCodeFiles = parseAppBuilderFiles(userStoryContent);
    // Merge with agent-parsed code files (deduplicate by path)
    const allCodePaths = new Set(appBuilderCodeFiles.map(f => f.type));
    for (const f of finalCodeFiles) {
      if (!allCodePaths.has(f.type)) {
        appBuilderCodeFiles.push(f);
        allCodePaths.add(f.type);
      }
    }

    if (appBuilderCodeFiles.length > 0) {
      // ZIP download at top
      files.unshift({
        id: "project-zip",
        name: "project.zip",
        type: `All ${appBuilderCodeFiles.length} code files (ZIP)`,
        icon: Package,
        size: `${appBuilderCodeFiles.length} files`,
        format: "ZIP Archive",
        content: userStoryContent,
        mimeType: "application/zip",
      });
    } else {
      // Fallback: single markdown download
      let name = "app-blueprint";
      const h = userStoryContent.match(/^#\s+(.+)/m);
      if (h) name = h[1].replace(/[^a-zA-Z0-9\s]/g, "").trim().replace(/\s+/g, "-").toLowerCase().slice(0, 40);
      files.push({ id: "project-md", name: `${name}.md`, type: "Markdown", icon: FileText, size: formatSize(userStoryContent.length), format: "Markdown (.md)", content: userStoryContent, mimeType: "text/markdown" });
    }
  }

  // ── Custom ────────────────────────────────────────────────────────────────
  if (workflowType === "custom" && userStoryContent) {
    let name = "custom-output";
    const h = userStoryContent.match(/^#\s+(.+)/m);
    if (h) name = h[1].replace(/[^a-zA-Z0-9\s]/g, "").trim().replace(/\s+/g, "-").toLowerCase().slice(0, 40);
    files.push({ id: "custom-md", name: `${name}.md`, type: "Markdown", icon: FileText, size: formatSize(userStoryContent.length), format: "Markdown (.md)", content: userStoryContent, mimeType: "text/markdown" });
  }

  // ── PPT ───────────────────────────────────────────────────────────────────
  if ((workflowType === "ppt" || workflowType === "ppt_revision") && pptContent) {
    let name = "presentation";
    const t = pptContent.match(/<title>([^<]+)<\/title>/i);
    const h1 = pptContent.match(/<h1[^>]*>([^<]+)<\/h1>/i);
    if (t && t[1] !== "Presentation") name = t[1].replace(/[^a-zA-Z0-9\s]/g, "").trim().replace(/\s+/g, "-").toLowerCase().slice(0, 40);
    else if (h1) name = h1[1].replace(/[^a-zA-Z0-9\s]/g, "").trim().replace(/\s+/g, "-").toLowerCase().slice(0, 40);
    files.push({ id: "presentation-pptx", name: `${name}.pptx`, type: "PowerPoint", icon: Presentation, size: "~", format: "PowerPoint (.pptx)", content: pptContent, mimeType: "application/vnd.openxmlformats-officedocument.presentationml.presentation" });
    files.push({ id: "presentation-html", name: `${name}.html`, type: "HTML Presentation", icon: Presentation, size: formatSize(pptContent.length), format: "HTML (.html) — open in browser", content: pptContent, mimeType: "text/html" });
  }

  // ── Prototype ─────────────────────────────────────────────────────────────
  if ((workflowType === "prototype" || workflowType === "prototype_revision" || workflowType === "od_prototype") && prototypeContent) {
    let name = "prototype";
    const t = prototypeContent.match(/<title>(.+?)<\/title>/i);
    if (t) name = t[1].replace(/[^a-zA-Z0-9\s]/g, "").trim().replace(/\s+/g, "-").toLowerCase().slice(0, 40);
    files.push({ id: "prototype-html", name: `${name}.html`, type: "HTML Prototype", icon: Layout, size: formatSize(prototypeContent.length), format: "HTML (.html)", content: prototypeContent, mimeType: "text/html" });
  }

  const handleDownload = useCallback(async (file: FileItem) => {
    if (file.id === "user-stories-md" && userStoryContent) {
      exportUserStories(userStoryContent, file.name.replace(".md", ""));
    } else if (file.id === "project-zip" && userStoryContent) {
      setDownloadingId(file.id);
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
        // Include all code files from agent outputs
        const allCode = parseAppBuilderFiles(userStoryContent);
        const seen = new Set<string>();
        for (const f of [...appBuilderCodeFiles, ...allCode]) {
          if (!seen.has(f.type)) { zip.file(f.type, f.content); seen.add(f.type); }
        }
        // Also include doc files as docs/ folder
        for (const d of appBuilderDocFiles) {
          zip.file(`docs/${d.name}`, d.content);
        }
        const blob = await zip.generateAsync({ type: "blob" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = "project.zip";
        a.click();
        URL.revokeObjectURL(url);
      } catch {
        alert("Failed to generate ZIP.");
      } finally {
        setDownloadingId(null);
      }
    } else if (file.id === "presentation-pptx" && pptContent) {
      setDownloadingId(file.id);
      try {
        const { getToken } = await import("@/lib/api");
        const token = getToken();
        const title = file.name.replace(".pptx", "").replace(/-/g, " ");
        let workflowId = "";
        try {
          const res = await fetch(`${ENV.API_URL}/api/workflows?type=ppt&limit=20`, {
            headers: { "Authorization": `Bearer ${token}` },
          });
          if (res.ok) {
            const runs = await res.json();
            const h1 = pptContent.match(/<h1[^>]*>([^<]+)<\/h1>/i);
            if (h1) {
              const match = runs.find((r: { output?: string }) => r.output?.includes(h1[1]));
              if (match) workflowId = match.id;
            }
            if (!workflowId && runs.length > 0) workflowId = runs[0].id;
          }
        } catch {}
        const response = await fetch(`${ENV.API_URL}/api/workflows/export-pptx`, {
          method: "POST",
          headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}` },
          body: JSON.stringify({ html: pptContent, workflow_id: workflowId, title }),
        });
        if (response.ok) {
          const blob = await response.blob();
          downloadBlob(URL.createObjectURL(blob), file.name, "");
        } else {
          alert("PPTX export failed. Try the Download PPTX button in the preview.");
        }
      } catch {
        alert("PPTX export failed.");
      } finally {
        setDownloadingId(null);
      }
    } else {
      downloadBlob(file.content, file.name, file.mimeType);
    }
  }, [userStoryContent, pptContent, appBuilderCodeFiles, appBuilderDocFiles]);

  const isAppBuilder = workflowType === "app_builder" || workflowType === "app_builder_revision";
  const totalCount = files.length + appBuilderDocFiles.length + appBuilderCodeFiles.length + genericAgentFiles.length;

  if (totalCount === 0) {
    return (
      <div className="flex items-center justify-center h-full px-6">
        <div className="text-center">
          <p className="text-sm text-gray-400">No files available</p>
          <p className="text-[11px] text-gray-400 mt-1">Run a workflow to generate downloadable files</p>
        </div>
      </div>
    );
  }

  const renderFileRow = (file: FileItem, idx: number) => {
    const Icon = file.icon;
    return (
      <motion.div
        key={file.id}
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: idx * 0.03 }}
        className="flex items-center gap-3 rounded-xl border border-gray-200 bg-white px-4 py-3 hover:border-gray-300 hover:shadow-sm transition-all"
      >
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gray-100 border border-gray-200 flex-shrink-0">
          <Icon className="h-4 w-4 text-gray-500" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-[12px] font-semibold text-gray-900 truncate">{file.name}</p>
          <p className="text-[10px] text-gray-400 mt-0.5 truncate">
            {file.type !== file.name ? `${file.type} · ` : ""}{file.size}
          </p>
        </div>
        <button
          onClick={() => handleDownload(file)}
          disabled={downloadingId === file.id}
          className="flex items-center justify-center rounded-lg p-2 text-gray-400 hover:text-gray-700 hover:bg-gray-100 border border-gray-200 transition-all flex-shrink-0 disabled:opacity-50"
          title={`Download ${file.name}`}
        >
          {downloadingId === file.id
            ? <span className="h-3.5 w-3.5 border-2 border-gray-400 border-t-transparent rounded-full animate-spin" />
            : <Download className="h-3.5 w-3.5" />
          }
        </button>
      </motion.div>
    );
  };

  return (
    <div className="px-5 py-4 h-full overflow-y-auto" style={{ background: "#f5f5f0" }}>
      {/* Header row */}
      <div className="flex items-center justify-between mb-4">
        <span className="text-[11px] text-gray-500 font-medium">{totalCount} file{totalCount !== 1 ? "s" : ""} available</span>
        <button
          onClick={() => {
            const all = [...files, ...(isAppBuilder ? appBuilderDocFiles : []), ...(isAppBuilder ? appBuilderCodeFiles : genericAgentFiles)];
            all.forEach((file, i) => setTimeout(() => handleDownload(file), i * 150));
          }}
          className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[10px] font-medium text-gray-700 bg-white hover:bg-gray-50 border border-gray-200 transition-all"
        >
          <Download className="h-3 w-3" />
          Download All
        </button>
      </div>

      {/* ── App Builder layout ─────────────────────────────────────────────── */}
      {isAppBuilder ? (
        <>
          {/* ZIP + final output files */}
          {files.length > 0 && (
            <>
              <SectionHeader label="Project Download" count={files.length} />
              <div className="space-y-2">{files.map((f, i) => renderFileRow(f, i))}</div>
            </>
          )}

          {/* Code files from code-producing agents */}
          {appBuilderCodeFiles.length > 0 && (
            <>
              <SectionHeader label="Source Code Files" count={appBuilderCodeFiles.length} />
              <p className="text-[10px] text-gray-400 mb-2">
                Generated code files — frontend, backend, tests, config, and infrastructure.
              </p>
              <div className="space-y-2">
                {appBuilderCodeFiles.map((f, i) => renderFileRow(f, files.length + i))}
              </div>
            </>
          )}

          {/* Agent outputs (.md) from design/analysis agents — same style as other pipelines */}
          {appBuilderDocFiles.length > 0 && (
            <>
              <SectionHeader label={`Agent Outputs (${appBuilderDocFiles.length})`} count={appBuilderDocFiles.length} />
              <p className="text-[10px] text-gray-400 mb-2">
                Intermediate output from each agent in the pipeline. Each file contains the full output of one agent.
              </p>
              <div className="space-y-2">
                {appBuilderDocFiles.map((f, i) => renderFileRow(f, files.length + appBuilderCodeFiles.length + i))}
              </div>
            </>
          )}
        </>
      ) : (
        /* ── Non-app-builder layout ─────────────────────────────────────── */
        <>
          {files.length > 0 && (
            <>
              {genericAgentFiles.length > 0 && (
                <p className="text-[10px] uppercase tracking-wider text-gray-400 font-medium mb-2">Final output</p>
              )}
              <div className="space-y-2 mb-5">{files.map(renderFileRow)}</div>
            </>
          )}

          {genericAgentFiles.length > 0 && (
            <>
              <p className="text-[10px] uppercase tracking-wider text-gray-400 font-medium mb-2">
                Agent outputs ({genericAgentFiles.length})
              </p>
              <p className="text-[10px] text-gray-400 mb-3">
                Intermediate work-in-progress from each agent in the pipeline.
              </p>
              <div className="space-y-2">
                {genericAgentFiles.map((f, i) => renderFileRow(f, files.length + i))}
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1048576).toFixed(1)} MB`;
}

function downloadBlob(content: string, filename: string, mimeType: string) {
  let url: string;
  if (content.startsWith("blob:")) {
    url = content;
  } else {
    const blob = new Blob([content], { type: mimeType });
    url = URL.createObjectURL(blob);
  }
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  if (!content.startsWith("blob:")) URL.revokeObjectURL(url);
}
