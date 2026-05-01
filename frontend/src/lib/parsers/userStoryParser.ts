import type { UserStoryDocument, Epic, Story } from "@/types";

/**
 * Parse a Markdown string into a structured UserStoryDocument.
 *
 * Expected Markdown format:
 *   # Epic Title
 *   Epic description text
 *
 *   ## Story Title
 *   Story description text
 *   - Acceptance criteria item 1
 *   - Acceptance criteria item 2
 */
export function parseUserStoryMarkdown(markdown: string): UserStoryDocument {
  const lines = markdown.split("\n");
  const epics: Epic[] = [];

  let currentEpic: Epic | null = null;
  let currentStory: Story | null = null;
  let collectingEpicDesc = false;
  let collectingStoryDesc = false;

  for (const line of lines) {
    const trimmed = line.trimEnd();

    // Epic heading: # Title
    if (/^# /.test(trimmed)) {
      // Finalize previous story into previous epic
      if (currentStory && currentEpic) {
        currentEpic.stories.push(currentStory);
        currentStory = null;
      }
      // Finalize previous epic
      if (currentEpic) {
        epics.push(currentEpic);
      }
      currentEpic = {
        title: trimmed.slice(2).trim(),
        description: "",
        stories: [],
      };
      collectingEpicDesc = true;
      collectingStoryDesc = false;
      continue;
    }

    // Story heading: ## Title
    if (/^## /.test(trimmed)) {
      // Finalize previous story
      if (currentStory && currentEpic) {
        currentEpic.stories.push(currentStory);
      }
      currentStory = {
        title: trimmed.slice(3).trim(),
        description: "",
        acceptanceCriteria: [],
      };
      collectingEpicDesc = false;
      collectingStoryDesc = true;
      continue;
    }

    // Acceptance criteria bullet: - text
    if (/^- /.test(trimmed) && currentStory) {
      currentStory.acceptanceCriteria.push(trimmed.slice(2).trim());
      collectingStoryDesc = false;
      collectingEpicDesc = false;
      continue;
    }

    // Description lines
    if (collectingEpicDesc && currentEpic) {
      if (trimmed === "") {
        // Skip leading blank lines, preserve trailing ones as separator
        if (currentEpic.description.length > 0) {
          collectingEpicDesc = false;
        }
      } else {
        currentEpic.description = currentEpic.description
          ? currentEpic.description + "\n" + trimmed
          : trimmed;
      }
      continue;
    }

    if (collectingStoryDesc && currentStory) {
      if (trimmed === "") {
        if (currentStory.description.length > 0) {
          collectingStoryDesc = false;
        }
      } else {
        currentStory.description = currentStory.description
          ? currentStory.description + "\n" + trimmed
          : trimmed;
      }
      continue;
    }
  }

  // Finalize last story and epic
  if (currentStory && currentEpic) {
    currentEpic.stories.push(currentStory);
  }
  if (currentEpic) {
    epics.push(currentEpic);
  }

  return { epics };
}

/**
 * Format a UserStoryDocument back into Markdown.
 */
export function formatUserStoryMarkdown(doc: UserStoryDocument): string {
  const parts: string[] = [];

  for (const epic of doc.epics) {
    parts.push(`# ${epic.title}`);
    if (epic.description) {
      parts.push(epic.description);
    }
    parts.push("");

    for (const story of epic.stories) {
      parts.push(`## ${story.title}`);
      if (story.description) {
        parts.push(story.description);
      }
      for (const criterion of story.acceptanceCriteria) {
        parts.push(`- ${criterion}`);
      }
      parts.push("");
    }
  }

  return parts.join("\n").trimEnd() + "\n";
}
