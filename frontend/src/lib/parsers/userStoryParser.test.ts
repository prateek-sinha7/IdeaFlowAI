import { describe, expect, it } from "vitest";
import type { UserStoryDocument } from "@/types";
import { formatUserStoryMarkdown, parseUserStoryMarkdown } from "./userStoryParser";

const md = (...lines: string[]): string => lines.join("\n");

describe("parseUserStoryMarkdown", () => {
  describe("empty and non-structural input", () => {
    it.each([
      ["an empty string", ""],
      ["only whitespace and blank lines", "  \n\n   \n"],
      ["plain prose without headings", "just some text\nmore text"],
      ["a single '#' with no title", "#"],
      ["a '# ' heading whose title is only spaces", "#   "],
      ["a hash without a following space", "#Title"],
    ])("returns no epics for %s", (_label, input) => {
      expect(parseUserStoryMarkdown(input)).toEqual({ epics: [] });
    });
  });

  describe("epic headings", () => {
    it("parses a plain epic title with empty description and stories", () => {
      expect(parseUserStoryMarkdown("# User Auth")).toEqual({
        epics: [{ title: "User Auth", description: "", stories: [], priority: undefined }],
      });
    });

    it.each(["P0", "P1", "P2"])("extracts the [%s] priority tag and strips it from the title", (p) => {
      const doc = parseUserStoryMarkdown(`# Checkout [${p}]`);

      expect(doc.epics[0].title).toBe("Checkout");
      expect(doc.epics[0].priority).toBe(p);
    });

    it("keeps an unsupported [P3] tag in the title and leaves priority undefined", () => {
      const doc = parseUserStoryMarkdown("# Checkout [P3]");

      expect(doc.epics[0].title).toBe("Checkout [P3]");
      expect(doc.epics[0].priority).toBeUndefined();
    });

    it("only treats a trailing priority tag as a priority", () => {
      const doc = parseUserStoryMarkdown("# [P0] Checkout");

      expect(doc.epics[0].title).toBe("[P0] Checkout");
      expect(doc.epics[0].priority).toBeUndefined();
    });

    it("removes a case-insensitive 'Epic:' prefix and the priority tag together", () => {
      const doc = parseUserStoryMarkdown("# epic:   Payments [P1]   ");

      expect(doc.epics[0].title).toBe("Payments");
      expect(doc.epics[0].priority).toBe("P1");
    });

    it("yields an empty title when the heading is only a priority tag", () => {
      const doc = parseUserStoryMarkdown("# [P2]");

      expect(doc.epics[0].title).toBe("");
      expect(doc.epics[0].priority).toBe("P2");
    });

    it("parses several epics in document order", () => {
      const doc = parseUserStoryMarkdown(md("# One", "# Two", "# Three"));

      expect(doc.epics.map((e) => e.title)).toEqual(["One", "Two", "Three"]);
    });

    it("skips the '# Personas' section without creating an epic, case-insensitively", () => {
      const doc = parseUserStoryMarkdown(
        md("# personas", "| Name | Role |", "| A | B |", "# Real Epic"),
      );

      expect(doc.epics.map((e) => e.title)).toEqual(["Real Epic"]);
    });

    it("does not let Personas text leak into the preceding epic description", () => {
      const doc = parseUserStoryMarkdown(md("# Epic A", "Desc A", "# Personas", "stray text", "# Epic B"));

      expect(doc.epics.map((e) => [e.title, e.description])).toEqual([
        ["Epic A", "Desc A"],
        ["Epic B", ""],
      ]);
    });
  });

  describe("epic description and metadata", () => {
    it("joins consecutive description lines with newlines", () => {
      const doc = parseUserStoryMarkdown(md("# E", "line one", "line two"));

      expect(doc.epics[0].description).toBe("line one\nline two");
    });

    it("ignores leading blank lines before the description starts", () => {
      const doc = parseUserStoryMarkdown(md("# E", "", "", "first"));

      expect(doc.epics[0].description).toBe("first");
    });

    it("stops collecting the description at the first blank line after text", () => {
      const doc = parseUserStoryMarkdown(md("# E", "kept", "", "dropped"));

      expect(doc.epics[0].description).toBe("kept");
    });

    it("trims trailing whitespace on description lines", () => {
      const doc = parseUserStoryMarkdown("# E\nkept   \t");

      expect(doc.epics[0].description).toBe("kept");
    });

    it("captures business value case-insensitively and stops description collection", () => {
      const doc = parseUserStoryMarkdown(md("# E", "**business value:**  Saves time ", "after"));

      expect(doc.epics[0].businessValue).toBe("Saves time");
      expect(doc.epics[0].description).toBe("");
    });

    it("leaves business value undefined when the label has no text", () => {
      const doc = parseUserStoryMarkdown(md("# E", "**Business Value:**"));

      expect(doc.epics[0].businessValue).toBeUndefined();
    });

    it("uses a '**Priority:**' line when the heading has no priority tag", () => {
      const doc = parseUserStoryMarkdown(md("# E", "**Priority:** High"));

      expect(doc.epics[0].priority).toBe("High");
    });

    it("keeps the heading priority tag over a later '**Priority:**' line", () => {
      const doc = parseUserStoryMarkdown(md("# E [P0]", "**Priority:** Low"));

      expect(doc.epics[0].priority).toBe("P0");
    });

    it("ignores an empty '**Priority:**' label", () => {
      const doc = parseUserStoryMarkdown(md("# E", "**Priority:**"));

      expect(doc.epics[0].priority).toBeUndefined();
    });

    it("ignores epic-level labels that appear before any epic exists", () => {
      const doc = parseUserStoryMarkdown(md("**Business Value:** orphan", "**Priority:** P0", "# E"));

      expect(doc.epics[0].businessValue).toBeUndefined();
      expect(doc.epics[0].priority).toBeUndefined();
    });

    it("appends a '#### ' sub-heading to the description while it is still being collected", () => {
      const doc = parseUserStoryMarkdown(md("# E", "text", "#### Detail"));

      expect(doc.epics[0].description).toBe("text\n#### Detail");
    });

    it("stops description collection at a '---' separator", () => {
      const doc = parseUserStoryMarkdown(md("# E", "text", "---", "more"));

      expect(doc.epics[0].description).toBe("text");
    });

    it("stops description collection at a '### ' heading", () => {
      const doc = parseUserStoryMarkdown(md("# E", "text", "### Notes", "more"));

      expect(doc.epics[0].description).toBe("text");
    });

    it("stops description collection at an Acceptance Criteria label", () => {
      const doc = parseUserStoryMarkdown(md("# E", "text", "**Acceptance Criteria:**", "more"));

      expect(doc.epics[0].description).toBe("text");
    });

    it.each(["**Definition of Done:**", "**DoD**", "**Notes:**", "**Technical Notes**"])(
      "stops description collection at the %s section label",
      (label) => {
        const doc = parseUserStoryMarkdown(md("# E", "text", label, "more"));

        expect(doc.epics[0].description).toBe("text");
      },
    );

    it("skips markdown table rows instead of adding them to the description", () => {
      const doc = parseUserStoryMarkdown(md("# E", "text", "| a | b |", "tail"));

      expect(doc.epics[0].description).toBe("text\ntail");
    });
  });

  describe("story headings", () => {
    it("parses a story with title, empty description and no criteria", () => {
      const doc = parseUserStoryMarkdown(md("# E", "## Login"));

      expect(doc.epics[0].stories).toEqual([
        { title: "Login", description: "", acceptanceCriteria: [] },
      ]);
    });

    it("removes a case-insensitive 'Story:' prefix from the title", () => {
      const doc = parseUserStoryMarkdown(md("# E", "## STORY:   Login"));

      expect(doc.epics[0].stories[0].title).toBe("Login");
    });

    it("assigns stories to the epic they appear under", () => {
      const doc = parseUserStoryMarkdown(
        md("# E1", "## S1", "## S2", "# E2", "## S3"),
      );

      expect(doc.epics.map((e) => e.stories.map((s) => s.title))).toEqual([["S1", "S2"], ["S3"]]);
    });

    it("collects plain story description lines until a blank line after text", () => {
      const doc = parseUserStoryMarkdown(md("# E", "## S", "", "first", "second", "", "dropped"));

      expect(doc.epics[0].stories[0].description).toBe("first\nsecond");
    });

    it("uses the '**As a**' line as the whole description, replacing earlier text", () => {
      const doc = parseUserStoryMarkdown(
        md("# E", "## S", "preamble", "**As a** user, **I want** x, **so that** y."),
      );

      expect(doc.epics[0].stories[0].description).toBe("**As a** user, **I want** x, **so that** y.");
    });

    it("ignores an '**As a**' line when no story is open", () => {
      const doc = parseUserStoryMarkdown(md("# E", "**As a** user"));

      expect(doc.epics[0].stories).toEqual([]);
      expect(doc.epics[0].description).toBe("**As a** user");
    });

    it("stops story description collection at a '### ' heading", () => {
      const doc = parseUserStoryMarkdown(md("# E", "## S", "kept", "### Acceptance Criteria", "dropped"));

      expect(doc.epics[0].stories[0].description).toBe("kept");
    });

    it("stops story description collection at a '---' separator", () => {
      const doc = parseUserStoryMarkdown(md("# E", "## S", "kept", "---", "dropped"));

      expect(doc.epics[0].stories[0].description).toBe("kept");
    });

    it("does not treat a '### ' heading as a story", () => {
      const doc = parseUserStoryMarkdown(md("# E", "### Sub"));

      expect(doc.epics[0].stories).toEqual([]);
    });
  });

  describe("story points and dependencies", () => {
    it("parses story points as an integer", () => {
      const doc = parseUserStoryMarkdown(md("# E", "## S", "**Story Points:** 13"));

      expect(doc.epics[0].stories[0].storyPoints).toBe(13);
    });

    it("keeps an explicit zero story point value", () => {
      const doc = parseUserStoryMarkdown(md("# E", "## S", "**story points:** 0"));

      expect(doc.epics[0].stories[0].storyPoints).toBe(0);
    });

    it("leaves story points undefined when the value is not numeric", () => {
      const doc = parseUserStoryMarkdown(md("# E", "## S", "**Story Points:** many"));

      expect(doc.epics[0].stories[0].storyPoints).toBeUndefined();
    });

    it("stops story description collection at a story points line", () => {
      const doc = parseUserStoryMarkdown(md("# E", "## S", "kept", "**Story Points:** 3", "dropped"));

      expect(doc.epics[0].stories[0].description).toBe("kept");
    });

    it("parses trimmed dependencies text", () => {
      const doc = parseUserStoryMarkdown(md("# E", "## S", "**Dependencies:**   Story A, Story B  "));

      expect(doc.epics[0].stories[0].dependencies).toBe("Story A, Story B");
    });

    it("leaves dependencies undefined when the label has no text", () => {
      const doc = parseUserStoryMarkdown(md("# E", "## S", "**Dependencies:**"));

      expect(doc.epics[0].stories[0].dependencies).toBeUndefined();
    });

    it("does not attach story points or dependencies when no story is open", () => {
      const doc = parseUserStoryMarkdown(md("# E", "**Story Points:** 5", "**Dependencies:** X"));

      expect(doc.epics[0].stories).toEqual([]);
    });
  });

  describe("acceptance criteria", () => {
    it("collects dash bullets as acceptance criteria in order", () => {
      const doc = parseUserStoryMarkdown(md("# E", "## S", "- first", "- second"));

      expect(doc.epics[0].stories[0].acceptanceCriteria).toEqual(["first", "second"]);
    });

    it("strips a leading unchecked '[ ]' checkbox marker", () => {
      const doc = parseUserStoryMarkdown(md("# E", "## S", "- [ ] todo item"));

      expect(doc.epics[0].stories[0].acceptanceCriteria).toEqual(["todo item"]);
    });

    it("keeps a checked '[x]' marker as part of the criterion text", () => {
      const doc = parseUserStoryMarkdown(md("# E", "## S", "- [x] done item"));

      expect(doc.epics[0].stories[0].acceptanceCriteria).toEqual(["[x] done item"]);
    });

    it("keeps Given/When/Then bullets verbatim", () => {
      const line = "- **Given** a user, **When** they log in, **Then** they see the dashboard";
      const doc = parseUserStoryMarkdown(md("# E", "## S", line));

      expect(doc.epics[0].stories[0].acceptanceCriteria).toEqual([
        "**Given** a user, **When** they log in, **Then** they see the dashboard",
      ]);
    });

    it("trims extra spaces after the dash", () => {
      const doc = parseUserStoryMarkdown(md("# E", "## S", "-    spaced"));

      expect(doc.epics[0].stories[0].acceptanceCriteria).toEqual(["spaced"]);
    });

    it("does not treat a bare dash with no text as a criterion", () => {
      const doc = parseUserStoryMarkdown(md("# E", "## S", "- ", "-"));

      expect(doc.epics[0].stories[0].acceptanceCriteria).toEqual([]);
    });

    it("treats a dash bullet under an epic with no open story as epic description text", () => {
      const doc = parseUserStoryMarkdown(md("# E", "- stray"));

      expect(doc.epics[0].stories).toEqual([]);
      expect(doc.epics[0].description).toBe("- stray");
    });

    it("keeps collecting bullets after an Acceptance Criteria label", () => {
      const doc = parseUserStoryMarkdown(
        md("# E", "## S", "**Acceptance Criteria:**", "- one", "### Definition of Done", "- two"),
      );

      expect(doc.epics[0].stories[0].acceptanceCriteria).toEqual(["one", "two"]);
    });
  });

  describe("line endings and structure", () => {
    it("handles CRLF line endings without leaking carriage returns", () => {
      const doc = parseUserStoryMarkdown("# E [P1]\r\ndesc\r\n## S\r\n**Story Points:** 2\r\n- ok\r\n");

      expect(doc).toEqual({
        epics: [
          {
            title: "E",
            description: "desc",
            priority: "P1",
            stories: [{ title: "S", description: "", storyPoints: 2, acceptanceCriteria: ["ok"] }],
          },
        ],
      });
    });

    it("parses a complete well-formed document", () => {
      const doc = parseUserStoryMarkdown(
        md(
          "# Personas",
          "| Name | Role |",
          "|------|------|",
          "| Ana | Admin |",
          "",
          "---",
          "",
          "# Epic: User Auth [P0]",
          "Lets users sign in.",
          "**Business Value:** Retention",
          "",
          "## Story: Login",
          "**As a** user, **I want** to log in, **so that** I see my data.",
          "**Story Points:** 5",
          "**Dependencies:** Story Signup",
          "**Acceptance Criteria:**",
          "- **Given** valid creds, **When** submitted, **Then** dashboard shows",
          "- [ ] Invalid creds show an error",
          "---",
          "## Logout",
          "Ends the session.",
          "",
          "# Billing",
          "**Priority:** P2",
        ),
      );

      expect(doc).toEqual({
        epics: [
          {
            title: "User Auth",
            description: "Lets users sign in.",
            priority: "P0",
            businessValue: "Retention",
            stories: [
              {
                title: "Login",
                description: "**As a** user, **I want** to log in, **so that** I see my data.",
                storyPoints: 5,
                dependencies: "Story Signup",
                acceptanceCriteria: [
                  "**Given** valid creds, **When** submitted, **Then** dashboard shows",
                  "Invalid creds show an error",
                ],
              },
              { title: "Logout", description: "Ends the session.", acceptanceCriteria: [] },
            ],
          },
          { title: "Billing", description: "", priority: "P2", stories: [] },
        ],
      });
    });

    it("drops a story that has no epic to belong to when the document ends", () => {
      expect(parseUserStoryMarkdown(md("## Lonely", "- crit"))).toEqual({ epics: [] });
    });

    // Characterization of CURRENT behaviour; suspected defect reported separately:
    // an orphan story (heading before any epic) is not cleared when the first epic starts,
    // so it is later attached to that epic.
    it("attaches a story written before the first epic to that epic (current behaviour)", () => {
      const doc = parseUserStoryMarkdown(md("## Orphan", "# First Epic"));

      expect(doc.epics.map((e) => [e.title, e.stories.map((s) => s.title)])).toEqual([
        ["First Epic", ["Orphan"]],
      ]);
    });

    // Characterization of CURRENT behaviour; suspected defect reported separately:
    // a description line after '**Business Value:**' is discarded.
    it("discards epic description text that follows a business value line (current behaviour)", () => {
      const doc = parseUserStoryMarkdown(md("# E", "**Business Value:** v", "Description after"));

      expect(doc.epics[0].description).toBe("");
    });
  });
});

