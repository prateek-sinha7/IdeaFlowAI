import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { canonicalHash, canonicalize, canonicalJson } from "./canonicalManifest";

interface CanonicalCase {
  name: string;
  manifest: Record<string, unknown>;
  expected: Record<string, unknown>;
  expected_json: string;
  expected_hash: string;
}

// Read with JSON.parse, not a JSON import: the bundler turns a "__proto__" key
// into a prototype assignment, while JSON.parse keeps it as plain data.
const { cases } = JSON.parse(
  readFileSync(path.join(__dirname, "canonicalManifest.cases.json"), "utf-8"),
) as { cases: CanonicalCase[] };

// Parity suite: backend/tests/contract/test_canonical_manifest_parity.py reads
// the same cases file, so the two implementations cannot drift apart.
describe("canonicalManifest shared cases", () => {
  it("has unique, non-empty case names", () => {
    const names = cases.map((testCase) => testCase.name);
    expect(names.length).toBeGreaterThan(0);
    expect(new Set(names).size).toBe(names.length);
  });

  it.each(cases)(
    "has a self-consistent expectation: $name",
    ({ expected, expected_json, expected_hash }) => {
      expect(JSON.parse(expected_json)).toEqual(expected);
      const digest = createHash("sha256").update(expected_json, "utf8").digest("hex");
      expect(expected_hash).toBe(digest);
    },
  );

  it.each(cases)("matches the Python output: $name", async (testCase) => {
    expect(canonicalize(testCase.manifest)).toEqual(testCase.expected);
    expect(canonicalJson(testCase.manifest)).toBe(testCase.expected_json);
    const hash = await canonicalHash(testCase.manifest);
    expect(hash).toMatch(/^[0-9a-f]{64}$/);
    expect(hash).toBe(testCase.expected_hash);
  });

  it("does not modify its input", () => {
    const manifest = { steps: [{ agent: "a", gates: [], note: null }] };
    const before = JSON.stringify(manifest);
    canonicalize(manifest);
    expect(JSON.stringify(manifest)).toBe(before);
  });

  it("rejects NaN and infinity", () => {
    expect(() => canonicalJson({ n: Number.NaN })).toThrow();
    expect(() => canonicalJson({ n: Number.POSITIVE_INFINITY })).toThrow();
  });
});
