"use client";

import { useEffect, useState, useMemo } from "react";
import { motion, AnimatePresence } from "motion/react";
import { Eye, FolderDown, PanelRightClose, Copy, Check } from "lucide-react";
import { UserStoryPreview } from "./UserStoryPreview";
import { PPTPreview } from "./PPTPreview";
import { PrototypePreview } from "./PrototypePreview";
import { MarkdownPreview } from "./MarkdownPreview";
import { FilesTab } from "@/components/results/FilesTab";
import { AppBuilderPreview, type ParsedFile } from "./AppBuilderPreview";
import type { WorkflowType } from "@/types/index";

// ─── Agents whose output contains ```filename: ``` code blocks ────────────────
const CODE_PRODUCING_AGENT_IDS = new Set([
  "app-code-generator",
  "app-feature-implementation",
  "app-infra-generator",
  "app-test-implementation",
]);

// ─── Parse ```filename: path/to/file ``` blocks from any markdown string ──────
// Also handles the alternative ### path/to/file + fenced block format used
// by feature-implementation and test-implementation agents.
function parseAppBuilderFilesForIDE(markdown: string): ParsedFile[] {
  const files: ParsedFile[] = [];
  const seen = new Set<string>();

  const langMap: Record<string, string> = {
    ts: "typescript", tsx: "typescript", js: "javascript", jsx: "javascript",
    py: "python", json: "json", md: "markdown", yml: "yaml", yaml: "yaml",
    css: "css", html: "html", sh: "bash", sql: "sql", dockerfile: "dockerfile",
    env: "bash", toml: "toml", prisma: "typescript", rs: "rust", go: "go",
    gitignore: "bash", lock: "plaintext", txt: "plaintext",
    java: "java", cs: "csharp", rb: "ruby", php: "php", kt: "kotlin",
    swift: "swift", xml: "xml", graphql: "graphql",
  };

  const addFile = (path: string, content: string) => {
    path = path.trim();
    if (!path || !content.trim() || seen.has(path)) return;
    // Skip paths that look like section headers, not file paths
    // (must contain a dot or be a known extensionless file like Dockerfile/Makefile)
    const name = path.split("/").pop() || path;
    const hasDot = name.includes(".");
    const isKnownExtensionless = /^(Dockerfile|Makefile|Procfile|Gemfile|Rakefile|Guardfile)$/i.test(name);
    if (!hasDot && !isKnownExtensionless) return;

    seen.add(path);
    const parts = path.split("/");
    const fileName = parts[parts.length - 1];
    const ext = fileName.includes(".") ? fileName.split(".").pop()!.toLowerCase() : "";
    files.push({
      path,
      name: fileName,
      ext,
      content,
      language: langMap[ext] || "plaintext",
    });
  };

  // Format 1: ```filename: path/to/file.ext\n[content]\n```
  const filenameRegex = /```(?:filename:\s*([^\n]+)\n)([\s\S]*?)```/g;
  let m: RegExpExecArray | null;
  while ((m = filenameRegex.exec(markdown)) !== null) {
    addFile(m[1], m[2]);
  }

  // Format 2: ### path/to/file.ext\n```[lang]\n[content]\n```
  // Used by feature-implementation, test-implementation, api-design, devops agents
  const headerRegex = /###\s+([\w./\-@][^\n]*\.\w+)\s*\n```[^\n]*\n([\s\S]*?)```/g;
  while ((m = headerRegex.exec(markdown)) !== null) {
    addFile(m[1], m[2]);
  }

  // Format 3: **`path/to/file.ext`** or **path/to/file.ext** followed by ```
  // Some agents bold the filename before the code block
  const boldRegex = /\*\*`?([\w./\-@][^\n`*]*\.\w+)`?\*\*\s*\n```[^\n]*\n([\s\S]*?)```/g;
  while ((m = boldRegex.exec(markdown)) !== null) {
    addFile(m[1], m[2]);
  }

  return files;
}

// ─── App Builder IDE wrapper ───────────────────────────────────────────────────
// Merges files from ALL code-producing agents + the final output (last agent).
// The Preview tab receives userStoryContent = last agent's output only, so
// without scanning agentOutputs the IDE would only show docs/ files.
function AppBuilderIDEPreview({
  content,
  agentOutputs,
  onRevise,
}: {
  content: string;
  agentOutputs?: import("@/components/results/FilesTab").AgentOutputItem[];
  onRevise?: (s: string) => void;
}) {
  const files = useMemo(() => {
    const seen = new Set<string>();
    const merged: ParsedFile[] = [];

    const addFiles = (parsed: ParsedFile[]) => {
      for (const f of parsed) {
        if (!seen.has(f.path)) {
          seen.add(f.path);
          merged.push(f);
        }
      }
    };

    // 1. Scan all code-producing agents first (agents 8, 9, 10, 12)
    if (agentOutputs) {
      for (const agent of agentOutputs) {
        if (
          agent.agentId &&
          CODE_PRODUCING_AGENT_IDS.has(agent.agentId) &&
          agent.output?.trim()
        ) {
          addFiles(parseAppBuilderFilesForIDE(agent.output));
        }
      }
    }

    // 2. Also scan the final output (last agent — governance) for any
    //    filename: blocks it may contain (e.g. docs/RUNBOOK.md)
    if (content) {
      addFiles(parseAppBuilderFilesForIDE(content));
    }

    return merged;
  }, [content, agentOutputs]);

  const projectName = useMemo(() => {
    // Try to extract project name from architecture agent output first
    const archAgent = agentOutputs?.find(a => a.agentId === "material-analyzer");
    const source = archAgent?.output || content;
    const h = source.match(/^#\s+(.+)/m);
    return h ? h[1].replace(/[^a-zA-Z0-9\s]/g, "").trim().slice(0, 40) : "Generated App";
  }, [content, agentOutputs]);

  return <AppBuilderPreview files={files} onRevise={onRevise} projectName={projectName} />;
}

type PanelTab = "preview" | "files";

interface PreviewPanelProps {
  userStoryContent?: string;
  pptContent?: string;
  prototypeContent?: string;
  isStreaming?: boolean;
  onCollapse?: () => void;
  initialTab?: string;
  onTabSelect?: (tab: string) => void;
  workflowType?: WorkflowType;
  pptxCode?: string;
  onRevisePpt?: (instruction: string) => void;
  onReviseUserStory?: (instruction: string) => void;
  onRevisePrototype?: (instruction: string) => void;
  onReviseAppBuilder?: (instruction: string) => void;
  // Per-agent outputs surfaced under the Files tab once the pipeline has
  // completed. Pass undefined / empty while running — the FilesTab filters
  // out empty outputs itself, but skipping the prop until completion keeps
  // the live "Final output" header from appearing prematurely.
  agentOutputs?: import("@/components/results/FilesTab").AgentOutputItem[];
}

const TAB_CONFIG: { id: PanelTab; label: string; icon: typeof Eye }[] = [
  { id: "preview", label: "Preview", icon: Eye },
  { id: "files", label: "Files", icon: FolderDown },
];

export function PreviewPanel({ userStoryContent, pptContent, prototypeContent, isStreaming, onCollapse, initialTab, onTabSelect, workflowType, pptxCode, onRevisePpt, onReviseUserStory, onRevisePrototype, onReviseAppBuilder, agentOutputs }: PreviewPanelProps) {
  const [activeTab, setActiveTab] = useState<PanelTab>("preview");
  const [copied, setCopied] = useState(false);

  useEffect(() => { if (initialTab === "preview" || initialTab === "files") setActiveTab(initialTab); }, [initialTab]);

  const detectedType: WorkflowType = workflowType || (userStoryContent ? "user_stories" : pptContent ? "ppt" : prototypeContent ? "prototype" : "user_stories");
  // Normalize revision types to their base type for rendering
  const renderType = detectedType === "user_stories_revision" ? "user_stories"
    : detectedType === "ppt_revision" ? "ppt"
    : detectedType === "prototype_revision" ? "prototype"
    : detectedType === "app_builder_revision" ? "app_builder"
    : detectedType;
  const activeContent =
    renderType === "user_stories" || renderType === "app_builder" || renderType === "custom"
      ? userStoryContent
      : renderType === "ppt"
      ? pptContent
      : prototypeContent;
  const hasContent = !!(userStoryContent || pptContent || prototypeContent || pptxCode);

  const handleTabChange = (tabId: PanelTab) => { setActiveTab(tabId); onTabSelect?.(tabId); };
  const handleCopy = () => {
    if (activeContent) {
      navigator.clipboard.writeText(activeContent);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="flex h-full flex-col bg-white border-l border-gray-200">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200">
        <h2 className="text-sm font-semibold text-gray-900">
          {isStreaming ? "Generating..." : hasContent ? "Results" : "Preview"}
        </h2>
        <div className="flex items-center gap-1">
          {hasContent && (
            <button
              onClick={handleCopy}
              className="p-1.5 rounded text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-all"
              title="Copy"
            >
              {copied ? <Check className="h-3.5 w-3.5 text-emerald-600" /> : <Copy className="h-3.5 w-3.5" />}
            </button>
          )}
          {onCollapse && (
            <button
              onClick={onCollapse}
              className="p-1.5 rounded text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-all"
              aria-label="Close preview"
            >
              <PanelRightClose className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>

      {/* Tab Bar */}
      <div className="px-4 py-2 border-b border-gray-200">
        <div className="flex gap-0.5 bg-gray-100 rounded-md p-0.5 w-fit">
          {TAB_CONFIG.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => handleTabChange(tab.id)}
                className={`flex items-center gap-1.5 rounded px-3 py-1 text-xs font-medium transition-all ${
                  isActive ? "bg-white text-gray-900 shadow-sm" : "text-gray-500 hover:text-gray-700"
                }`}
              >
                <Icon className="h-3 w-3" />
                {tab.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Tab Content */}
      <div className="relative flex-1 min-h-0 overflow-hidden">
        <AnimatePresence mode="wait">
          {activeTab === "preview" && (
            <motion.div
              key="preview"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.15 }}
              className="absolute inset-0 overflow-y-auto"
            >
              {!hasContent ? (
                <div className="flex items-center justify-center h-full">
                  <p className="text-xs text-gray-400">Output will appear here</p>
                </div>
              ) : (
                <>
                  {renderType === "user_stories" && userStoryContent && <UserStoryPreview content={userStoryContent} onRevise={onReviseUserStory} />}
                  {(renderType === "app_builder" || renderType === "custom") && userStoryContent && (
                    renderType === "app_builder"
                      ? <AppBuilderIDEPreview content={userStoryContent} agentOutputs={agentOutputs} onRevise={onReviseAppBuilder} />
                      : <MarkdownPreview content={userStoryContent} />
                  )}
                  {renderType === "ppt" && (pptContent || pptxCode) && <PPTPreview content={pptContent} isStreaming={isStreaming} pptxCode={pptxCode} onRevise={onRevisePpt} />}
                  {renderType === "prototype" && prototypeContent && <PrototypePreview content={prototypeContent} isStreaming={isStreaming} onRevise={onRevisePrototype} />}
                </>
              )}
            </motion.div>
          )}
          {activeTab === "files" && (
            <motion.div
              key="files"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.15 }}
              className="absolute inset-0"
            >
              <FilesTab workflowType={renderType} userStoryContent={userStoryContent} pptContent={pptContent} prototypeContent={prototypeContent} agentOutputs={agentOutputs} />
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
