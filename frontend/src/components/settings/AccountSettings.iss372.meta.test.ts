/**
 * ISS-945 (QA-KB-087) — meta-lock over AccountSettings.iss372.test.tsx.
 * The ISS-921 case waits on `fetch`, but the file's own getConstitution mock never calls it,
 * so the case times out whatever the app does and hides under it.fails. Each case is
 * `it.fails`: red today; the runner flags it once the test file is fixed.
 */
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const src = readFileSync(resolve(__dirname, "AccountSettings.iss372.test.tsx"), "utf8");

describe("ISS-945 — ISS-921 Constitution case is a valid proof", () => {
  it("does not wait on a fetch its own getConstitution mock never makes", () => {
    const stale =
      /getConstitution:\s*\(\)\s*=>\s*Promise\.resolve/.test(src) &&
      /waitFor\(\(\)\s*=>\s*expect\(fetch\)\.toHaveBeenCalled\(\)\)/.test(src);
    expect(stale).toBe(false);
  });

  it("is a plain it(), so it can prove ISS-921", () => {
    expect(src).not.toMatch(/it\.fails\(\s*"reports dirty after the Constitution draft is edited/);
  });
});
