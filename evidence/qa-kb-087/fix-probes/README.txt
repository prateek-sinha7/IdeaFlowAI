QA-KB-087 5-fixer probe scripts (2026-10-07), stored as .txt so vitest, tsc and eslint never collect them.
They build scratch copies OUTSIDE the repo (session scratchpad), from git HEAD and the working tree, and never write the repo.

  vt.sh.txt                      runs ONE vitest file in place from frontend/ and appends an ANSI-free transcript (fix-01, fix-02)
  probe945.*                     ISS-945 / ISS-1036: the ISS-921 case vs the real AccountSettings and two mutants (fix-03)
  probe1039.*                    ISS-1039 / ISS-1040: wrong-reason red at HEAD, green after, red on a no-feedback mutant (fix-05)
  probe1041.make_probe.py.txt    ISS-1041 (deferred): legacy spy case vs network case, on the shipped and the pre-FIX-636 picker (fix-06)
                                 the "as shipped" pair in fix-06 was built by an inline python step: the HEAD file with only its import repointed
Reproduce: mkdir <dir>; copy a probe's make_probe.py/run_probe.sh/vitest.config.mts (drop .txt); set root in vitest.config.mts to <dir>;
ln -s <repo>/frontend/node_modules <dir>/node_modules; python3 make_probe.py; ./run_probe.sh
