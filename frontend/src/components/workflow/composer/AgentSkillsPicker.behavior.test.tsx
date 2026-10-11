import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { renderWithProviders, screen, within } from "@/test/renderWithProviders";
import type { AgentDef } from "@/types/index";
import type { GlobalSkillEntry } from "@/store/api/skills";

import { AgentSkillsPicker } from "./AgentSkillsPicker";

// Behavior of the per-agent Skills picker beyond the ISS-359 markdown-render
// regression pinned in AgentSkillsPicker.test.tsx: compatibility filtering,
// search/category narrowing, selection, read-only mounts and the detail dialog.

const BUILTIN: AgentDef = {
  id: "domain_discovery",
  name: "Domain Discovery Agent",
  role: "Research",
  description: "Discovers things.",
  pipeline_type: "discovery",
  order: 0,
  icon: "zap",
  estimated_duration: 300,
  has_skill: true,
};

function makeSkill(
  id: string,
  name: string,
  overrides: Partial<GlobalSkillEntry> = {},
): GlobalSkillEntry {
  return {
    id,
    name,
    display_name: name,
    description: `${name} description`,
    content: `# ${name}\n\nBody`,
    category: "testing",
    tags: [],
    ...overrides,
  };
}

const CATEGORIES = [
  { id: "all", label: "All" },
  { id: "testing", label: "Testing" },
  { id: "security", label: "Security" },
  { id: "planning", label: "Planning" },
];

function stateWith(skills: GlobalSkillEntry[], categories = CATEGORIES) {
  return {
    skills: {
      skills,
      totalCount: skills.length,
      skillCategories: categories,
      status: "succeeded" as const,
      error: null,
    },
  };
}

/** Seven skills so the search box and category pills are shown (> 6). */
const MANY: GlobalSkillEntry[] = [
  makeSkill("s1", "Alpha Audit", { category: "security", description: "Finds vulnerabilities" }),
  makeSkill("s2", "Bravo Build", { category: "testing" }),
  makeSkill("s3", "Charlie Check", { category: "testing" }),
  makeSkill("s4", "Delta Deploy", { category: "testing" }),
  makeSkill("s5", "Echo Explore", { category: "testing" }),
  makeSkill("s6", "Foxtrot Fix", { category: "testing" }),
  makeSkill("s7", "Golf Gate", { category: "testing" }),
];

