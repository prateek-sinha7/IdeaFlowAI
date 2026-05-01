"use client";

import { parseUserStoryMarkdown } from "@/lib/parsers/userStoryParser";

interface UserStoryPreviewProps {
  content?: string;
}

/**
 * Renders parsed User Story Markdown as formatted HTML
 * with Epics/Stories/Acceptance Criteria hierarchy.
 */
export function UserStoryPreview({ content }: UserStoryPreviewProps) {
  if (!content) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-sm text-grey">
          User Story content will appear here once generation begins.
        </p>
      </div>
    );
  }

  const doc = parseUserStoryMarkdown(content);

  return (
    <div className="space-y-6 p-4">
      {doc.epics.map((epic, epicIdx) => (
        <div
          key={epicIdx}
          className="rounded-lg border border-grey/30 bg-navy/30 p-4"
        >
          <h2 className="mb-2 text-lg font-bold text-white">{epic.title}</h2>
          {epic.description && (
            <p className="mb-4 text-sm text-grey">{epic.description}</p>
          )}

          <div className="space-y-4 pl-4">
            {epic.stories.map((story, storyIdx) => (
              <div
                key={storyIdx}
                className="rounded border border-grey/20 bg-black/30 p-3"
              >
                <h3 className="mb-1 text-sm font-semibold text-white">
                  {story.title}
                </h3>
                {story.description && (
                  <p className="mb-2 text-xs text-grey">{story.description}</p>
                )}

                {story.acceptanceCriteria.length > 0 && (
                  <ul className="space-y-1 pl-3">
                    {story.acceptanceCriteria.map((criterion, critIdx) => (
                      <li
                        key={critIdx}
                        className="flex items-start gap-2 text-xs text-grey"
                      >
                        <span className="mt-1 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-grey/60" />
                        <span>{criterion}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