describe("formatUserStoryMarkdown", () => {
  it("returns a single newline for a document with no epics", () => {
    expect(formatUserStoryMarkdown({ epics: [] })).toBe("\n");
  });

  it("formats a minimal epic as a heading followed by a trailing newline", () => {
    const doc: UserStoryDocument = { epics: [{ title: "E", description: "", stories: [] }] };

    expect(formatUserStoryMarkdown(doc)).toBe("# E\n");
  });

  it("appends the priority tag to the epic heading", () => {
    const doc: UserStoryDocument = {
      epics: [{ title: "E", description: "", stories: [], priority: "P1" }],
    };

    expect(formatUserStoryMarkdown(doc)).toBe("# E [P1]\n");
  });

  it("emits business value before the epic description", () => {
    const doc: UserStoryDocument = {
      epics: [{ title: "E", description: "Desc", stories: [], businessValue: "Value" }],
    };

    expect(formatUserStoryMarkdown(doc)).toBe("# E\n**Business Value:** Value\nDesc\n");
  });

  it("formats a full story with points, dependencies and criteria", () => {
    const doc: UserStoryDocument = {
      epics: [
        {
          title: "E",
          description: "Desc",
          priority: "P0",
          stories: [
            {
              title: "S",
              description: "Story desc",
              storyPoints: 8,
              dependencies: "Other",
              acceptanceCriteria: ["a", "b"],
            },
          ],
        },
      ],
    };

    expect(formatUserStoryMarkdown(doc)).toBe(
      md(
        "# E [P0]",
        "Desc",
        "",
        "## S",
        "Story desc",
        "**Story Points:** 8",
        "**Dependencies:** Other",
        "- a",
        "- b",
        "",
      ),
    );
  });

  it("omits story points of zero and empty optional fields", () => {
    const doc: UserStoryDocument = {
      epics: [
        {
          title: "E",
          description: "",
          stories: [{ title: "S", description: "", storyPoints: 0, acceptanceCriteria: [] }],
        },
      ],
    };

    expect(formatUserStoryMarkdown(doc)).toBe("# E\n\n## S\n");
  });

  it("separates multiple epics with a blank line", () => {
    const doc: UserStoryDocument = {
      epics: [
        { title: "A", description: "", stories: [] },
        { title: "B", description: "", stories: [] },
      ],
    };

    expect(formatUserStoryMarkdown(doc)).toBe("# A\n\n# B\n");
  });

  it("round-trips a document through parse after format", () => {
    const original: UserStoryDocument = {
      epics: [
        {
          title: "Auth",
          description: "Sign in",
          priority: "P1",
          stories: [
            {
              title: "Login",
              description: "**As a** user, **I want** in.",
              storyPoints: 3,
              dependencies: "Signup",
              acceptanceCriteria: ["works", "fails safely"],
            },
          ],
        },
      ],
    };

    expect(parseUserStoryMarkdown(formatUserStoryMarkdown(original))).toEqual(original);
  });
});
