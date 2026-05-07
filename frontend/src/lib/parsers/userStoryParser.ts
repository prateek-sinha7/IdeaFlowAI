import type { UserStoryDocument, Epic, Story } from "@/types";

/**
 * Parse a Markdown string into a structured UserStoryDocument.
 *
 * Expected Markdown format:
 *   # Epic Title [P0]
 *   Epic description text
 *   **Business Value:** ...
 *   **Priority:** ...
 *
 *   ## Story Title
 *   **As a** persona, **I want** goal, **so that** benefit.
 *   **Story Points:** 5
 *   **Dependencies:** Story X
 *   - **Given** X, **When** Y, **Then** Z
 *
 * Also supports the simpler legacy format:
 *   # Epic Title
 *   ## Story Title
 *   - Acceptance criteria
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

    // Epic heading: # Title or # Epic: Title [P0]
    if (/^# /.test(trimmed) && !/^## /.test(trimmed)) {
      // Skip the Personas heading
      if (/^# Personas/i.test(trimmed)) {
        collectingEpicDesc = false;
        collectingStoryDesc = false;
        continue;
      }

      // Finalize previous story into previous epic
      if (currentStory && currentEpic) {
        currentEpic.stories.push(currentStory);
        currentStory = null;
      }
      // Finalize previous epic
      if (currentEpic) {
        epics.push(currentEpic);
      }

      // Parse priority from title like "# Epic: User Auth [P0]"
      let title = trimmed.slice(2).trim();
      let priority: string | undefined;
      const priorityMatch = title.match(/\[(P[012])\]\s*$/);
      if (priorityMatch) {
        priority = priorityMatch[1];
        title = title.replace(/\s*\[P[012]\]\s*$/, "").trim();
      }
      // Remove "Epic: " prefix if present
      title = title.replace(/^Epic:\s*/i, "");

      currentEpic = {
        title,
        description: "",
        stories: [],
        priority,
      };
      collectingEpicDesc = true;
      collectingStoryDesc = false;
      continue;
    }

    // Story heading: ## Title or ## Story: Title
    if (/^## /.test(trimmed) && !/^### /.test(trimmed)) {
      // Finalize previous story
      if (currentStory && currentEpic) {
        currentEpic.stories.push(currentStory);
      }
      let storyTitle = trimmed.slice(3).trim();
      // Remove "Story: " prefix if present
      storyTitle = storyTitle.replace(/^Story:\s*/i, "");

      currentStory = {
        title: storyTitle,
        description: "",
        acceptanceCriteria: [],
      };
      collectingEpicDesc = false;
      collectingStoryDesc = true;
      continue;
    }

    // Skip ### headings (like ### Acceptance Criteria, ### Definition of Done)
    if (/^### /.test(trimmed)) {
      collectingStoryDesc = false;
      collectingEpicDesc = false;
      continue;
    }

    // Story Points line
    if (/^\*\*Story Points:\*\*\s*/i.test(trimmed) && currentStory) {
      const spMatch = trimmed.match(/\*\*Story Points:\*\*\s*(\d+)/i);
      if (spMatch) {
        currentStory.storyPoints = parseInt(spMatch[1], 10);
      }
      collectingStoryDesc = false;
      continue;
    }

    // Dependencies line
    if (/^\*\*Dependencies:\*\*\s*/i.test(trimmed) && currentStory) {
      const depMatch = trimmed.match(/\*\*Dependencies:\*\*\s*(.+)/i);
      if (depMatch) {
        currentStory.dependencies = depMatch[1].trim();
      }
      collectingStoryDesc = false;
      continue;
    }

    // Business Value line for epic
    if (/^\*\*Business Value:\*\*\s*/i.test(trimmed) && currentEpic) {
      const bvMatch = trimmed.match(/\*\*Business Value:\*\*\s*(.+)/i);
      if (bvMatch) {
        currentEpic.businessValue = bvMatch[1].trim();
      }
      collectingEpicDesc = false;
      continue;
    }

    // Priority line for epic
    if (/^\*\*Priority:\*\*\s*/i.test(trimmed) && currentEpic) {
      const prMatch = trimmed.match(/\*\*Priority:\*\*\s*(.+)/i);
      if (prMatch && !currentEpic.priority) {
        currentEpic.priority = prMatch[1].trim();
      }
      collectingEpicDesc = false;
      continue;
    }

    // "As a" description line for story
    if (/^\*\*As a\*\*/i.test(trimmed) && currentStory) {
      currentStory.description = trimmed;
      collectingStoryDesc = false;
      continue;
    }

    // Skip "Acceptance Criteria:" label line
    if (/^\*\*Acceptance Criteria:?\*\*/i.test(trimmed)) {
      collectingStoryDesc = false;
      collectingEpicDesc = false;
      continue;
    }

    // Skip "Definition of Done" or similar section headers
    if (/^\*\*(Definition of Done|DoD|Notes|Technical Notes):?\*\*/i.test(trimmed)) {
      collectingStoryDesc = false;
      collectingEpicDesc = false;
      continue;
    }

    // Acceptance criteria bullet: - text or - [ ] text
    if (/^- /.test(trimmed) && currentStory) {
      const criterionText = trimmed.slice(2).trim().replace(/^\[ \]\s*/, "");
      currentStory.acceptanceCriteria.push(criterionText);
      collectingStoryDesc = false;
      collectingEpicDesc = false;
      continue;
    }

    // Horizontal rule separator
    if (/^---\s*$/.test(trimmed)) {
      collectingEpicDesc = false;
      collectingStoryDesc = false;
      continue;
    }

    // Table rows (skip them - they're for personas)
    if (/^\|/.test(trimmed)) {
      continue;
    }

    // Description lines
    if (collectingEpicDesc && currentEpic) {
      if (trimmed === "") {
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
    const priorityTag = epic.priority ? ` [${epic.priority}]` : "";
    parts.push(`# ${epic.title}${priorityTag}`);
    if (epic.businessValue) {
      parts.push(`**Business Value:** ${epic.businessValue}`);
    }
    if (epic.description) {
      parts.push(epic.description);
    }
    parts.push("");

    for (const story of epic.stories) {
      parts.push(`## ${story.title}`);
      if (story.description) {
        parts.push(story.description);
      }
      if (story.storyPoints) {
        parts.push(`**Story Points:** ${story.storyPoints}`);
      }
      if (story.dependencies) {
        parts.push(`**Dependencies:** ${story.dependencies}`);
      }
      for (const criterion of story.acceptanceCriteria) {
        parts.push(`- ${criterion}`);
      }
      parts.push("");
    }
  }

  return parts.join("\n").trimEnd() + "\n";
}
