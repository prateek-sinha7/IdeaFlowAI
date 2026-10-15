#!/usr/bin/env bash
# QA-KB-085 analyzer: every frontend test that ends a source slice at a hook dependency list, and how many times
# that literal occurs in the file it slices. Run from the repo root. Read-only.
cd frontend/src
echo "## tests that anchor on a dependency list (grep)"
grep -rn --include='*.test.ts' --include='*.test.tsx' -E 'endMarker = "\}, \[|depsMarker =|indexOf\("\}, \[|^\s+"\}, \[viewPathKey' . | cut -c1-170
echo
echo "## occurrences of each literal in the file it slices (grep -c -F)"
P='app/[...view]/page.tsx'; W=components/history/WorkflowHistory.tsx; D=components/layout/DashboardLayout.tsx
c() { printf '%-3s x  %s :: %s\n' "$(grep -c -F -- "$2" "$1")" "$1" "$2"; }
c "$D" '}, [contentSourceRunId]);'                     # runTabShallowNav.test.ts:29  (the bug; the only hit left is the WRONG one, L737)
c "$P" '}, [router, dispatch]);'                       # authEffectGuard.iss844.source.test.ts:35 (2 hits: intended L960 + decoy L3440)
c "$W" '}, [onOpenRun]);'                              # page.iss856.test.tsx:65
c "$P" '[recentRuns, runConnection, seedRunChatTranscript, handleWebSocketMessage],'   # page.iss657.test.tsx:42
c "$P" '}, [viewPathKey, isAuthenticated, handleSelectWorkflowRun, runTabDeepLink.requestOpenTab]);'  # runViewEffects.qaSg004 T7
c "$P" '}, [viewPathKey, isAuthenticated, handleSelectWorkflowRun]);'                  # runViewEffects.qaSg004 T11
c "$P" '[runStore.viewed.pipelineState.pipelineRunId, resetPipeline, setWaveGroups, handleWebSocketMessage, setSubmittedBrief, seedRunChatTranscript, runConnection]'  # page.qaSg004.test.tsx:113
echo
echo "## where the two '}, [router, dispatch]);' hits are"
grep -n -F '}, [router, dispatch]);' "$P"
grep -n -F '// Auth check on mount' "$P"
