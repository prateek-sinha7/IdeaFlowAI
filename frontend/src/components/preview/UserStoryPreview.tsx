"use client";

import { useState } from "react";
import { FileText, BookOpen, CheckCircle2, Copy, Check, Users, Link2 } from "lucide-react";
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

function getStoryPointColor(points?: number): string {
  if (!points) return "bg-grey/20 text-grey/70";
  if (points <= 3) return "bg-emerald-400/20 text-emerald-400";
  if (points <= 5) return "bg-amber-400/20 text-amber-400";
  return "bg-rose-400/20 text-rose-400";
}

function getPriorityColor(priority?: string): string {
  if (!priority) return "bg-grey/20 text-grey/70";
  if (priority.includes("P0")) return "bg-rose-400/20 text-rose-400";
  if (priority.includes("P1")) return "bg-amber-400/20 text-amber-400";
  return "bg-blue-400/20 text-blue-400";
}

/**
 * Renders parsed User Story Markdown as formatted HTML
 * with Personas, Epics/Stories/Acceptance Criteria hierarchy,
 * story points badges, Given/When/Then formatting, and dependencies.
 */
export function UserStoryPreview({ content }: UserStoryPreviewProps) {
  const [copied, setCopied] = useState(false);

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

  const handleCopyMarkdown = () => {
    navigator.clipboard.writeText(content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Extract personas from content (look for persona table pattern)
  const personaLines = content.split("\n").filter(line => line.startsWith("|") && !line.includes("---") && !line.includes("Persona"));
  const personas = personaLines.map(line => {
    const cells = line.split("|").filter(c => c.trim());
    return cells[0]?.trim() || "";
  }).filter(Boolean);

  return (
    <div className="space-y-4 p-4">
      {/* Copy as Markdown button */}
      <div className="flex justify-end">
        <button
          onClick={handleCopyMarkdown}
          className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[11px] font-medium text-grey/60 hover:text-white hover:bg-white/5 border border-grey/15 transition-all duration-200"
          aria-label="Copy as Markdown"
        >
          {copied ? (
            <>
              <Check className="h-3 w-3 text-emerald-400" />
              <span className="text-emerald-400">Copied!</span>
            </>
          ) : (
            <>
              <Copy className="h-3 w-3" />
              <span>Copy as Markdown</span>
            </>
          )}
        </button>
      </div>

      {/* Persona badges */}
      {personas.length > 0 && (
        <div className="rounded-xl border border-grey/15 bg-gradient-to-br from-navy/30 to-black/40 p-3">
          <div className="flex items-center gap-2 mb-2">
            <Users className="h-3.5 w-3.5 text-cyan-400" />
            <span className="text-[10px] font-bold uppercase tracking-wider text-grey/60">Personas</span>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {personas.map((persona, idx) => (
              <span
                key={idx}
                className="inline-flex items-center rounded-full bg-cyan-400/10 px-2.5 py-1 text-[10px] font-medium text-cyan-400 border border-cyan-400/20"
              >
                {persona}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Epics and Stories */}
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
                <div className="flex items-center gap-2 flex-wrap">
                  <h2 className="text-sm font-bold text-white leading-tight">{epic.title}</h2>
                  {epic.priority && (
                    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[9px] font-bold uppercase ${getPriorityColor(epic.priority)}`}>
                      {epic.priority}
                    </span>
                  )}
                </div>
                {epic.description && (
                  <p className="mt-1 text-xs text-grey/70 leading-relaxed">{epic.description}</p>
                )}
                {epic.businessValue && (
                  <p className="mt-1 text-[10px] text-grey/50 italic">{epic.businessValue}</p>
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
                    <div className="flex items-center gap-2 flex-wrap">
                      <h3 className="text-xs font-semibold text-white leading-tight">
                        <span className="text-grey/50 mr-1.5">{epicIdx + 1}.{storyIdx + 1}</span>
                        {story.title}
                      </h3>
                      {story.storyPoints && (
                        <span className={`inline-flex items-center rounded-full px-1.5 py-0.5 text-[9px] font-bold ${getStoryPointColor(story.storyPoints)}`}>
                          {story.storyPoints} SP
                        </span>
                      )}
                    </div>
                    {story.description && (
                      <p className="mt-1 text-[11px] text-grey/60 leading-relaxed">{story.description}</p>
                    )}

                    {/* Dependencies */}
                    {story.dependencies && story.dependencies !== "None" && (
                      <div className="mt-1.5 flex items-center gap-1">
                        <Link2 className="h-2.5 w-2.5 text-grey/40" />
                        <span className="text-[10px] text-grey/50">Depends on: </span>
                        <span className="text-[10px] text-amber-400/80 font-medium">{story.dependencies}</span>
                      </div>
                    )}

                    {/* Acceptance Criteria with Given/When/Then highlighting */}
                    {story.acceptanceCriteria.length > 0 && (
                      <ul className="mt-2 space-y-1.5">
                        {story.acceptanceCriteria.map((criterion, critIdx) => {
                          const hasGWT = /\*\*Given\*\*|\*\*When\*\*|\*\*Then\*\*/i.test(criterion) ||
                                         /Given .+, When .+, Then/i.test(criterion);
                          return (
                            <li
                              key={critIdx}
                              className="flex items-start gap-1.5 text-[11px] text-grey/70"
                            >
                              <CheckCircle2 className="h-3 w-3 flex-shrink-0 mt-0.5 text-grey/40" />
                              {hasGWT ? (
                                <span
                                  dangerouslySetInnerHTML={{
                                    __html: criterion
                                      .replace(/\*\*Given\*\*/g, '<span class="text-blue-400 font-semibold">Given</span>')
                                      .replace(/\*\*When\*\*/g, '<span class="text-amber-400 font-semibold">When</span>')
                                      .replace(/\*\*Then\*\*/g, '<span class="text-emerald-400 font-semibold">Then</span>')
                                  }}
                                />
                              ) : (
                                <span>{criterion}</span>
                              )}
                            </li>
                          );
                        })}
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
