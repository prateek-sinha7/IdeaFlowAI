"use client";

import { useCallback, useState } from "react";
import { motion } from "motion/react";
import { Download, FileText, Presentation, Layout, Code, Package } from "lucide-react";
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
  // Both share the same shape contract:
  //   { name, role?, output, agentId? }
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

// ─── App Builder: parse code files from markdown output ───────────────────────
// The App Builder agent outputs code blocks like:
//   ```filename: src/models/user.ts
//   [content]
//   ```
function parseAppBuilderFiles(markdown: string): FileItem[] {
  const files: FileItem[] = [];

  // Match ```filename: path/to/file.ext\n[content]\n```
  const codeBlockRegex = /```(?:filename:\s*([^\n]+)\n)([\s\S]*?)```/g;
  let match;

  while ((match = codeBlockRegex.exec(markdown)) !== null) {
    const filePath = match[1].trim();
    const content = match[2];
    if (!filePath || !content.trim()) continue;

    const ext = filePath.split(".").pop()?.toLowerCase() || "txt";
    const mimeMap: Record<string, string> = {
      ts: "text/typescript", tsx: "text/typescript", js: "text/javascript",
      jsx: "text/javascript", py: "text/x-python", json: "application/json",
      md: "text/markdown", yml: "text/yaml", yaml: "text/yaml",
      env: "text/plain", txt: "text/plain", sh: "text/x-sh",
      dockerfile: "text/plain", css: "text/css", html: "text/html",
      sql: "text/x-sql", prisma: "text/plain", toml: "text/plain",
    };

    const iconMap: Record<string, typeof FileText> = {
      ts: Code, tsx: Code, js: Code, jsx: Code, py: Code,
      json: FileText, md: FileText, yml: FileText, yaml: FileText,
      dockerfile: Package, sh: Code, css: Code, html: Layout,
    };

    files.push({
      id: `file-${files.length}-${filePath.replace(/[^a-z0-9]/gi, "-")}`,
      name: filePath.includes("/") ? filePath.split("/").pop()! : filePath,
      type: filePath,
      icon: iconMap[ext] || FileText,
      size: formatSize(content.length),
      format: ext.toUpperCase(),
      content,
      mimeType: mimeMap[ext] || "text/plain",
    });
  }

  return files;
}