describe("AgentSkillsPicker", () => {
  describe("compatibility filtering", () => {
    it("shows a notice when no skill fits a built-in agent", () => {
      renderWithProviders(<AgentSkillsPicker agent={BUILTIN} />, {
        preloadedState: stateWith([makeSkill("x", "Other Skill", { compatible_agents: ["someone_else"] })]),
      });

      expect(screen.getByText("No compatible skills.")).toBeInTheDocument();
      expect(screen.queryByText("Attach skills to this agent in the workflow composer.")).not.toBeInTheDocument();
    });

    it("lists skills that name the agent and skills with no compatibility list, hiding others", () => {
      renderWithProviders(<AgentSkillsPicker agent={BUILTIN} />, {
        preloadedState: stateWith([
          makeSkill("mine", "Mine Skill", { compatible_agents: ["domain_discovery"] }),
          makeSkill("any", "Anyone Skill", { compatible_agents: [] }),
          makeSkill("unset", "Unset Skill"),
          makeSkill("theirs", "Theirs Skill", { compatible_agents: ["someone_else"] }),
        ]),
      });

      expect(screen.getByRole("button", { name: "Add Mine Skill" })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Add Anyone Skill" })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Add Unset Skill" })).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Add Theirs Skill" })).not.toBeInTheDocument();
    });

    it("offers every skill to a custom agent regardless of compatibility", () => {
      renderWithProviders(<AgentSkillsPicker agent={{ ...BUILTIN, isCustom: true }} />, {
        preloadedState: stateWith([makeSkill("theirs", "Theirs Skill", { compatible_agents: ["someone_else"] })]),
      });

      expect(screen.getByRole("button", { name: "Add Theirs Skill" })).toBeInTheDocument();
    });
  });

  describe("selection", () => {
    it("adds a skill to an agent that has no skills list yet", async () => {
      const user = userEvent.setup();
      const onSkillsChange = vi.fn();
      renderWithProviders(<AgentSkillsPicker agent={BUILTIN} onSkillsChange={onSkillsChange} />, {
        preloadedState: stateWith([makeSkill("s1", "Alpha Audit")]),
      });

      await user.click(screen.getByRole("button", { name: "Add Alpha Audit" }));

      expect(onSkillsChange).toHaveBeenCalledWith("domain_discovery", ["s1"]);
    });

    it("appends a skill after the ones already attached", async () => {
      const user = userEvent.setup();
      const onSkillsChange = vi.fn();
      renderWithProviders(
        <AgentSkillsPicker agent={{ ...BUILTIN, skills: ["s1"] }} onSkillsChange={onSkillsChange} />,
        { preloadedState: stateWith([makeSkill("s1", "Alpha Audit"), makeSkill("s2", "Bravo Build")]) },
      );

      await user.click(screen.getByRole("button", { name: "Add Bravo Build" }));

      expect(onSkillsChange).toHaveBeenCalledWith("domain_discovery", ["s1", "s2"]);
    });

    it("removes only the clicked skill from the attached list", async () => {
      const user = userEvent.setup();
      const onSkillsChange = vi.fn();
      renderWithProviders(
        <AgentSkillsPicker agent={{ ...BUILTIN, skills: ["s1", "s2"] }} onSkillsChange={onSkillsChange} />,
        { preloadedState: stateWith([makeSkill("s1", "Alpha Audit"), makeSkill("s2", "Bravo Build")]) },
      );

      await user.click(screen.getByRole("button", { name: "Remove Alpha Audit" }));

      expect(onSkillsChange).toHaveBeenCalledWith("domain_discovery", ["s2"]);
    });

    it("tolerates a missing change handler", async () => {
      const user = userEvent.setup();
      renderWithProviders(<AgentSkillsPicker agent={BUILTIN} />, {
        preloadedState: stateWith([makeSkill("s1", "Alpha Audit")]),
      });

      await user.click(screen.getByRole("button", { name: "Add Alpha Audit" }));

      expect(screen.getByRole("button", { name: "Add Alpha Audit" })).toBeInTheDocument();
    });

    it("shows how many skills are attached only when there are some", () => {
      const { rerender } = renderWithProviders(<AgentSkillsPicker agent={BUILTIN} />, {
        preloadedState: stateWith([makeSkill("s1", "Alpha Audit"), makeSkill("s2", "Bravo Build")]),
      });
      const root = screen.getByTestId("agent-skills-picker-domain_discovery");
      expect(within(root).queryByText(/^\d+$/)).not.toBeInTheDocument();

      rerender(<AgentSkillsPicker agent={{ ...BUILTIN, skills: ["s1", "s2"] }} />);

      expect(within(root).getByText("2")).toBeInTheDocument();
    });

    it("lists attached skills first, then the rest alphabetically", () => {
      renderWithProviders(<AgentSkillsPicker agent={{ ...BUILTIN, skills: ["s3"] }} />, {
        preloadedState: stateWith([
          makeSkill("s1", "Alpha Audit"),
          makeSkill("s2", "Bravo Build"),
          makeSkill("s3", "Charlie Check"),
        ]),
      });

      const labels = screen
        .getAllByRole("button", { name: /^(Add|Remove) / })
        .map((b) => b.getAttribute("aria-label"));
      expect(labels).toEqual(["Remove Charlie Check", "Add Alpha Audit", "Add Bravo Build"]);
    });

    it("keeps the scroll position of the surrounding scroll container after the list reorders", async () => {
      const user = userEvent.setup();
      let scrollTop = 0;

      function Host() {
        const [skills, setSkills] = useState<string[]>([]);
        return (
          <div
            data-testid="scroller"
            style={{ overflowY: "auto" }}
            ref={(el) => {
              if (!el) return;
              Object.defineProperty(el, "scrollHeight", { configurable: true, value: 1000 });
              Object.defineProperty(el, "clientHeight", { configurable: true, value: 100 });
              Object.defineProperty(el, "scrollTop", {
                configurable: true,
                get: () => scrollTop,
                set: (v: number) => {
                  scrollTop = v;
                },
              });
            }}
          >
            <AgentSkillsPicker
              agent={{ ...BUILTIN, skills }}
              onSkillsChange={(_id, next) => {
                // Simulate the browser resetting the offset as the reordered list repaints.
                scrollTop = 0;
                setSkills(next);
              }}
            />
          </div>
        );
      }

      renderWithProviders(<Host />, {
        preloadedState: stateWith([makeSkill("s1", "Alpha Audit"), makeSkill("s2", "Bravo Build")]),
      });
      scrollTop = 240;

      await user.click(screen.getByRole("button", { name: "Add Bravo Build" }));

      expect(scrollTop).toBe(240);
      expect(screen.getByRole("button", { name: "Remove Bravo Build" })).toBeInTheDocument();
    });
  });

  describe("read-only mount", () => {
    it("disables attaching and searching but explains where to attach skills", () => {
      renderWithProviders(<AgentSkillsPicker agent={BUILTIN} readOnly />, {
        preloadedState: stateWith(MANY),
      });

      expect(screen.getByRole("button", { name: "Add Alpha Audit" })).toBeDisabled();
      expect(screen.getByRole("searchbox", { name: "Search skills" })).toBeDisabled();
      expect(screen.getByRole("button", { name: "Security" })).toBeDisabled();
      expect(screen.getByRole("button", { name: "View Alpha Audit details" })).toBeEnabled();
      expect(screen.getByText("Attach skills to this agent in the workflow composer.")).toBeInTheDocument();
    });

    it("leaves controls enabled and omits the note when editable", () => {
      renderWithProviders(<AgentSkillsPicker agent={BUILTIN} />, { preloadedState: stateWith(MANY) });

      expect(screen.getByRole("button", { name: "Add Alpha Audit" })).toBeEnabled();
      expect(screen.getByRole("searchbox", { name: "Search skills" })).toBeEnabled();
      expect(screen.queryByText("Attach skills to this agent in the workflow composer.")).not.toBeInTheDocument();
    });
  });

  describe("search and category filters", () => {
    it("hides search and category pills for a short list", () => {
      renderWithProviders(<AgentSkillsPicker agent={BUILTIN} />, {
        preloadedState: stateWith(MANY.slice(0, 6)),
      });

      expect(screen.queryByRole("searchbox", { name: "Search skills" })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Security" })).not.toBeInTheDocument();
    });

    it("hides category pills when the catalog offers a single category", () => {
      renderWithProviders(<AgentSkillsPicker agent={BUILTIN} />, {
        preloadedState: stateWith(MANY, [{ id: "all", label: "All" }]),
      });

      expect(screen.getByRole("searchbox", { name: "Search skills" })).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "All" })).not.toBeInTheDocument();
    });

    it("only offers category pills that some compatible skill belongs to", () => {
      renderWithProviders(<AgentSkillsPicker agent={BUILTIN} />, { preloadedState: stateWith(MANY) });

      expect(screen.getByRole("button", { name: "All" })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Testing" })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Security" })).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Planning" })).not.toBeInTheDocument();
    });

    it("narrows the list to one category and back to all", async () => {
      const user = userEvent.setup();
      renderWithProviders(<AgentSkillsPicker agent={BUILTIN} />, { preloadedState: stateWith(MANY) });

      await user.click(screen.getByRole("button", { name: "Security" }));
      expect(screen.getByRole("button", { name: "Add Alpha Audit" })).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Add Bravo Build" })).not.toBeInTheDocument();

      await user.click(screen.getByRole("button", { name: "All" }));
      expect(screen.getByRole("button", { name: "Add Bravo Build" })).toBeInTheDocument();
    });

    it("filters by name, case-insensitively, ignoring surrounding spaces", async () => {
      const user = userEvent.setup();
      renderWithProviders(<AgentSkillsPicker agent={BUILTIN} />, { preloadedState: stateWith(MANY) });

      await user.type(screen.getByRole("searchbox", { name: "Search skills" }), "  BRAVO ");

      expect(screen.getByRole("button", { name: "Add Bravo Build" })).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Add Alpha Audit" })).not.toBeInTheDocument();
    });

    it("filters by description text", async () => {
      const user = userEvent.setup();
      renderWithProviders(<AgentSkillsPicker agent={BUILTIN} />, { preloadedState: stateWith(MANY) });

      await user.type(screen.getByRole("searchbox", { name: "Search skills" }), "vulnerab");

      expect(screen.getByRole("button", { name: "Add Alpha Audit" })).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Add Bravo Build" })).not.toBeInTheDocument();
    });

    it("copes with a skill that has no description", async () => {
      const user = userEvent.setup();
      const skills = [
        ...MANY.slice(0, 6),
        { ...makeSkill("s7", "Golf Gate"), description: undefined as unknown as string },
      ];
      renderWithProviders(<AgentSkillsPicker agent={BUILTIN} />, { preloadedState: stateWith(skills) });

      await user.type(screen.getByRole("searchbox", { name: "Search skills" }), "golf");

      expect(screen.getByRole("button", { name: "Add Golf Gate" })).toBeInTheDocument();
    });

    it("says nothing matches when the search finds no skill", async () => {
      const user = userEvent.setup();
      renderWithProviders(<AgentSkillsPicker agent={BUILTIN} />, { preloadedState: stateWith(MANY) });

      await user.type(screen.getByRole("searchbox", { name: "Search skills" }), "zzz-no-such-skill");

      expect(screen.getByText("No skills match.")).toBeInTheDocument();
    });

    it("keeps an attached skill visible even when the filters exclude it", async () => {
      const user = userEvent.setup();
      renderWithProviders(<AgentSkillsPicker agent={{ ...BUILTIN, skills: ["s1"] }} />, {
        preloadedState: stateWith(MANY),
      });

      await user.type(screen.getByRole("searchbox", { name: "Search skills" }), "bravo");
      await user.click(screen.getByRole("button", { name: "Testing" }));

      expect(screen.getByRole("button", { name: "Remove Alpha Audit" })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Add Bravo Build" })).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Add Charlie Check" })).not.toBeInTheDocument();
    });
  });

  describe("skill detail dialog", () => {
    function renderOne(skill: GlobalSkillEntry) {
      return renderWithProviders(<AgentSkillsPicker agent={BUILTIN} />, {
        preloadedState: stateWith([skill]),
      });
    }

    it("shows the description and rendered content of the chosen skill", async () => {
      const user = userEvent.setup();
      renderOne(makeSkill("s1", "Alpha Audit", { description: "Audits things", content: "## Steps\n\nDo it." }));

      await user.click(screen.getByRole("button", { name: "View Alpha Audit details" }));

      const dialog = screen.getByRole("dialog", { name: "Alpha Audit details" });
      expect(within(dialog).getByText("Audits things")).toBeInTheDocument();
      expect(within(dialog).getByText("Steps")).toBeInTheDocument();
      expect(within(dialog).getByText("Do it.")).toBeInTheDocument();
      expect(within(dialog).queryByText("No prompt content available.")).not.toBeInTheDocument();
    });

    it("says there is no prompt content when the skill has none", async () => {
      const user = userEvent.setup();
      renderOne(makeSkill("s1", "Alpha Audit", { content: "" }));

      await user.click(screen.getByRole("button", { name: "View Alpha Audit details" }));

      expect(
        within(screen.getByRole("dialog", { name: "Alpha Audit details" })).getByText(
          "No prompt content available.",
        ),
      ).toBeInTheDocument();
    });

    it("omits the description paragraph when the skill has no description", async () => {
      const user = userEvent.setup();
      renderOne(makeSkill("s1", "Alpha Audit", { description: "", content: "Body text" }));

      await user.click(screen.getByRole("button", { name: "View Alpha Audit details" }));

      const dialog = screen.getByRole("dialog", { name: "Alpha Audit details" });
      expect(within(dialog).getByText("Body text")).toBeInTheDocument();
      expect(within(dialog).queryByText("Alpha Audit description")).not.toBeInTheDocument();
    });

    it("closes from the Close button", async () => {
      const user = userEvent.setup();
      renderOne(makeSkill("s1", "Alpha Audit"));
      await user.click(screen.getByRole("button", { name: "View Alpha Audit details" }));

      await user.click(screen.getByRole("button", { name: "Close" }));

      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });

    it("closes on Escape", async () => {
      const user = userEvent.setup();
      renderOne(makeSkill("s1", "Alpha Audit"));
      await user.click(screen.getByRole("button", { name: "View Alpha Audit details" }));

      await user.keyboard("{Escape}");

      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });

    it("closes on a backdrop click but not on a click inside the dialog", async () => {
      const user = userEvent.setup();
      renderOne(makeSkill("s1", "Alpha Audit"));
      await user.click(screen.getByRole("button", { name: "View Alpha Audit details" }));
      const dialog = screen.getByRole("dialog", { name: "Alpha Audit details" });

      await user.click(within(dialog).getByText("Alpha Audit description"));
      expect(screen.getByRole("dialog", { name: "Alpha Audit details" })).toBeInTheDocument();

      // The backdrop is the dialog's only wrapper and exposes no role/label to query.
      await user.click(dialog.parentElement as HTMLElement);
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
  });
});
