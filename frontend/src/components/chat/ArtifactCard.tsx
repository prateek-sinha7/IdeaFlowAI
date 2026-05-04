"use client";

import { useState, useCallback } from "react";
import { motion } from "motion/react";
import {
  FileText,
  Presentation,
  Layout,
  Copy,
  Check,
  Download,
} from "lucide-react";
import { exportToPptx } from "@/lib/exporters/pptExporter";
import { exportPrototype } from "@/lib/exporters/prototypeExporter";
import { parsePPTSlideData } from "@/lib/parsers/pptParser";

interface ArtifactCardProps {
  type: "user-stories" | "ppt" | "prototype";
  filename: string;
  content: string;
  summary: string;
  onOpenPreview?: () => void;
}

const TYPE_CONFIG = {
  "user-stories": {
    icon: FileText,
    badge: ".md",
    badgeColor: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
    iconColor: "text-emerald-400",
  },
  ppt: {
    icon: Presentation,
    badge: ".pptx",
    badgeColor: "bg-blue-500/20 text-blue-400 border-blue-500/30",
    iconColor: "text-blue-400",
  },
  prototype: {
    icon: Layout,
    badge: ".json",
    badgeColor: "bg-purple-500/20 text-purple-400 border-purple-500/30",
    iconColor: "text-purple-400",
  },
} as const;

/**
 * Claude-inspired inline artifact card for generated content.
 * Shows file icon, filename, type badge, and copy/download actions.
 */
export function ArtifactCard({
  type,
  filename,
  content,
  summary,
  onOpenPreview,
}: ArtifactCardProps) {
  const [copied, setCopied] = useState(false);

  const config = TYPE_CONFIG[type];
  const Icon = config.icon;

  const handleCopy = useCallback(
    async (e: React.MouseEvent) => {
      e.stopPropagation();
      try {
        await navigator.clipboard.writeText(content);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      } catch (err) {
        console.error("Failed to copy artifact:", err);
      }
    },
    [content]
  );

  const handleDownload = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      try {
        if (type === "ppt") {
          const slideData = parsePPTSlideData(content);
          exportToPptx(slideData, filename.replace(/\.pptx$/, ""));
        } else if (type === "prototype") {
          exportPrototype(content, filename.replace(/\.json$/, ""));
        } else {
          // User stories — download as .md
          const blob = new Blob([content], {
            type: "text/markdown;charset=utf-8",
          });
          const url = URL.createObjectURL(blob);
          const link = document.createElement("a");
          link.href = url;
          link.download = filename;
          document.body.appendChild(link);
          link.click();
          document.body.removeChild(link);
          URL.revokeObjectURL(url);
        }
      } catch (err) {
        console.error("Failed to download artifact:", err);
      }
    },
    [type, content, filename]
  );

  return (
    <motion.div
      initial={{ opacity: 0, y: 6, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.3, ease: "easeOut" }}
      onClick={onOpenPreview}
      className="artifact-card group relative flex items-center gap-3 rounded-xl border px-4 py-3 cursor-pointer transition-all duration-200 hover:scale-[1.01]"
      style={{
        background:
          "linear-gradient(135deg, rgba(0, 31, 63, 0.3) 0%, rgba(0, 0, 0, 0.4) 100%)",
        borderColor: "var(--theme-border)",
        backdropFilter: "blur(12px)",
        WebkitBackdropFilter: "blur(12px)",
      }}
      role="button"
      tabIndex={0}
      aria-label={`Artifact: ${filename}`}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onOpenPreview?.();
        }
      }}
    >
      {/* File icon */}
      <div
        className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg border"
        style={{
          background: "rgba(255, 255, 255, 0.04)",
          borderColor: "var(--theme-border)",
        }}
      >
        <Icon className={`h-5 w-5 ${config.iconColor}`} />
      </div>

      {/* File info */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-white truncate">
            {filename}
          </span>
          <span
            className={`inline-flex items-center rounded-full border px-1.5 py-0.5 text-[10px] font-medium ${config.badgeColor}`}
          >
            {config.badge}
          </span>
        </div>
        <p className="text-xs text-grey/70 mt-0.5 truncate">{summary}</p>
      </div>

      {/* Action buttons */}
      <div className="flex items-center gap-1 flex-shrink-0">
        <button
          onClick={handleCopy}
          className="flex h-8 w-8 items-center justify-center rounded-lg transition-colors hover:bg-white/10"
          aria-label="Copy content"
        >
          {copied ? (
            <Check className="h-3.5 w-3.5 text-green-400" />
          ) : (
            <Copy className="h-3.5 w-3.5 text-grey/70 group-hover:text-white/80" />
          )}
        </button>
        <button
          onClick={handleDownload}
          className="flex h-8 w-8 items-center justify-center rounded-lg transition-colors hover:bg-white/10"
          aria-label="Download file"
        >
          <Download className="h-3.5 w-3.5 text-grey/70 group-hover:text-white/80" />
        </button>
      </div>
    </motion.div>
  );
}
