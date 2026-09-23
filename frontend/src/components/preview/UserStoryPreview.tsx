"use client";

import { useState } from "react";
import { FileText, Copy, Check, ChevronDown, ChevronRight, Link2, RefreshCw } from "lucide-react";
import { useClipboardCopy } from "@/hooks/useClipboardCopy";
import { parseUserStoryMarkdown } from "@/lib/parsers/userStoryParser";

interface UserStoryPreviewProps {
  content?: string;
  onRevise?: (instruction: string) => void;
}

function getPriorityLabel(priority?: string): { label: string; cls: string } {
  if (!priority) return { label: "P2", cls: "bg-gray-100 text-gray-500" };
  if (priority.includes("P0")) return { label: "P0", cls: "bg-[#1B2A4A] text-white" };
  if (priority.includes("P1")) return { label: "P1", cls: "bg-gray-800 text-white" };
  return { label: "P2", cls: "bg-gray-200 text-gray-600" };
}

function getSprintColor(sp?: number): string {
  if (!sp) return "text-gray-400 bg-gray-100";
  if (sp <= 2) return "text-gray-700 bg-gray-100";
  if (sp <= 5) return "text-gray-700 bg-gray-100";
  return "text-gray-700 bg-gray-100";
}

export function UserStoryPreview({ content, onRevise }: UserStoryPreviewProps) {
  const { copied, failed, copy } = useClipboardCopy();
  const [expandedEpics, setExpandedEpics] = useState<Set<number>>(new Set([0, 1, 2, 3, 4, 5]));
  const [revisionText, setRevisionText] = useState("");

  if (!content) {
    return (
      <div className="flex h-full flex-col items-center justify-center px-6">
        <div className="flex h-14 w-14 items-center justify-center rounded-lg bg-gray-100 border border-gray-200 mb-4">
          <FileText className="h-7 w-7 text-gray-400" />
        </div>
        <p className="text-sm font-medium text-gray-600 mb-1">No User Stories Yet</p>
        <p className="text-xs text-gray-400 text-center max-w-[220px]">
          Run the pipeline to generate a structured product backlog.
        </p>
      </div>
    );
  }

  const doc = parseUserStoryMarkdown(content);

  const handleCopy = () => void copy(content);

  const toggleEpic = (idx: number) => {
    setExpandedEpics((prev) => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx);
      else next.add(idx);
      return next;
    });
  };

  const totalStories = doc.epics.reduce((s, e) => s + e.stories.length, 0);
  const totalPoints = doc.epics.reduce((s, e) => s + e.stories.reduce((p, st) => p + (st.storyPoints || 0), 0), 0);
  const totalSprints = Math.ceil(totalPoints / 30) || 1;
  const p0Count = doc.epics.filter((e) => e.priority?.includes("P0")).length;
  const p1Count = doc.epics.filter((e) => e.priority?.includes("P1")).length;
  const p2Count = doc.epics.length - p0Count - p1Count;

  if (doc.epics.length === 0) {
    return (
      <div className="p-5 h-full overflow-y-auto">
        <div className="flex justify-end mb-3">
          <button onClick={handleCopy} className="flex items-center gap-1.5 text-[11px] font-medium text-gray-500 hover:text-gray-900 border border-gray-200 rounded-md px-2.5 py-1.5 transition-all">
            {copied ? <><Check className="h-3 w-3 text-emerald-600" /> Copied</> : <><Copy className="h-3 w-3" /> {failed ? "Copy failed" : "Copy MD"}</>}
          </button>
        </div>
        <pre className="text-[11px] text-gray-700 leading-relaxed whitespace-pre-wrap font-mono">{content}</pre>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto bg-white">
      {/* Header */}
      <div className="sticky top-0 z-10 bg-white border-b border-gray-100 px-6 py-4 flex items-center justify-between">
        <div>
          <h1 className="text-[15px] font-semibold text-gray-900">Product Backlog</h1>
        </div>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1.5 text-[11px] font-medium text-gray-500 hover:text-gray-900 border border-gray-200 rounded-md px-2.5 py-1.5 transition-all"
        >
          {copied ? <><Check className="h-3 w-3 text-emerald-600" /> Copied</> : <><Copy className="h-3 w-3" /> {failed ? "Copy failed" : "Copy MD"}</>}
        </button>
      </div>

      {/* Stats bar */}
      <div className="border-b border-gray-100 px-6 py-4 grid grid-cols-4 divide-x divide-gray-100">
        <div className="pr-6">
          <p className="text-[22px] font-bold text-gray-900 leading-none">{doc.epics.length}</p>
          <p className="text-[11px] text-gray-400 mt-1">Epics</p>
        </div>
        <div className="px-6">
          <p className="text-[22px] font-bold text-gray-900 leading-none">{totalStories}</p>
          <p className="text-[11px] text-gray-400 mt-1">Stories</p>
        </div>
        <div className="px-6">
          <p className="text-[22px] font-bold text-[#1B2A4A] leading-none">{totalPoints}</p>
          <p className="text-[11px] text-gray-400 mt-1">Points</p>
        </div>
        <div className="pl-6">
          <p className="text-[22px] font-bold text-gray-900 leading-none">{totalSprints}</p>
          <p className="text-[11px] text-gray-400 mt-1">Sprints</p>
        </div>
      </div>

      {/* Priority pills */}
      {(p0Count > 0 || p1Count > 0 || p2Count > 0) && (
        <div className="px-6 py-3 border-b border-gray-100 flex items-center gap-2">
          {p0Count > 0 && (
            <span className="text-[11px] font-medium px-2.5 py-1 rounded-full bg-[#1B2A4A] text-white">
              {p0Count} Must-have
            </span>
          )}
          {p1Count > 0 && (
            <span className="text-[11px] font-medium px-2.5 py-1 rounded-full bg-gray-700 text-white">
              {p1Count} Should-have
            </span>
          )}
          {p2Count > 0 && (
            <span className="text-[11px] font-medium px-2.5 py-1 rounded-full bg-gray-200 text-gray-600">
              {p2Count} Nice-to-have
            </span>
          )}
        </div>
      )}

      {/* Epics */}
      <div className="divide-y divide-gray-100">
        {doc.epics.map((epic, epicIdx) => {
          const isExpanded = expandedEpics.has(epicIdx);
          const { label: prioLabel, cls: prioCls } = getPriorityLabel(epic.priority);

          return (
            <div key={epicIdx}>
              {/* Epic header */}
              <button
                onClick={() => toggleEpic(epicIdx)}
                className="w-full px-6 py-4 flex items-start gap-3 text-left hover:bg-gray-50 transition-colors"
              >
                <div className="flex-shrink-0 mt-0.5">
                  {isExpanded
                    ? <ChevronDown className="h-4 w-4 text-gray-400" />
                    : <ChevronRight className="h-4 w-4 text-gray-400" />
                  }
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${prioCls}`}>{prioLabel}</span>
                    <h2 className="text-[13px] font-semibold text-gray-900">{epic.title}</h2>
                    <span className="text-[11px] text-gray-400">{epic.stories.length} stories</span>
                  </div>
                  {epic.businessValue && (
                    <p className="mt-1 text-[11px] text-gray-500 leading-relaxed">{epic.businessValue}</p>
                  )}
                </div>
              </button>

              {/* Stories */}
              {isExpanded && (
                <div className="bg-gray-50 divide-y divide-gray-100">
                  {epic.stories.map((story, storyIdx) => (
                    <div key={storyIdx} className="px-6 py-4 pl-14">
                      {/* Story header */}
                      <div className="flex items-start gap-3">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap mb-1.5">
                            <span className="text-[10px] font-mono text-gray-400 bg-white border border-gray-200 px-1.5 py-0.5 rounded">
                              {epicIdx + 1}.{storyIdx + 1}
                            </span>
                            <h3 className="text-[12px] font-semibold text-gray-900">{story.title}</h3>
                            {story.storyPoints && (
                              <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${getSprintColor(story.storyPoints)}`}>
                                {story.storyPoints} SP
                              </span>
                            )}
                          </div>

                          {/* As a / I want / So that */}
                          {story.description && (
                            <p className="text-[11px] text-gray-500 leading-relaxed mb-2 italic">
                              {story.description.replace(/\*\*/g, "")}
                            </p>
                          )}

                          {/* Dependencies */}
                          {story.dependencies && story.dependencies !== "None" && (
                            <div className="flex items-center gap-1.5 mb-2">
                              <Link2 className="h-3 w-3 text-gray-400 flex-shrink-0" />
                              <span className="text-[10px] text-gray-400">Depends on: </span>
                              <span className="text-[10px] text-[#1B2A4A] font-medium underline underline-offset-2">
                                {story.dependencies}
                              </span>
                            </div>
                          )}

                          {/* Acceptance Criteria */}
                          {story.acceptanceCriteria.length > 0 && (
                            <div className="mt-2 space-y-1.5">
                              <p className="text-[9px] font-semibold text-gray-400 uppercase tracking-wider mb-1.5">
                                Acceptance Criteria
                              </p>
                              {story.acceptanceCriteria.map((criterion, critIdx) => (
                                <div key={critIdx} className="flex items-start gap-2 text-[11px] text-gray-600 leading-relaxed">
                                  <div className="w-1 h-1 rounded-full bg-gray-300 flex-shrink-0 mt-2" />
                                  <span
                                    dangerouslySetInnerHTML={{
                                      __html: criterion
                                        // Strip any HTML tags from model output before our safe replacements
                                        .replace(/<[^>]*>/g, '')
                                        .replace(/\*\*Given\*\*/g, '<span class="font-semibold text-[#1B2A4A]">Given</span>')
                                        .replace(/\*\*When\*\*/g, '<span class="font-semibold text-gray-700">When</span>')
                                        .replace(/\*\*Then\*\*/g, '<span class="font-semibold text-gray-900">Then</span>')
                                        .replace(/\bGiven\b(?![^<]*>)/g, '<span class="font-semibold text-[#1B2A4A]">Given</span>')
                                        .replace(/\bWhen\b(?![^<]*>)/g, '<span class="font-semibold text-gray-700">When</span>')
                                        .replace(/\bThen\b(?![^<]*>)/g, '<span class="font-semibold text-gray-900">Then</span>')
                                    }}
                                  />
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Revision bar — request changes to the backlog */}
      {onRevise && (
        <div className="flex-shrink-0 border-t border-gray-100 bg-white px-5 py-3 flex items-center gap-3 sticky bottom-0">
          <input
            type="text"
            aria-label="Revision instructions"
            name="user-story-revision"
            value={revisionText}
            onChange={(e) => setRevisionText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && revisionText.trim()) {
                onRevise(revisionText.trim());
                setRevisionText("");
              }
            }}
            placeholder='Request changes, e.g. "Add a story for password reset" or "Remove the NFR epic"'
            className="flex-1 text-[12px] text-gray-700 placeholder-gray-400 bg-gray-50 border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:border-gray-400 transition-colors"
          />
          <button
            onClick={() => {
              if (revisionText.trim()) {
                onRevise(revisionText.trim());
                setRevisionText("");
              }
            }}
            disabled={!revisionText.trim()}
            className="flex items-center gap-1.5 text-[11px] font-medium text-white bg-[#1B2A4A] hover:bg-[#2a3d5e] disabled:opacity-40 rounded-lg px-3 py-2 transition-colors flex-shrink-0"
          >
            <RefreshCw className="h-3.5 w-3.5" /> Revise
          </button>
        </div>
      )}
    </div>
  );
}
