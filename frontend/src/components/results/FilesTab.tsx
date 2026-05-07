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
      id: "prototype-html",
      name: "prototype.html",
      type: "HTML",
      icon: Layout,
      iconColor: "text-emerald-400",
      size: formatSize(prototypeContent.length),
      format: "HTML (.html)",
      available: true,
    });
    files.push({
      id: "prototype-source",
      name: "prototype-source.txt",
      type: "Source",
      icon: File,
      iconColor: "text-purple-400",
      size: formatSize(prototypeContent.length),
      format: "Text (.txt)",
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
    } else if (fileId === "prototype-html" && prototypeContent) {
      downloadBlob(prototypeContent, "prototype.html", "text/html");
    } else if (fileId === "prototype-source" && prototypeContent) {
      downloadBlob(prototypeContent, "prototype-source.txt", "text/plain");
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
