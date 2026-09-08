/**
 * Playwright Test Collection Without Browser Installation
 *
 * Lists all Playwright test identities (spec file, test name, classification)
 * without requiring a full browser installation. Used for inventory validation
 * and split-proof generation.
 *
 * Usage: node --loader ts-node/esm ci/collect-playwright-identities.ts
 *        or: npx ts-node ci/collect-playwright-identities.ts
 *
 * Requirements: 2.2, 2.3, 2.4, 3.1, 3.5, 3.6, 3.7
 */

import * as fs from 'fs';
import * as path from 'path';

const PROJECT_ROOT = process.cwd();

interface PlaywrightTestNode {
  nodeId: string;
  specFile: string;
  testName: string;
  classification: 'mocked' | 'live_only';
}

interface PlaywrightInventory {
  mocked: PlaywrightTestNode[];
  live_only: PlaywrightTestNode[];
  totalCount: number;
  digest: string;
}

/**
 * Parse a Playwright spec file to extract test names.
 * Looks for test(...) and it(...) calls.
 */
function extractTestNamesFromFile(filePath: string): string[] {
  try {
    const content = fs.readFileSync(filePath, 'utf8');
    const testNames: string[] = [];

    // Match test(...) or it(...) calls
    // Simplified regex: looks for test( or it( followed by a string
    const testRegex = /(?:test|it)\s*\(\s*['"](.*?)['"]/g;
    let match;

    while ((match = testRegex.exec(content)) !== null) {
      testNames.push(match[1]);
    }

    return testNames;
  } catch (err) {
    console.error(`Failed to parse ${filePath}:`, err);
    return [];
  }
}

/**
 * Classify a spec file as mocked or live_only based on filename.
 */
function classifySpec(
  specFile: string
): 'mocked' | 'live_only' {
  if (specFile.includes('.live.spec.ts')) {
    return 'live_only';
  }
  return 'mocked';
}

/**
 * Collect all Playwright test identities from the e2e/tests directory.
 */
function collectPlaywrightTests(): PlaywrightInventory {
  const testDir = path.join(PROJECT_ROOT, 'e2e', 'tests');
  const mocked: PlaywrightTestNode[] = [];
  const live_only: PlaywrightTestNode[] = [];

  // Recursively find all .spec.ts files
  function walkDir(dir: string): void {
    try {
      const entries = fs.readdirSync(dir, { withFileTypes: true });

      for (const entry of entries) {
        const fullPath = path.join(dir, entry.name);

        if (entry.isDirectory()) {
          walkDir(fullPath);
        } else if (entry.name.endsWith('.spec.ts')) {
          // Extract relative path for reporting
          const relPath = path.relative(testDir, fullPath);
          const specFile = path.normalize(relPath);
          const classification = classifySpec(specFile);

          // Extract test names
          const testNames = extractTestNamesFromFile(fullPath);

          for (const testName of testNames) {
            const nodeId = `${specFile}::${testName}`;
            const node: PlaywrightTestNode = {
              nodeId,
              specFile,
              testName,
              classification,
            };

            if (classification === 'mocked') {
              mocked.push(node);
            } else {
              live_only.push(node);
            }
          }
        }
      }
    } catch (err) {
      console.error(`Error walking directory ${dir}:`, err);
    }
  }

  // Start collection
  walkDir(testDir);

  // Compute digest (SHA-256 would be ideal, but for simplicity use base64)
  const allNodeIds = [
    ...mocked.map((n) => n.nodeId),
    ...live_only.map((n) => n.nodeId),
  ].sort();
  const digest = Buffer.from(allNodeIds.join('|')).toString('base64');

  return {
    mocked,
    live_only,
    totalCount: mocked.length + live_only.length,
    digest,
  };
}

/**
 * Validate inventory properties.
 */
function validateInventory(inventory: PlaywrightInventory): string[] {
  const errors: string[] = [];

  // Check for overlaps by comparing arrays
  const mockedIds = inventory.mocked.map((n) => n.nodeId);
  const liveIds = new Set(inventory.live_only.map((n) => n.nodeId));

  const overlap: string[] = [];
  for (const id of mockedIds) {
    if (liveIds.has(id)) {
      overlap.push(id);
    }
  }
  if (overlap.length > 0) {
    errors.push(
      `Mocked and live-only classifications overlap: ${overlap.join(', ')}`
    );
  }

  // Check that counts are non-empty for mandatory
  if (mockedIds.length === 0) {
    errors.push('Mocked test set is empty');
  }

  return errors;
}

/**
 * Output inventory in JSON format.
 */
function main(): void {
  const inventory = collectPlaywrightTests();
  const errors = validateInventory(inventory);

  if (errors.length > 0) {
    console.error('Inventory validation errors:');
    errors.forEach((e) => console.error(`  - ${e}`));
    process.exit(1);
  }

  // Output to stdout as JSON
  console.log(JSON.stringify(inventory, null, 2));
}

// Run collection
main();
