# Feature: Library

A read-only catalogue of the platform's capabilities: agents, skills and hooks.

**Routes:** `/library`, `/library?tab=skills`, `/library?tab=hooks`,
`/library/agents/{slug}`, `/library/skills/{slug}`, `/library/hooks/{slug}`
**Screenshots:** `06-library/` — p35 agents, p36 skills, p37 hooks, p38–p40 drawers · `13-states/62` dark
**Source:** `frontend/src/components/library/LibraryPage.tsx`

---

## Structure

**H1** "Library", subtitle
`93 agents · 186 skills · 8 hooks · tap any item to see its capabilities`.

**Three tabs**, each with a live count badge:
`Agents 93` (`tab-agents`), `Skills 186` (`tab-skills`), `Hooks 8` (`tab-hooks`).

The tab is a **query param, not a path segment** — a post-close amendment to spec
015 (2026-08-21) collapsed three list screens into one. `routes.library()` omits
`tab` when it is `agents` and omits `category` when it is `all`, so the default
state has a clean URL. The legacy two-segment shapes (`/library/agents` with no
slug) are intercepted by `next.config.ts` redirects before they reach the parser.

**Search:** `input[name="library-search"]`.

**Category pills** change per tab:

| Tab | Categories |
|---|---|
| Agents | All 93, App Builder 15, Retry Loop 0, Language Branch 0, Spanish Greeter 0, Dutch Greeter 0, Workflow Handoff 0, Human Handoff 0, PPT 3, PPT v2 2, Prototype 5, User Stories 6, Custom 10, Human Gate 0 |
| Skills | All, Collaboration, Creative, Debugging, Planning, Research, Security, Specialist, Testing, Workflow |
| Hooks | All, PostToolUse, PreToolUse, SessionStart, Stop |

**Seven agent categories have a count of zero** — every one of them a spec-014
conditional-gate fixture. Half the agent filters on this page are dead. See D-04.

**Cards.** `.bg-surface-card`, or more precisely `div.cursor-pointer.p-4` — the
latter matches exactly the item count, the former over-matches (107 elements for
93 agents; 196 for 186 skills; 13 for 8 hooks) because the class is shared with
layout chrome. **Use `div.cursor-pointer.p-4`.**

An agent card shows: name, category badge, role, description, `~Ns` estimate, and a
`Configure →` affordance. Skill and hook cards navigate on a card click; **agent
cards navigate only from `Configure →`** — clicking the card body does nothing.

---

## Detail views

All three open as an in-page drawer beside the still-visible list, push a URL, and
carry `[role="dialog"] = 0` — they are **not** modals.

**Agent** (`/library/agents/{slug}`, testid `agent-drawer`): H2 the display name,
tabs `Overview` (`tab-overview`), `Skills`, `Hooks`, `Config` (`tab-config`), and a
`System Prompt Base AGENT.md prompt` control.

The slug is the agent **id**, which is not always guessable from the name —
`/library/agents/material-analyzer` is "Architecture Agent". That is correct
(`backend/agents/prompts/material-analyzer/AGENT.md` declares `id: material-analyzer`,
`name: Architecture Agent`), just legacy.

**Skill** (`/library/skills/{slug}`): H2 the skill name, then the rendered skill
document as H3 sections — `WHEN TO USE`, `CORE CONCEPTS`, `HOW IT WORKS`,
`CROSS-PLATFORM MAPPING`, `EXAMPLES`, `ANTI-PATTERNS TO AVOID`,
`BEST PRACTICES CHECKLIST`, `REFERENCES`, `RELATED SKILLS`. Plus `Copy content`.
Section set varies by skill — do not assert a fixed list.

**Hook** (`/library/hooks/{slug}`): H2 the hook name, plus `Copy`.

---

