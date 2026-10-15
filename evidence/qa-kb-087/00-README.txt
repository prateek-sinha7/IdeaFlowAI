QA-KB-087 analysis evidence (3-analyzer, 2026-10-02). No repo file was edited: every variant ran from a scratch directory.

Files
  01-analyze-official-file-run.txt          the official AccountSettings.iss372.test.tsx run in place: 3 passed | 1 expected fail
  02-analyze-scratch-runs.txt               scratch variants A-H (reproduction, proposed fix, alternative fix, mutants)
  03-analyze-mutant-kill-rate-and-act-flush.txt   how reliably a non-empty saved constitution catches the mutant, with and without an act() flush
  04-analyze-eslint-trap.txt                deleting :83 alone leaves an unused waitFor import = eslint error, exit 1
  05-analyze-code-quotes.txt                exact file:line quotes and the blast-radius greps
  06-analyze-meta-test-regex-check.txt      the two suggested meta-lock predicates: true on the official file, false on both fix variants
  07-analyze-itfails-scan.txt               every frontend test file that uses it.fails (26 files, 52 xfail cases) run with the marker removed: where each case really fails, and the classification
  08-analyze-itfails-wrong-reason-probes.txt  the probes behind ISS-1039 / ISS-1040 / ISS-1041 (fix variants that go green, the StrictMode effect trace, the pre-fix experiment)
  scratch/                                  the generator, the config, the runners and every variant, stored as .txt so nothing here is collected by vitest, tsc or eslint
  scratch/dbg/                              the in-place-resolution config and the ArtifactVersionPicker / LibraryPage / IntegrationsCard probe files
  scratch/scan_*.py.txt, scan_results.jsonl.txt   the it.fails scan: mirror builder, runner, failure-site printer, raw results

Reproduce (needs frontend/node_modules; edit SCR in make_variants.py / the runners if the scratch dir moves)
  1. mkdir <scratch> && cd <scratch> && ln -s <repo>/frontend/node_modules node_modules
  2. copy scratch/vitest.config.mts.txt -> vitest.config.mts (set root to <scratch>), scratch/make_variants.py.txt -> make_variants.py
  3. python3 make_variants.py            writes a1_asis ... h1_real_sources and AccountSettingsMutant.tsx from the official files
  4. copy run_all.sh / repeat.sh / stress.sh (drop the .txt) and run ./run_all.sh

Variant key
  a1_asis             official file, it.fails -> it only, line 83 intact          FAILS at :83:39 after ~1.3 s (the bug)
  b1_fixed            line 83 deleted + waitFor import dropped + it.fails -> it   4 passed (the proposed fix)
  c1_delegated        line 83 kept, getConstitution mock delegated to fetch       4 passed (the other valid fix; AccountSettings.render.test.tsx:53-56 does this)
  d1_nonempty         b1_fixed with a saved constitution "saved rules"            passes on the real component
  e1_mutant_empty     b1_fixed against a component whose load forgets setLoadedValue(loaded) (AccountSettings.tsx:635)   4 passed (mutant survives; sibling card)
  f1_mutant_nonempty  same mutant, saved constitution "saved rules"               caught 59 of 62 runs
  f2_..._act          f1 plus await act(async () => {}) before the negative assertion   caught 40 of 40
  d2_nonempty_act     f2's case on the real component                             32 of 32 pass
  g1_mutant_sources   AccountSettings.iss372.sources.test.tsx against the mutant  3 passed (mutant survives)
  h1_real_sources     same file against the real component                        3 passed (harness sanity)

5-fixer files (2026-10-07, FIX-744). Repo edits are the three test files in fix-08-diff.txt; no product file changed.
  fix-01-before.txt                 every affected file run in place BEFORE any edit, one file per run (B1-B7)
  fix-02-after.txt                  the same files AFTER the edits (A1-A5); the meta-test XPASS is the pass signal
  fix-03-mutant-probe-iss945-iss1036.txt   the ISS-921 case vs the real component and two mutants, plus 16/16 + 16/16 stability rounds
  fix-04-eslint.txt                 eslint --max-warnings 0 on the three edited files
  fix-05-probe-iss1039-iss1040.txt  wrong-reason red at HEAD, green after, red on a no-feedback mutant
  fix-06-probe-iss1041.txt          ISS-1041 (deferred, not edited): legacy spy case vs network case on the shipped and pre-FIX-636 picker
  fix-07-tsc.txt                    tsc --noEmit: 0 errors in the edited files
  fix-08-diff.txt                   the full diff
  fix-probes/                       the probe scripts behind fix-03/05/06 (as .txt)
