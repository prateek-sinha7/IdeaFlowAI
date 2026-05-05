"use client";

import { useCallback } from "react";
import { motion } from "motion/react";
import {
  Download,
  FileText,
  Presentation,
  Layout,
  FileJson,
  File,
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
    files.push({
      id: "user-stories-md",
      name: "user-stories.md",
      type: "Markdown",
      icon: FileText,
      iconColor: "text-blue-400",
      size: formatSize(userStoryContent.length),
      format: "Markdown (.md)",
      available: true,
    });
    files.push({
      id: "user-stories-json",
      name: "user-stories.json",
      type: "JSON",
      icon: FileJson,
      iconColor: "text-yellow-400",
      size: formatSize(userStoryContent.length),
      format: "JSON (.json)",
      available: true,
    });
  }

  if (workflowType === "ppt" && pptContent) {
    files.push({
      id: "presentation-pptx",
      name: "presentation.pptx",
      type: "PowerPoint",
      icon: Presentation,
      iconColor: "text-amber-400",
      size: formatSize(pptContent.length * 2), // Approximate PPTX size
      format: "PowerPoint (.pptx)",
      available: true,
    });
    files.push({
      id: "presentation-json",
      name: "presentation.json",
      type: "JSON",
      icon: FileJson,
      iconColor: "text-yellow-400",
      size: formatSize(pptContent.length),
      format: "JSON (.json)",
      available: true,
    });
  }

  if (workflowType === "prototype" && prototypeContent) {
    files.push({
      id: "prototype-json",
      name: "prototype.json",
      type: "JSON",
      icon: Layout,
      iconColor: "text-emerald-400",
      size: formatSize(prototypeContent.length),
      format: "JSON (.json)",
      available: true,
    });
    files.push({
      id: "prototype-html",
      name: "prototype.html",
      type: "HTML Preview",
      icon: File,
      iconColor: "text-purple-400",
      size: formatSize(prototypeContent.length * 3),
      format: "HTML (.html)",
      available: true,
    });
  }

  const handleDownload = useCallback((fileId: string) => {
    if (fileId === "user-stories-md" && userStoryContent) {
      exportUserStories(userStoryContent);
    } else if (fileId === "user-stories-json" && userStoryContent) {
      downloadBlob(userStoryContent, "user-stories.json", "application/json");
    } else if (fileId === "presentation-pptx" && pptContent) {
      try {
        const slideData = parsePPTSlideData(pptContent);
        exportToPptx(slideData);
      } catch {
        downloadBlob(pptContent, "presentation.json", "application/json");
      }
    } else if (fileId === "presentation-json" && pptContent) {
      downloadBlob(pptContent, "presentation.json", "application/json");
    } else if (fileId === "prototype-json" && prototypeContent) {
      exportPrototype(prototypeContent);
    } else if (fileId === "prototype-html" && prototypeContent) {
      // Generate a simple HTML wrapper
      const html = `<!DOCTYPE html><html><head><meta charset="utf-8"><title>Prototype</title></head><body><pre>${prototypeContent}</pre></body></html>`;
      downloadBlob(html, "prototype.html", "text/html");
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
          <p className="text-sm text-grey/50">No files available</p>
          <p className="text-[11px] text-grey/35 mt-1">Run a workflow to generate downloadable files</p>
        </div>
      </div>
    );
  }

  return (
    <div className="px-5 py-4 h-full overflow-y-auto">
      <div className="flex items-center justify-between mb-4">
        <span className="text-[11px] text-grey/50 font-medium">{files.length} files available</span>
        <motion.button
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.97 }}
          onClick={handleDownloadAll}
          className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[10px] font-medium text-white bg-white/10 hover:bg-white/15 border border-white/10 transition-all"
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
              className="flex items-center gap-3 rounded-xl border border-grey/10 bg-white/[0.01] hover:bg-white/[0.03] hover:border-grey/20 px-4 py-3 transition-all"
            >
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-white/5 border border-white/10 flex-shrink-0">
                <Icon className={`h-5 w-5 ${file.iconColor}`} />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-xs font-medium text-white/90">{file.name}</p>
                <p className="text-[10px] text-grey/50 mt-0.5">{file.format} • {file.size}</p>
              </div>
              <motion.button
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                onClick={() => handleDownload(file.id)}
                className="flex items-center justify-center rounded-lg p-2 text-grey/50 hover:text-white hover:bg-white/10 border border-grey/15 transition-all"
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
