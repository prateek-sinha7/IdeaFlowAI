QA-KB-110 / ISS-1154 analysis probe (vitest + jsdom, offline, no server, no browser, no run launched).

Files
  qa-kb-110.probe.test.tsx   the probe; imports the REAL DashboardLayout and routes.ts, slices
                             initialMainViewFor / initialWorkflowTypeFor / wizardModeFor out of page.tsx
  vitest.probe.config.ts     collects only the probe; QA_KB_110_MUTATE=1 applies two anchored string
                             replacements to DashboardLayout.tsx IN MEMORY (the file is never written)

It lives outside frontend/src on purpose, so it is not part of the repo's test suite and the repo's own
vitest include glob is unchanged. To run it, give the directory a node_modules that resolves to the
frontend's, in a scratch copy (do not commit the symlink):

  mkdir /tmp/qa-kb-110 && cp qa-kb-110.probe.test.tsx vitest.probe.config.ts /tmp/qa-kb-110/
  ln -s <repo>/frontend/node_modules /tmp/qa-kb-110/node_modules
  cd /tmp/qa-kb-110
  export QA_KB_110_FRONTEND=<repo>/frontend VITE_CONFIG_NATIVE_IGNORE_WARNING=true
  ./node_modules/.bin/vitest run --config vitest.probe.config.ts --reporter=verbose                       # today
  QA_KB_110_MUTATE=1 ./node_modules/.bin/vitest run --config vitest.probe.config.ts --reporter=verbose    # candidate-fix shape

Observed outputs: ../analysis-01-probe-remount-loses-pendinghomebrief.txt (today) and
../analysis-02-mutation-one-shot-draft-for-non-wizard-destinations.txt (candidate-fix shape).
