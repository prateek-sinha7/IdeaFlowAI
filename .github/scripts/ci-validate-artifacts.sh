#!/usr/bin/env bash
# Validate artifacts downloaded from an untrusted evaluator run before use.
#
# Artifacts produced by a run of fork code are DATA. The previous finalizer
# declared MAX_ARTIFACT_SIZE_BYTES and then never referenced it, and performed no
# path, size, symlink or parse checks at all — it downloaded the files and handed
# them straight to the scanner.
#
# What is enforced here:
#   * no symlinks (a link could redirect a later copy outside the workspace)
#   * no path traversal or absolute paths in entry names
#   * a per-file size ceiling
#   * every expected file present and non-empty
#   * XML parses as XML, LCOV looks like LCOV
#
# Usage: ci-validate-artifacts.sh <download-dir>
set -euo pipefail

dir="${1:?usage: ci-validate-artifacts.sh <download-dir>}"
max_bytes="${MAX_ARTIFACT_SIZE_BYTES:-104857600}" # 100 MiB

if [[ ! -d "${dir}" ]]; then
  echo "::error::download directory ${dir} does not exist"
  exit 1
fi

problems=0

# Symlinks first: everything after this assumes real files.
while IFS= read -r -d '' link; do
  echo "::error::artifact contains a symlink, which is not allowed: ${link}"
  problems=$((problems + 1))
done < <(find "${dir}" -type l -print0)

while IFS= read -r -d '' file; do
  relative="${file#"${dir}/"}"

  case "${relative}" in
    /*|*..*)
      echo "::error::artifact entry name is unsafe: ${relative}"
      problems=$((problems + 1))
      continue
      ;;
  esac

  size="$(stat -c '%s' "${file}")"
  if ((size == 0)); then
    echo "::error::artifact file is empty: ${relative}"
    problems=$((problems + 1))
    continue
  fi
  if ((size > max_bytes)); then
    echo "::error::artifact file ${relative} is ${size} bytes, over the ${max_bytes} limit"
    problems=$((problems + 1))
    continue
  fi

  echo "  ok ${relative} (${size} bytes)"
done < <(find "${dir}" -type f -print0)

# Required inputs. Sonar must not analyse without coverage: it would produce a
# passing gate over unmeasured code.
for required in backend-coverage.xml frontend-lcov.info; do
  if [[ ! -s "${dir}/${required}" ]]; then
    echo "::error::required coverage artifact is missing: ${required}"
    problems=$((problems + 1))
  fi
done

# Parse checks. Malformed input is rejected here rather than silently producing
# an analysis with no coverage attached.
if [[ -s "${dir}/backend-coverage.xml" ]]; then
  if ! python3 -c 'import sys,xml.etree.ElementTree as ET; ET.parse(sys.argv[1])' \
       "${dir}/backend-coverage.xml"; then
    echo "::error::backend-coverage.xml is not parseable XML"
    problems=$((problems + 1))
  fi
fi

if [[ -s "${dir}/frontend-lcov.info" ]]; then
  if ! grep -qE '^(SF:|TN:)' "${dir}/frontend-lcov.info"; then
    echo "::error::frontend-lcov.info does not look like an LCOV report"
    problems=$((problems + 1))
  fi
fi

if ((problems > 0)); then
  echo "::error::${problems} artifact validation problem(s); refusing to proceed."
  exit 1
fi

echo "All downloaded artifacts validated."
