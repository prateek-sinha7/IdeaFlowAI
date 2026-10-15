#!/bin/sh
# QA-KB-122 analysis (3-analyzer, 2026-10-09): when did the e2e tier last agree with the app,
# and which intentional app changes landed afterwards without touching it?
# Read-only git queries. Run from the repo root:  sh evidence/qa-kb-122/analysis-01-git-timeline.sh
set -u
echo "== last repair of the offline e2e tier, and the merge that brought the Cognito cut-over in the day after"
git log -1 --format='%h %ad %s' --date=short 14ce62c59
git log -1 --format='%h %ad %s' --date=short 1d95275b4
git merge-base --is-ancestor b2a621f84 14ce62c59 && echo "b2a621f84 IS an ancestor of 14ce62c59" || echo "b2a621f84 is NOT an ancestor of 14ce62c59 (the repair sweep ran on a tree without the cut-over)"
git merge-base --is-ancestor b2a621f84 1d95275b4 && echo "b2a621f84 IS an ancestor of 1d95275b4 (the 2026-09-23 merge)"
echo
echo "== intentional app changes: date, subject, and how many tests/integration/e2e files each touched"
for c in b2a621f84 f9df3737c 911547c7d 87903ab3b 5336d910c; do
  n=$(git show --name-only --format='' "$c" | grep -c '^tests/integration/e2e')
  t=$(git show --name-only --format='' "$c" | grep -c .)
  printf '%s  %s  e2e files touched: %s of %s   %s\n' "$c" "$(git log -1 --format=%ad --date=short "$c")" "$n" "$t" "$(git log -1 --format=%s "$c" | cut -c1-90)"
done
echo
echo "== the unit-tier twin each of them DID update in the same commit"
git show --name-only --format='' 911547c7d | grep -E 'CanvasConfigRail.dataTab.test|stepKind.ts'
git show --name-only --format='' f9df3737c | grep -E 'test_run_sandbox_api|SandboxTab.test'
git show --name-only --format='' b2a621f84 | grep -E 'admin.reskin.test'
echo
echo "== QA-KB-060 closed 2026-10-07: it flipped the unit-tier it.fails to it(), and touched no e2e file"
git show --name-only --format='%h %s' 32cfcf599 | sed 's/^/   /'
echo
echo "== no CI job or pre-commit hook references the e2e tier (empty output below = no reference)"
grep -n -E 'tests/integration|integration/e2e|run-all-offline' .github/workflows/*.yml .pre-commit-config.yaml 2>/dev/null
echo "(end)"
