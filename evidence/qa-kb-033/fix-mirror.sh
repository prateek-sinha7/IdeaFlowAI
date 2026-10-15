#!/usr/bin/env bash
# QA-KB-033 (ISS-442, ISS-867) fix proof: run the REAL test files under vitest
# against mutated COPIES of page.tsx in a throwaway mirror. Never writes the repo.
# Usage: bash evidence/qa-kb-033/fix-mirror.sh [workdir]   (default: mktemp -d)
#        TESTS_FROM=HEAD bash ...   runs the committed (pre-fix) test files instead
set -u
REPO="${REPO:-$(cd "$(dirname "$0")/../.." && pwd)}"
FE="$REPO/frontend"
VIEW="src/app/[...view]"
WORK="${1:-$(mktemp -d)}"
M="$WORK/mirror"
rm -rf "$M"; mkdir -p "$M/$VIEW" "$M/src/components/layout"
ln -s "$FE/node_modules" "$M/node_modules"
for T in workflowDetailCatch.source.test.ts launchImageAndRecents.source.test.ts; do
  if [ "${TESTS_FROM:-}" = HEAD ]; then git -C "$REPO" show "HEAD:frontend/$VIEW/$T" > "$M/$VIEW/$T"
  else cp "$FE/$VIEW/$T" "$M/$VIEW/"; fi
done
cp "$FE/src/components/layout/DashboardLayout.tsx" "$M/src/components/layout/"
echo "repo: $REPO   test files from: ${TESTS_FROM:-working tree}"
grep -nE 'toBe\(5\)|toBe\(2\)|toBeGreaterThanOrEqual\((5|2)\)' "$M/$VIEW/workflowDetailCatch.source.test.ts" "$M/$VIEW/launchImageAndRecents.source.test.ts" | sed "s#$M/##"

for S in BASE 442-S1 442-S4 442-S2 442-S3 867-S1 867-S4 867-S3; do
  node - "$FE/$VIEW/page.tsx" "$M/$VIEW/page.tsx" "$S" <<'JS'
const fs = require("fs");
const [src, dst, s] = process.argv.slice(2);
const IDIOM = "if (err instanceof ApiError && (err.status === 403 || err.status === 404)) {";
const SPREAD = "...(pending.images && pending.images.length > 0 ? { images: pending.images } : {}),";
const nth = (t, n, k) => { let i = -1; for (let j = 0; j <= k; j++) i = t.indexOf(n, i + 1); return i; };
const swap = (t, n, k, w) => { const i = nth(t, n, k); if (i < 0) throw new Error("no site " + k); return t.slice(0, i) + w + t.slice(i + n.length); };
const addSite = (t) => t + `\ntry { await f(); } catch (err) {\n  ${IDIOM}\n    setSomethingNewDenied(true);\n  }\n}\n`;
const addReader = (t) => t + `\nconst extra = pending.images && pending.images.length > 0 ? pending.images : [];\n`;
const MUT = {
  "BASE": (t) => t,                                              // page.tsx as it is
  "442-S1": addSite,                                             // +1 legitimate narrowed catch (the bug)
  "442-S4": (t) => swap(t, IDIOM, 2, "if (true) {"),             // /edit catch back to swallow-all (must stay red)
  "442-S2": (t) => swap(swap(t, IDIOM, 4, "if (true) {"), IDIOM, 0, "if (true) {"), // /run + canvas undone (must stay red)
  "442-S3": (t) => addSite(swap(t, IDIOM, 2, "if (true) {")),    // S4 + S1 compensating (known ceiling of any count)
  "867-S1": addReader,                                           // +1 legitimate pending.images reader (the bug)
  "867-S4": (t) => swap(t, SPREAD, 1, ""),                       // ppt setter drops its images spread (must stay red)
  "867-S3": (t) => addReader(swap(t, SPREAD, 1, "")),            // S4 + S1 compensating (known ceiling of any count)
};
const out = MUT[s](fs.readFileSync(src, "utf8"));
fs.writeFileSync(dst, out);
const c = (n) => out.split(n).length - 1;
console.log(`== ${s}  idiom=${c(IDIOM)}  guard=${c("pending.images && pending.images.length > 0")}`);
JS
  (cd "$M" && npx vitest run --reporter=verbose 2>&1 | grep -E '^ *(✓|×|Test Files|Tests )' | sed -E 's/ [0-9]+ms$//')
done