```gherkin
Feature: The capability library

  Background:
    Given I am signed in as "qa-admin@flowinqa.com"

  Scenario: The library opens on Agents by default
    When I cold-load "/library"
    Then I see the heading "Library"
    And the subtitle reports the agent, skill and hook counts
    And the "Agents" tab is selected
    And the URL has no "tab" parameter
    # routes.library() omits tab when it is the default. Assert the clean URL.

  Scenario Outline: Each tab is addressable by query param
    When I cold-load "/library?tab=<tab>"
    Then the "<label>" tab is selected
    And the visible cards are <kind>

    Examples:
      | tab    | label      | kind   |
      | skills | Skills 186 | skills |
      | hooks  | Hooks 8    | hooks  |

  Scenario: Tab badge counts agree with the rendered cards
    When I cold-load "/library"
    Then the number of agent cards equals the count in the "Agents" tab badge
    When I switch to Skills
    Then the number of skill cards equals the count in the "Skills" tab badge
    When I switch to Hooks
    Then the number of hook cards equals the count in the "Hooks" tab badge
    # Count cards with `div.cursor-pointer.p-4`. `.bg-surface-card` over-matches
    # — it also hits layout chrome (107 elements for 93 agents).

  Scenario: Switching a tab updates the URL
    When I cold-load "/library"
    And I click the second tab
    Then the URL becomes "/library?tab=skills"
    When I press browser Back
    Then I am back on the Agents tab
    # Quirk `libraryTabBadgeFormatting`: tab labels carry their count
    # ("Agents  93"), so an exact-text click fails. Use [role="tab"]:nth-child(N).

  Scenario: Category counts sum to the All count
    When I cold-load "/library"
    Then the "All" pill's count equals the total agent count
    And the sum of the other category counts equals the "All" count

  Scenario: Filtering by category narrows the grid
    When I cold-load "/library"
    And I click the category "App Builder"
    Then the visible card count equals that category's badge count
    And every visible card carries the "APP BUILDER" badge

  Scenario: The category is addressable by URL
    When I cold-load "/library?category=ppt"
    Then that category is applied on a cold load
    And the URL keeps the category parameter
    # routes.library() omits category when it is "all" — so the default is clean
    # and a non-default is explicit.

  @defect
  # D-04 / ISS-187. Seven of the fourteen agent categories are spec-014 test
  # fixtures with no agents behind them. Recorded as current behaviour.
  Scenario: Seven agent categories are empty test fixtures
    When I cold-load "/library"
    Then I see the category pills "Retry Loop", "Language Branch", "Spanish Greeter", "Dutch Greeter", "Workflow Handoff", "Human Handoff", "Human Gate"
    And each of those pills reports a count of 0
    When I click "Retry Loop"
    Then no cards are shown

  Scenario: Search filters the current tab
    When I cold-load "/library"
    And I type "architecture" into the library search
    Then every visible card matches "architecture", case-insensitively
    When I clear the search
    Then the full grid returns

  Scenario: Search is scoped to the active tab
    When I cold-load "/library?tab=skills"
    And I type a term that matches an AGENT but no skill
    Then no cards are shown
    And the Skills tab is still selected

  Scenario: An agent opens from its Configure affordance, not its card body
    When I cold-load "/library"
    And I click the card body of the first agent
    Then the URL is unchanged
    When I click that card's "Configure →"
    Then the URL becomes "/library/agents/{id}"
    And a drawer opens showing that agent's name
    # Agent cards differ from skill and hook cards, which DO navigate on a body
    # click. Do not share a page-object method across the three.

  Scenario: An agent's drawer exposes its configuration tabs
    When I cold-load "/library/agents/material-analyzer"
    Then a drawer with testid "agent-drawer" is shown
    And its heading reads "Architecture Agent"
    And I see the tabs "Overview", "Skills", "Hooks", "Config"
    And I see a control to view the base AGENT.md prompt
    # The slug is the agent ID and need not resemble the name.
    # material-analyzer IS Architecture Agent — verified against
    # backend/agents/prompts/material-analyzer/AGENT.md.

  Scenario Outline: Each agent drawer tab shows its own content
    When I cold-load "/library/agents/{slug}"
    And I click the drawer tab "<tab>"
    Then that panel's content is shown

    Examples:
      | tab      |
      | Overview |
      | Skills   |
      | Hooks    |
      | Config   |

  Scenario: A skill opens from a card click and renders its document
    When I cold-load "/library?tab=skills"
    And I click the first skill card
    Then the URL becomes "/library/skills/{id}"
    And I see the skill's name as a heading
    And I see a "WHEN TO USE" section
    And I see a "Copy content" control
    # Section headings vary by skill. Assert on WHEN TO USE, which every skill
    # has, not on the full list.

  Scenario: A hook opens from a card click
    When I cold-load "/library?tab=hooks"
    And I click the first hook card
    Then the URL becomes "/library/hooks/{id}"
    And I see the hook's name as a heading
    And I see a "Copy" control

  Scenario: Hook categories are lifecycle events
    When I cold-load "/library?tab=hooks"
    Then the category pills are "All", "PostToolUse", "PreToolUse", "SessionStart", "Stop"

  Scenario: A detail view is a drawer, not a modal
    When I cold-load "/library/skills/{slug}"
    Then the list behind the drawer is still rendered
    And no element with role "dialog" is present
    And the tab badges are still visible

  Scenario: Closing a detail returns to the list URL
    Given I am on "/library/agents/{slug}"
    When I close the drawer
    Then I return to the library list
    And the tab I came from is still selected

  Scenario: Deep-linking a detail view works cold
    When I cold-load "/library/hooks/post-design-quality"
    Then that hook's drawer is open
    And the Hooks tab is selected behind it
    # A shared link must land on the right item AND the right tab.

  Scenario: The library is read-only
    When I cold-load "/library"
    Then no control offers to create, edit or delete an agent, skill or hook
```

## Notes for phase 2

- **Card selector: `div.cursor-pointer.p-4`.** `.bg-surface-card` is what the old
  browser definition recommended and it over-counts by 10–14 elements per tab.
- Tab clicks need `[role="tab"]:nth-child(N)` — the labels include their count
  badge, so exact-text matching fails.
- The counts (93/186/8) are derived from what is on disk. Assert badge-to-card
  agreement, not the literal numbers.
- Agent slugs are ids, not names. Read them from the list before deep-linking, or
  from `backend/agents/prompts/*/AGENT.md`.