export function FilesTab({ workflowType, userStoryContent, pptContent, prototypeContent, agentOutputs }: FilesTabProps) {
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const files: FileItem[] = [];

  // Build per-agent file entries (rendered separately from final-output files
  // so the user can see they're the work-in-progress, not the deliverable).
  // Only agents with non-empty output show up.
  const agentFiles: FileItem[] = (agentOutputs ?? [])
    .filter((a) => a.output && a.output.trim().length > 0)
    .map((a, i) => {
      const slug = (a.name || `agent-${i + 1}`)
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-|-$/g, "")
        .slice(0, 60);
      const idx = String(i + 1).padStart(2, "0");
      return {
        id: `agent-${a.agentId || slug}-${i}`,
        name: `${idx}-${slug}.md`,
        type: a.role || "Agent output",
        icon: FileText,
        size: formatSize(a.output.length),
        format: "Markdown (.md)",
        content: a.output,
        mimeType: "text/markdown",
      };
    });

  // ── User Stories (including revisions) ──────────────────────────────────
  if ((workflowType === "user_stories" || workflowType === "user_stories_revision") && userStoryContent) {
    let name = "user-stories";
    const h = userStoryContent.match(/^#\s+(.+)/m);
    if (h) name = h[1].replace(/[^a-zA-Z0-9\s]/g, "").trim().replace(/\s+/g, "-").toLowerCase().slice(0, 40);
    files.push({ id: "user-stories-md", name: `${name}.md`, type: "Markdown", icon: FileText, size: formatSize(userStoryContent.length), format: "Markdown (.md)", content: userStoryContent, mimeType: "text/markdown" });
  }

  // ── App Builder (including revisions) ────────────────────────────────────
  if ((workflowType === "app_builder" || workflowType === "app_builder_revision") && userStoryContent) {
    const projectFiles = parseAppBuilderFiles(userStoryContent);
    if (projectFiles.length > 0) {
      files.push(...projectFiles);
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

  // ── PPT (including revisions) ─────────────────────────────────────────────
  if ((workflowType === "ppt" || workflowType === "ppt_revision") && pptContent) {
    let name = "presentation";
    const t = pptContent.match(/<title>([^<]+)<\/title>/i);
    const h1 = pptContent.match(/<h1[^>]*>([^<]+)<\/h1>/i);
    if (t && t[1] !== "Presentation") name = t[1].replace(/[^a-zA-Z0-9\s]/g, "").trim().replace(/\s+/g, "-").toLowerCase().slice(0, 40);
    else if (h1) name = h1[1].replace(/[^a-zA-Z0-9\s]/g, "").trim().replace(/\s+/g, "-").toLowerCase().slice(0, 40);

    // PPTX download via server-side export
    files.push({ id: "presentation-pptx", name: `${name}.pptx`, type: "PowerPoint", icon: Presentation, size: "~", format: "PowerPoint (.pptx)", content: pptContent, mimeType: "application/vnd.openxmlformats-officedocument.presentationml.presentation" });
    // HTML fallback
    files.push({ id: "presentation-html", name: `${name}.html`, type: "HTML Presentation", icon: Presentation, size: formatSize(pptContent.length), format: "HTML (.html) — open in browser", content: pptContent, mimeType: "text/html" });
  }

  // ── Prototype (including revisions) ──────────────────────────────────────
  if ((workflowType === "prototype" || workflowType === "prototype_revision") && prototypeContent) {
    let name = "prototype";
    const t = prototypeContent.match(/<title>(.+?)<\/title>/i);
    if (t) name = t[1].replace(/[^a-zA-Z0-9\s]/g, "").trim().replace(/\s+/g, "-").toLowerCase().slice(0, 40);
    files.push({ id: "prototype-html", name: `${name}.html`, type: "HTML Prototype", icon: Layout, size: formatSize(prototypeContent.length), format: "HTML (.html)", content: prototypeContent, mimeType: "text/html" });
  }

  const handleDownload = useCallback(async (file: FileItem) => {
    if (file.id === "user-stories-md" && userStoryContent) {
      exportUserStories(userStoryContent, file.name.replace(".md", ""));
    } else if (file.id === "presentation-pptx" && pptContent) {
      // Server-side PPTX export
      setDownloadingId(file.id);
      try {
        const { getToken } = await import("@/lib/api");
        const token = getToken();
        // Get title from filename
        const title = file.name.replace(".pptx", "").replace(/-/g, " ");
        // Find matching workflow
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
      } catch (e) {
        alert("PPTX export failed.");
      } finally {
        setDownloadingId(null);
      }
    } else {
      downloadBlob(file.content, file.name, file.mimeType);
    }
  }, [userStoryContent, pptContent]);

  const totalCount = files.length + agentFiles.length;

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
          <p className="text-[10px] text-gray-400 mt-0.5 truncate">{file.type !== file.name ? file.type + " · " : ""}{file.size}</p>
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
      <div className="flex items-center justify-between mb-4">
        <span className="text-[11px] text-gray-500 font-medium">{totalCount} file{totalCount !== 1 ? "s" : ""} available</span>
        <button
          onClick={() => [...files, ...agentFiles].forEach((file, i) => setTimeout(() => handleDownload(file), i * 150))}
          className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[10px] font-medium text-gray-700 bg-white hover:bg-gray-50 border border-gray-200 transition-all"
        >
          <Download className="h-3 w-3" />
          Download All
        </button>
      </div>

      {files.length > 0 && (
        <>
          {agentFiles.length > 0 && (
            <p className="text-[10px] uppercase tracking-wider text-gray-400 font-medium mb-2">Final output</p>
          )}
          <div className="space-y-2 mb-5">{files.map(renderFileRow)}</div>
        </>
      )}

      {agentFiles.length > 0 && (
        <>
          <p className="text-[10px] uppercase tracking-wider text-gray-400 font-medium mb-2">
            Agent outputs ({agentFiles.length})
          </p>
          <p className="text-[10px] text-gray-400 mb-3">
            Intermediate work-in-progress from each agent in the pipeline. The final output above is the deliverable.
          </p>
          <div className="space-y-2">{agentFiles.map((f, i) => renderFileRow(f, files.length + i))}</div>
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
    url = content; // already a blob URL
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
