"use client";

import { FileText, BookOpen, CheckCircle2 } from "lucide-react";
import { parseUserStoryMarkdown } from "@/lib/parsers/userStoryParser";

interface UserStoryPreviewProps {
  content?: string;
}

const EPIC_ACCENT_COLORS = [
  "border-l-blue-400",
  "border-l-purple-400",
  "border-l-emerald-400",
  "border-l-amber-400",
  "border-l-rose-400",
  "border-l-cyan-400",
];

/**
 * Renders parsed User Story Markdown as formatted HTML
 * with Epics/Stories/Acceptance Criteria hierarchy.
 * Features numbered epics/stories, accent borders, and better visual hierarchy.
 */
export function UserStoryPreview({ content }: UserStoryPreviewProps) {
  if (!content) {
    return (
      <div className="flex h-full flex-col items-center justify-center px-6">
        <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-navy/50 border border-grey/10 mb-4">
          <FileText className="h-7 w-7 text-grey/40" />
        </div>
        <p className="text-sm font-medium text-grey/60 mb-1">No User Stories Yet</p>
        <p className="text-xs text-grey/40 text-center max-w-[200px]">
          User story content will appear here once generation begins.
        </p>
      </div>
    );
  }

  const doc = parseUserStoryMarkdown(content);

  return (
    <div className="space-y-5 p-4">
      {doc.epics.map((epic, epicIdx) => (
        <div
          key={epicIdx}
          className={`rounded-xl border border-grey/15 bg-gradient-to-br from-navy/40 to-navy/20 overflow-hidden border-l-[3px] ${EPIC_ACCENT_COLORS[epicIdx % EPIC_ACCENT_COLORS.length]}`}
        >
          {/* Epic header */}
          <div className="px-4 pt-4 pb-3">
            <div className="flex items-start gap-3">
              <div className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-md bg-white/10 text-xs font-bold text-white/80">
                {epicIdx + 1}
              </div>
              <div className="flex-1 min-w-0">
                <h2 className="text-sm font-bold text-white leading-tight">{epic.title}</h2>
                {epic.description && (
                  <p className="mt-1 text-xs text-grey/70 leading-relaxed">{epic.description}</p>
                )}
              </div>
            </div>
          </div>

          {/* Stories */}
          <div className="space-y-2 px-4 pb-4">
            {epic.stories.map((story, storyIdx) => (
              <div
                key={storyIdx}
                className="rounded-lg border border-grey/10 bg-black/30 p-3"
              >
                <div className="flex items-start gap-2.5">
                  <div className="flex items-center gap-1.5">
                    <BookOpen className="h-3.5 w-3.5 text-grey/50 flex-shrink-0 mt-0.5" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <h3 className="text-xs font-semibold text-white leading-tight">
                      <span className="text-grey/50 mr-1.5">{epicIdx + 1}.{storyIdx + 1}</span>
                      {story.title}
                    </h3>
                    {story.description && (
                      <p className="mt-1 text-[11px] text-grey/60 leading-relaxed">{story.description}</p>
                    )}

                    {story.acceptanceCriteria.length > 0 && (
                      <ul className="mt-2 space-y-1">
                        {story.acceptanceCriteria.map((criterion, critIdx) => (
                          <li
                            key={critIdx}
                            className="flex items-start gap-1.5 text-[11px] text-grey/70"
                          >
                            <CheckCircle2 className="h-3 w-3 flex-shrink-0 mt-0.5 text-grey/40" />
                            <span>{criterion}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
