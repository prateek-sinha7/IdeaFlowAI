# evals/.archive

Kept for reference, referenced by nothing.

- **`golden/`** — hand-picked reference prototypes (spec/tasks/analysis/HTML per
  industry) plus a `calibration/` pair of known-good and known-broken documents
  with expected verdicts. Zero code in `evals/minimal` ever read them: they
  were built for a judge-calibration harness that was never written. Real,
  reusable material if calibration is picked back up — a fixed document with a
  known verdict is the only way to measure the judge itself rather than the
  agent — but until something loads them they are 744K of dead weight in the
  working tree.
