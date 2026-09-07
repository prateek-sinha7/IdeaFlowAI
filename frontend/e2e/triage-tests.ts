#!/usr/bin/env npx tsx
/**
 * Playwright E2E Test Triage Tool
 * 
 * Systematically collects and categorizes all mocked tests,
 * runs them in batches, and captures failure root causes.
 */

import { execSync } from "child_process";
import fs from "fs";
import path from "path";

const TESTS_DIR = path.join(__dirname, "tests");
const _REPORT_FILE = path.join(__dirname, "triage-report.json");

interface TestCase {
  file: string;
  title: string;
  fullName: string;
  status?: "passed" | "failed" | "skipped" | "unknown";
  error?: string;
  rootCause?: "selector" | "timing" | "fixture" | "mock" | "product" | "other";
}

interface _TriageReport {
  timestamp: string;
  totalTests: number;
  passed: number;
  failed: number;
  skipped: number;
  failures: { [key: string]: { rootCause: string; error: string } };
}

function collectTests(): TestCase[] {
  const tests: TestCase[] = [];
  const files = fs
    .readdirSync(TESTS_DIR)
    .filter((f) => f.endsWith(".spec.ts") && !f.endsWith(".live.spec.ts"));

  for (const file of files) {
    const content = fs.readFileSync(path.join(TESTS_DIR, file), "utf-8");
    const testMatches = content.match(/^\s*test\s*\(\s*[`'"](.*?)['"`]/gm) || [];

    for (const match of testMatches) {
      const titleMatch = match.match(/[`'"](.*?)[`'"]/);
      if (titleMatch) {
        tests.push({
          file,
          title: titleMatch[1],
          fullName: `${file}#${titleMatch[1]}`,
        });
      }
    }
  }

  return tests;
}

function runBatchTests(testPatterns: string[]): void {
  for (const pattern of testPatterns) {
    try {
      console.log(`\n\n=== Running: ${pattern} ===`);
      const cmd = `npm run e2e -- --project=mocked --grep="${pattern}" --workers=1`;
      const output = execSync(cmd, { stdio: "pipe", encoding: "utf-8" });
      console.log(output);
    } catch (e) {
      if (e instanceof Error) {
        console.error(`Failed: ${e.message}`);
      }
    }
  }
}

function _categorizeFailure(output: string): string {
  if (output.includes("getByRole") || output.includes("locator")) {
    return "selector";
  }
  if (output.includes("Timeout") || output.includes("timeout")) {
    return "timing";
  }
  if (output.includes("fixture") || output.includes("MockApi") || output.includes("MockSse")) {
    return "fixture";
  }
  if (output.includes("Mock")) {
    return "mock";
  }
  return "other";
}

async function main() {
  console.log("Collecting all mocked tests...");
  const tests = collectTests();
  console.log(`Found ${tests.length} tests across ${new Set(tests.map((t) => t.file)).size} files`);

  // Get unique test file patterns
  const patterns = [...new Set(tests.map((t) => t.file.replace(".spec.ts", "")))];

  console.log(`\nRunning ${patterns.length} test files in batches...`);
  runBatchTests(patterns);
}

main().catch(console.error);
