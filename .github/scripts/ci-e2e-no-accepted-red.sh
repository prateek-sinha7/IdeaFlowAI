#!/usr/bin/env bash
# Reject accepted-red baselines in the mandatory mocked Playwright project.
#
# WHY THIS EXISTS
#   The mocked project is a mandatory gate, so "the test does not run" and "the
#   test passes" must not be the same outcome. A previous remediation pass
#   converted 20-odd failing tests from `test.fixme(true, ...)` to
#   `test.skip(true, ...)` and added an `Owner:` suffix. Nothing was fixed; the
#   suite merely stopped reporting the failures. This check makes that pattern
#   visible instead of silent.
#
# WHAT IS REJECTED
#   test.skip(true, ...)            - unconditionally disabled
#   test.fixme(true, ...)           - unconditionally disabled
#   test.skip("name", async ...)    - declared and skipped in one call
#   test.fixme("name", async ...)   - same
#   describe.skip(...)              - whole block disabled
#
# WHAT IS ALLOWED
#   A skip whose condition is a real runtime predicate, e.g.
#   `test.skip(!process.env.FIDELITY_CAPTURE, "capture only")`. That is a
#   genuinely inapplicable case in this environment, not a hidden failure.
#
#   Files matching *.live.spec.ts are excluded: they are not part of the mocked
#   project (playwright.config.ts sets testIgnore for them) and have their own
#   credential-gated owner.
set -euo pipefail

specs_dir="frontend/e2e/tests"
violations=0

if [[ ! -d "${specs_dir}" ]]; then
  echo "::error::${specs_dir} does not exist."
  exit 1
fi

echo "Auditing the mandatory mocked project for accepted-red skips."
echo

while IFS= read -r -d '' spec; do
  case "${spec}" in
    *.live.spec.ts) continue ;;
  esac

  # Unconditional disables: the literal `true` as the first argument.
  while IFS=: read -r line_no line_text; do
    [[ -z "${line_no}" ]] && continue
    echo "::error file=${spec},line=${line_no}::Unconditionally disabled test in a mandatory project: ${line_text#"${line_text%%[![:space:]]*}"}"
    violations=$((violations + 1))
  done < <(grep -nE '(test|it)\.(skip|fixme)\(\s*true\s*,' "${spec}" || true)

  # Declared-and-skipped form: first argument is a string title.
  while IFS=: read -r line_no line_text; do
    [[ -z "${line_no}" ]] && continue
    echo "::error file=${spec},line=${line_no}::Test declared as skipped in a mandatory project: ${line_text#"${line_text%%[![:space:]]*}"}"
    violations=$((violations + 1))
  done < <(grep -nE '(test|it)\.(skip|fixme)\(\s*["'\''`]' "${spec}" || true)

  # Whole suites disabled.
  while IFS=: read -r line_no line_text; do
    [[ -z "${line_no}" ]] && continue
    echo "::error file=${spec},line=${line_no}::Suite disabled in a mandatory project: ${line_text#"${line_text%%[![:space:]]*}"}"
    violations=$((violations + 1))
  done < <(grep -nE '(describe|test\.describe)\.(skip|fixme)\(' "${spec}" || true)
done < <(find "${specs_dir}" -type f -name '*.spec.ts' -print0 | sort -z)

echo
if ((violations > 0)); then
  cat <<'EOF'
::error::The mocked Playwright project contains disabled tests.
::error::
::error::Each one must be resolved, not relabelled. For every case above:
::error::  * fix the test or the product behaviour it caught, OR
::error::  * prove it is genuinely inapplicable and move it out of the mocked
::error::    project (rename to *.live.spec.ts, or delete it with review),
::error::    naming the owner that covers the behaviour instead.
::error::
::error::Converting test.fixme to test.skip is not a resolution.
EOF
  exit 1
fi

echo "No accepted-red skips in the mandatory mocked project."
