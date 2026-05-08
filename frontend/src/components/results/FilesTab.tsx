"use client";

import { useCallback } from "react";
import { motion } from "motion/react";
import {
  Download,
  FileText,
  Presentation,
  Layout,
} from "lucide-react";
import { exportUserStories } from "@/lib/exporters/storyExporter";
import type { WorkflowType } from "@/types/index";

interface FilesTabProps {
  workflowType: WorkflowType;
  userStoryContent?: string;
  pptContent?: string;
  prototypeContent?: string;
}

interface FileItem {
  id: string;
  name: string;
  type: string;
  icon: typeof FileText;
  iconColor: string;
  size: string;
  format: string;
  available: boolean;
}

/**
 * Files Tab — shows downloadable artifacts as file cards.
 */
export function FilesTab({ workflowType, userStoryContent, pptContent, prototypeContent }: FilesTabProps) {
  const files: FileItem[] = [];

  // Primary output file
  if (workflowType === "user_stories" && userStoryContent) {
    // Derive filename from first heading or first line
    let storyName = "user-stories";
    const firstHeading = userStoryContent.match(/^#\s+(.+)/m);
    if (firstHeading) {
      storyName = firstHeading[1].replace(/[^a-zA-Z0-9\s]/g, "").trim().replace(/\s+/g, "-").toLowerCase().slice(0, 40);
    }

    files.push({
      id: "user-stories-md",
      name: `${storyName}.md`,
      type: "Markdown",
      icon: FileText,
      iconColor: "text-blue-400",
      size: formatSize(userStoryContent.length),
      format: "Markdown (.md)",
      available: true,
    });
  }

  if ((workflowType === "app_builder" || workflowType === "reverse_engineer" || workflowType === "custom") && userStoryContent) {
    let docName = workflowType === "app_builder" ? "app-blueprint" : "codebase-analysis";
    const firstHeading = userStoryContent.match(/^#\s+(.+)/m);
    if (firstHeading) {
      docName = firstHeading[1].replace(/[^a-zA-Z0-9\s]/g, "").trim().replace(/\s+/g, "-").toLowerCase().slice(0, 40);
    }

    files.push({
      id: "project-md",
      name: `${docName}.md`,
      type: "Markdown",
      icon: FileText,
      iconColor: workflowType === "app_builder" ? "text-orange-400" : "text-rose-400",
      size: formatSize(userStoryContent.length),
      format: "Markdown (.md)",
      available: true,
    });
  }

  if (workflowType === "ppt" && pptContent) {
    // PPT is now an HTML slide deck — offer as HTML download
    // The PPTX download is built into the HTML itself (Download button in the presentation)
    let pptName = "presentation";
    const titleMatch = pptContent.match(/<title>(.+?)<\/title>/i);
    if (titleMatch) {
      pptName = titleMatch[1].replace(/[^a-zA-Z0-9\s]/g, "").trim().replace(/\s+/g, "-").toLowerCase().slice(0, 40);
    }

    files.push({
      id: "presentation-html",
      name: `${pptName}.html`,
      type: "HTML Presentation",
      icon: Presentation,
      iconColor: "text-amber-400",
      size: formatSize(pptContent.length),
      format: "HTML (.html) — Open in browser to view slides & download PPTX",
      available: true,
    });
  }

  if (workflowType === "prototype" && prototypeContent) {
    // Derive filename from content
    let protoName = "prototype";
    const titleMatch = prototypeContent.match(/<title>(.+?)<\/title>/i);
    if (titleMatch) {
      protoName = titleMatch[1].replace(/[^a-zA-Z0-9\s]/g, "").trim().replace(/\s+/g, "-").toLowerCase().slice(0, 40);
    }

    files.push({
      id: "prototype-html",
      name: `${protoName}.html`,
      type: "HTML",
      icon: Layout,
      iconColor: "text-emerald-400",
      size: formatSize(prototypeContent.length),
      format: "HTML (.html)",
      available: true,
    });
  }

  const handleDownload = useCallback((fileId: string) => {
    if (fileId === "user-stories-md" && userStoryContent) {
      // Derive filename from first heading
      let storyName = "user-stories";
      const firstHeading = userStoryContent.match(/^#\s+(.+)/m);
      if (firstHeading) {
        storyName = firstHeading[1].replace(/[^a-zA-Z0-9\s]/g, "").trim().replace(/\s+/g, "-").toLowerCase().slice(0, 40);
      }
      exportUserStories(userStoryContent, storyName);
    } else if (fileId === "project-md" && userStoryContent) {
      let docName = workflowType === "app_builder" ? "app-blueprint" : "codebase-analysis";
      const firstHeading = userStoryContent.match(/^#\s+(.+)/m);
      if (firstHeading) {
        docName = firstHeading[1].replace(/[^a-zA-Z0-9\s]/g, "").trim().replace(/\s+/g, "-").toLowerCase().slice(0, 40);
      }
      exportUserStories(userStoryContent, docName);
    } else if (fileId === "presentation-html" && pptContent) {
      let pptName = "presentation";
      const titleMatch = pptContent.match(/<title>(.+?)<\/title>/i);
      if (titleMatch) {
        pptName = titleMatch[1].replace(/[^a-zA-Z0-9\s]/g, "").trim().replace(/\s+/g, "-").toLowerCase().slice(0, 40);
      }
      downloadBlob(pptContent, `${pptName}.html`, "text/html");
    } else if (fileId === "prototype-html" && prototypeContent) {
      let protoName = "prototype";
      const titleMatch = prototypeContent.match(/<title>(.+?)<\/title>/i);
      if (titleMatch) {
        protoName = titleMatch[1].replace(/[^a-zA-Z0-9\s]/g, "").trim().replace(/\s+/g, "-").toLowerCase().slice(0, 40);
      }
      downloadBlob(prototypeContent, `${protoName}.html`, "text/html");
    }
  }, [userStoryContent, pptContent, prototypeContent]);

  const handleDownloadAll = useCallback(() => {
    // Download each available file
    files.forEach((file) => {
      if (file.available) {
        setTimeout(() => handleDownload(file.id), 100);
      }
    });
  }, [files, handleDownload]);

  if (files.length === 0) {
    return (
      <div className="flex items-center justify-center h-full px-6">
        <div className="text-center">
          <p className="text-sm text-gray-400">No files available</p>
          <p className="text-[11px] text-gray-400 mt-1">Run a workflow to generate downloadable files</p>
        </div>
      </div>
    );
  }

  return (
    <div className="px-5 py-4 h-full overflow-y-auto">
      <div className="flex items-center justify-between mb-4">
        <span className="text-[11px] text-gray-500 font-medium">{files.length} files available</span>
        <motion.button
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.97 }}
          onClick={handleDownloadAll}
          className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[10px] font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 border border-gray-200 transition-all"
        >
          <Download className="h-3 w-3" />
          Download All
        </motion.button>
      </div>

      <div className="space-y-2">
        {files.map((file, idx) => {
          const Icon = file.icon;
          return (
            <motion.div
              key={file.id}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: idx * 0.05 }}
              className="flex items-center gap-3 rounded-lg border border-gray-200 bg-white hover:bg-gray-50 hover:border-gray-300 px-4 py-3 transition-all"
            >
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-gray-100 border border-gray-200 flex-shrink-0">
                <Icon className={`h-5 w-5 ${file.iconColor}`} />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-xs font-medium text-gray-900">{file.name}</p>
                <p className="text-[10px] text-gray-500 mt-0.5">{file.format} • {file.size}</p>
              </div>
              <motion.button
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                onClick={() => handleDownload(file.id)}
                className="flex items-center justify-center rounded-lg p-2 text-gray-400 hover:text-gray-700 hover:bg-gray-100 border border-gray-200 transition-all"
                title={`Download ${file.name}`}
              >
                <Download className="h-4 w-4" />
              </motion.button>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1048576).toFixed(1)} MB`;
}

function downloadBlob(content: string, filename: string, mimeType: string) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
