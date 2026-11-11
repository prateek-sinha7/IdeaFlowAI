import fc from "fast-check";
import { describe, expect, it } from "vitest";

import { withConnectorTools, withToolGrant, withToolSets, type StepSelection } from "@/components/workflow/AgentsPopup";
import type { ManifestStep } from "@/types/index";

import {
  agentsToManifestSteps,
  manifestStepsToAgents,
  manifestStepsToGateSelections,
} from "./userWorkflows";

// Connected Apps persistence (design 4.5): the connector grant survives
// load -> save, and the shared grant writers never lose a sibling key.

const PROPERTY_OPTIONS = { seed: 20260514, numRuns: 100 } as const;

const TOOL_NAMES = [
  "jira__search_issues",
  "jira__get_issue",
  "jira__add_comment",
  "github__get_issue",
  "github__create_pull_request",
] as const;
const PACKS = ["file_extract", "playwright"] as const;

const namesArb = fc.uniqueArray(fc.constantFrom(...TOOL_NAMES), { maxLength: TOOL_NAMES.length });
const packsArb = fc.uniqueArray(fc.constantFrom(...PACKS), { maxLength: PACKS.length });

const stepArb: fc.Arbitrary<ManifestStep> = fc
  .record({
    read: fc.option(fc.boolean(), { nil: undefined }),
    write: fc.option(fc.boolean(), { nil: undefined }),
    packs: packsArb,
    connectors: fc.option(namesArb, { nil: undefined }),
  })
  .map(({ read, write, packs, connectors }) => ({
    agent: "custom-agent",
    instance_id: "writer",
    name: "Writer",
    prompt: "Write.",
    tools: {
      ...(read === undefined ? {} : { read_files: read }),
      ...(write === undefined ? {} : { write_files: write }),
      ...(packs.length > 0 ? { tool_sets: packs } : {}),
      ...(connectors === undefined ? {} : { connectors }),
    },
  }));

const selectionArb: fc.Arbitrary<StepSelection> = fc
  .record({
    read: fc.option(fc.boolean(), { nil: undefined }),
    write: fc.option(fc.boolean(), { nil: undefined }),
    packs: packsArb,
    connectors: namesArb,
  })
  .map(({ read, write, packs, connectors }) => ({
    tools: {
      ...(read === undefined ? {} : { read_files: read }),
      ...(write === undefined ? {} : { write_files: write }),
      ...(packs.length > 0 ? { tool_sets: packs } : {}),
      ...(connectors.length > 0 ? { connectors } : {}),
    },
  }));

describe("connectors round trip (load then save)", () => {
  it("saves exactly the connector names the step was loaded with", () => {
    fc.assert(
      fc.property(stepArb, (step) => {
        const [saved] = agentsToManifestSteps(manifestStepsToAgents([step]), manifestStepsToGateSelections([step]));

        const expected = step.tools?.connectors ?? [];
        if (expected.length === 0) expect(saved.tools).not.toHaveProperty("connectors");
        else expect(saved.tools?.connectors).toEqual(expected);
      }),
      PROPERTY_OPTIONS,
    );
  });

  it("saves exactly the selection's names, whatever the loaded step carried", () => {
    fc.assert(
      fc.property(stepArb, namesArb, (step, edited) => {
        const selections = manifestStepsToGateSelections([step]);
        const next = withConnectorTools(selections.writer, edited);

        const [saved] = agentsToManifestSteps(manifestStepsToAgents([step]), { writer: { tools: next } });

        if (edited.length === 0) expect(saved.tools).not.toHaveProperty("connectors");
        else expect(saved.tools?.connectors).toEqual(edited);
      }),
      PROPERTY_OPTIONS,
    );
  });

  it("keeps the pack list and file grants of the loaded step", () => {
    fc.assert(
      fc.property(stepArb, (step) => {
        const [saved] = agentsToManifestSteps(manifestStepsToAgents([step]), manifestStepsToGateSelections([step]));

        expect(saved.tools?.tool_sets).toEqual(step.tools?.tool_sets);
        expect(saved.tools?.read_files).toBe(step.tools?.read_files ?? true);
        expect(saved.tools?.write_files).toBe(step.tools?.write_files ?? true);
      }),
      PROPERTY_OPTIONS,
    );
  });
});

describe("shared tool-grant writers", () => {
  it("withToolSets keeps connectors and file grants while replacing the packs", () => {
    fc.assert(
      fc.property(selectionArb, packsArb, (sel, packs) => {
        const next = withToolSets(sel, packs);

        expect(next.connectors).toEqual(sel.tools?.connectors);
        expect(next.read_files).toBe(sel.tools?.read_files ?? true);
        expect(next.write_files).toBe(sel.tools?.write_files ?? true);
        if (packs.length === 0) expect(next).not.toHaveProperty("tool_sets");
        else expect(next.tool_sets).toEqual(packs);
      }),
      PROPERTY_OPTIONS,
    );
  });

  it("withConnectorTools keeps packs and file grants while replacing the names", () => {
    fc.assert(
      fc.property(selectionArb, namesArb, (sel, names) => {
        const next = withConnectorTools(sel, names);

        expect(next.tool_sets).toEqual(sel.tools?.tool_sets);
        expect(next.read_files).toBe(sel.tools?.read_files ?? true);
        expect(next.write_files).toBe(sel.tools?.write_files ?? true);
        if (names.length === 0) expect(next).not.toHaveProperty("connectors");
        else expect(next.connectors).toEqual(names);
      }),
      PROPERTY_OPTIONS,
    );
  });

  it("withToolGrant keeps connectors", () => {
    fc.assert(
      fc.property(selectionArb, fc.boolean(), (sel, on) => {
        expect(withToolGrant(sel, "write_files", on).connectors).toEqual(sel.tools?.connectors);
      }),
      PROPERTY_OPTIONS,
    );
  });

  it("does not mutate the selection it was given", () => {
    fc.assert(
      fc.property(selectionArb, namesArb, packsArb, (sel, names, packs) => {
        const before = structuredClone(sel);

        withConnectorTools(sel, names);
        withToolSets(sel, packs);

        expect(sel).toEqual(before);
      }),
      PROPERTY_OPTIONS,
    );
  });
});
