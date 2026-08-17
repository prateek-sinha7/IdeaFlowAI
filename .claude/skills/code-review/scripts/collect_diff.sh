#!/usr/bin/env bash
#
# Collects a read-only diff between two branches for PR/MR review.
#
# Fetches the given source and target branches from origin, then produces a
# three-dot diff (origin/target...origin/source) representing only the changes
# introduced by the source branch since it diverged from target. This mirrors
# what a GitLab merge request diff shows.
#
# This script is READ-ONLY: it does not check out, merge, rebase, or push
# anything. It only runs `git fetch` (read) and `git diff`/`git log` (read).
#
# Usage:
#   collect_diff.sh --source <branch> [--target <branch>] [--repo <path>]
#
# Outputs a JSON object to stdout with diffFile, commitCount, filesChanged,
# fileList, source, target, and success — matching collect_diff.ps1.

set -uo pipefail

SOURCE=""
TARGET="dev"
REPO_PATH="."

fail() {
    # Emit JSON error and exit non-zero
    printf '{"success":false,"error":"%s"}\n' "$1"
    exit 1
}

# --- Parse arguments (supports --source/-s, --target/-t, --repo/-r) ---
while [[ $# -gt 0 ]]; do
    case "$1" in
        --source|-s) SOURCE="${2:-}"; shift 2 ;;
        --target|-t) TARGET="${2:-}"; shift 2 ;;
        --repo|-r)   REPO_PATH="${2:-}"; shift 2 ;;
        *) fail "Unknown argument: $1" ;;
    esac
done

[[ -z "$SOURCE" ]] && fail "Missing required argument: --source <branch>"

cd "$REPO_PATH" 2>/dev/null || fail "Cannot access repo path: $REPO_PATH"

# Confirm we're inside a git repository
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    fail "Not a git repository: $REPO_PATH"
fi

# Fetch latest refs for both branches (read-only, no local branch changes)
if ! git fetch origin "$TARGET" "$SOURCE" >/dev/null 2>&1; then
    fail "git fetch failed for origin/$TARGET or origin/$SOURCE. Check branch names and remote access."
fi

TARGET_REF="origin/$TARGET"
SOURCE_REF="origin/$SOURCE"

# Verify both refs actually resolve after fetch
git rev-parse --verify "$TARGET_REF" >/dev/null 2>&1 || fail "Target branch '$TARGET' not found on origin."
git rev-parse --verify "$SOURCE_REF" >/dev/null 2>&1 || fail "Source branch '$SOURCE' not found on origin."

RANGE="${TARGET_REF}...${SOURCE_REF}"
LOG_RANGE="${TARGET_REF}..${SOURCE_REF}"

DIFF_TEXT="$(git diff "$RANGE")"
STAT_TEXT="$(git diff --stat "$RANGE")"
LOG_TEXT="$(git log "$LOG_RANGE" --oneline)"
FILES_CHANGED="$(git diff --name-only "$RANGE")"

if [[ -z "$LOG_TEXT" ]]; then
    COMMIT_COUNT=0
else
    COMMIT_COUNT="$(printf '%s\n' "$LOG_TEXT" | grep -c '')"
fi

if [[ -z "$FILES_CHANGED" ]]; then
    FILE_COUNT=0
else
    FILE_COUNT="$(printf '%s\n' "$FILES_CHANGED" | grep -c '')"
fi

# Write the diff report to a temp file
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
SAFE_SOURCE="${SOURCE//[\/:\\]/_}"
SAFE_TARGET="${TARGET//[\/:\\]/_}"
TMPDIR_BASE="${TMPDIR:-/tmp}"
OUT_FILE="${TMPDIR_BASE%/}/flowin-pr-review-${SAFE_SOURCE}-to-${SAFE_TARGET}-${TIMESTAMP}.diff"

{
    echo "# PR Review Diff"
    echo "# Source: $SOURCE ($SOURCE_REF)"
    echo "# Target: $TARGET ($TARGET_REF)"
    echo "# Generated: $(date '+%Y-%m-%d %H:%M:%S')"
    echo ""
    echo "## Commit log ($LOG_RANGE)"
    echo "$LOG_TEXT"
    echo ""
    echo "## Diff stat"
    echo "$STAT_TEXT"
    echo ""
    echo "## Full diff"
    echo "$DIFF_TEXT"
} > "$OUT_FILE"

# Build fileList JSON array (each entry escaped for quotes/backslashes)
FILE_LIST_JSON="$(printf '%s\n' "$FILES_CHANGED" | awk 'NF' | while IFS= read -r line; do
    esc="${line//\\/\\\\}"
    esc="${esc//\"/\\\"}"
    printf '"%s",' "$esc"
done)"
FILE_LIST_JSON="[${FILE_LIST_JSON%,}]"

# Escape the diff file path for JSON
DIFF_FILE_ESC="${OUT_FILE//\\/\\\\}"
DIFF_FILE_ESC="${DIFF_FILE_ESC//\"/\\\"}"

printf '{"success":true,"diffFile":"%s","source":"%s","target":"%s","commitCount":%s,"filesChanged":%s,"fileList":%s}\n' \
    "$DIFF_FILE_ESC" "$SOURCE" "$TARGET" "$COMMIT_COUNT" "$FILE_COUNT" "$FILE_LIST_JSON"
