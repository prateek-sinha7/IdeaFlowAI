import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { computeDraftState, manifestAsPassthrough } from "@/lib/builderDraft";
import { canonicalize } from "@/lib/canonicalManifest";
import type { WorkflowManifest } from "@/types/index";

import { buildWorkflowManifest, compiledRootIds } from "./userWorkflows";

// Task 22.9: render each per-pattern draft through the composer mapping, build the
// Save payload with no edits, and compare it with the payload that the skill's
// `export_manifest.py --save-payload` wrote (fixtures made by task 22.8).
// **Validates: Requirements 10.9, 49.8**

const FIXTURE_DIR = path.join(__dirname, "__fixtures__", "builder-patterns");

/** Allowed patterns: `patterns.md` sections 1 to 18 and 21. */
const EXPECTED_PATTERNS = [...Array.from({ length: 18 }, (_, i) => i + 1), 21];

interface IndexEntry {
  pattern: number;
  slug: string;
  title: string;
  trust: string;
  manifest: string;
  payload: string;
}

interface ExpectedPayload {
  name: string;
  description: string;
  base_pipeline_type: string;
  agent_ids: string[];
  manifest: Record<string, unknown>;
}

/** Read a fixture as JSON. JSON.parse accepts LF and CRLF alike, so a checkout with
 *  `core.autocrlf=true` cannot change what the test sees. */
function readJson<T>(file: string): T {
  return JSON.parse(readFileSync(path.join(FIXTURE_DIR, file), "utf8")) as T;
}

const { fixtures } = readJson<{ fixtures: IndexEntry[] }>("index.json");

/** Apply an unedited draft to the composer state and build the Save payload. */
function renderAndSave(draft: WorkflowManifest) {
  const state = computeDraftState(draft);
  const manifest = buildWorkflowManifest(
    state.pipelineAgents,
    state.capabilities,
    state.selections,
    state.runConfig,
    manifestAsPassthrough(draft),
  );
  return {
    base_pipeline_type: "custom" as const,
    agent_ids: compiledRootIds(manifest),
    manifest,
  };
}

/**
 * Patterns whose saved manifest differs from the expected payload today. The strict
 * test for these patterns is marked `it.fails`, so it turns red (and the entry must be
 * deleted) as soon as the mapping is fixed. None today.
 */
const KNOWN_DEVIATIONS: ReadonlySet<number> = new Set<number>();

describe("builder pattern fixtures", () => {
  it("lists one fixture for every allowed pattern", () => {
    expect(fixtures.map((f) => f.pattern)).toEqual(EXPECTED_PATTERNS);
  });

  for (const entry of fixtures) {
    const run = KNOWN_DEVIATIONS.has(entry.pattern) ? it.fails : it;
    run(`pattern ${entry.pattern} (${entry.slug}): saves the unedited draft as the expected payload`, () => {
      const draft = readJson<WorkflowManifest>(entry.manifest);
      const expected = readJson<ExpectedPayload>(entry.payload);

      const saved = renderAndSave(draft);

      expect(saved.base_pipeline_type).toBe(expected.base_pipeline_type);
      expect(saved.agent_ids).toEqual(expected.agent_ids);
      expect(canonicalize({ ...saved.manifest })).toEqual(canonicalize(expected.manifest));
    });
  }
});
