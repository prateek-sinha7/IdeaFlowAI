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
import { exportToPptx } from "@/lib/exporters/pptExporter";
import { exportPrototype } from "@/lib/exporters/prototypeExporter";
import { parsePPTSlideData } from "@/lib/parsers/pptParser";
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
    // Derive filename from first slide title
    let pptName = "presentation";
    try {
      const parsed = JSON.parse(pptContent.trim().startsWith("{") ? pptContent : pptContent.slice(pptContent.indexOf("{")));
      if (parsed?.slides?.[0]?.title) {
        pptName = parsed.slides[0].title.replace(/[^a-zA-Z0-9\s]/g, "").trim().replace(/\s+/g, "-").toLowerCase().slice(0, 40);
      }
    } catch { /* use default */ }

    files.push({
      id: "presentation-pptx",
      name: `${pptName}.pptx`,
      type: "PowerPoint",
      icon: Presentation,
      iconColor: "text-amber-400",
      size: formatSize(pptContent.length * 2),
      format: "PowerPoint (.pptx)",
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
    } else if (fileId === "presentation-pptx" && pptContent) {
      try {
        const slideData = parsePPTSlideData(pptContent);
        // Derive filename from first slide title
        let pptName = "presentation";
        if (slideData.slides?.[0]?.title) {
          pptName = slideData.slides[0].title.replace(/[^a-zA-Z0-9\s]/g, "").trim().replace(/\s+/g, "-").toLowerCase().slice(0, 40);
        }
        exportToPptx(slideData, pptName);
      } catch (e) {
        alert("Failed to generate PPTX: " + (e instanceof Error ? e.message : "Unknown error"));
      }
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
          <p className="text-sm text-[#87867f]">No files available</p>
          <p className="text-[11px] text-[#87867f] mt-1">Run a workflow to generate downloadable files</p>
        </div>
      </div>
    );
  }

  return (
    <div className="px-5 py-4 h-full overflow-y-auto">
      <div className="flex items-center justify-between mb-4">
        <span className="text-[11px] text-[#87867f] font-medium">{files.length} files available</span>
        <motion.button
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.97 }}
          onClick={handleDownloadAll}
          className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[10px] font-medium text-[#141413] bg-[#f0eee6] hover:bg-[#e8e6dc] border border-[#e8e6dc] transition-all"
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
              className="flex items-center gap-3 rounded-xl border border-[#e8e6dc] bg-white hover:bg-[#faf9f5] hover:border-[#c96442]/20 px-4 py-3 transition-all"
            >
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-[#faf9f5] border border-[#e8e6dc] flex-shrink-0">
                <Icon className={`h-5 w-5 ${file.iconColor}`} />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-xs font-medium text-[#141413]">{file.name}</p>
                <p className="text-[10px] text-[#87867f] mt-0.5">{file.format} • {file.size}</p>
              </div>
              <motion.button
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                onClick={() => handleDownload(file.id)}
                className="flex items-center justify-center rounded-lg p-2 text-[#87867f] hover:text-[#141413] hover:bg-[#f0eee6] border border-[#e8e6dc] transition-all"
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
