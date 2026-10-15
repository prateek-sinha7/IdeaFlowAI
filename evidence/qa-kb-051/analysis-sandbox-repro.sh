#!/usr/bin/env bash
# QA-KB-051 analyzer proof: reproduce the half-applied .knowledge/ state from BUG-127 in a THROWAWAY
# copy, so the real tree is never written. Re-runnable by the test-writer / fixer / verifier.
#
#   bash evidence/qa-kb-051/analysis-sandbox-repro.sh
#   PY_OLD=/usr/bin/python3 PY_GOOD=backend/.venv/bin/python KEEP=1 bash evidence/qa-kb-051/analysis-sandbox-repro.sh
#
# What it does (all inside a mktemp sandbox):
#   0. copy tools/knowledge + .knowledge, `git init` (build_index/validate resolve their root through
#      `git rev-parse --show-toplevel`; no commit or add is ever run), symlink the other top-level
#      entries so relative links out of .knowledge/ still resolve
#   1. converge the sandbox under a >=3.10 interpreter (PY_GOOD)
#   2. add one dummy card (what a book-keeping run does), run the cards-only rebuild under the OLD
#      interpreter (PY_OLD, default /usr/bin/python3 = 3.9.6) -> TypeError at build_context.py:431
#   3. show INDEX.md + state.yaml advanced while CONTEXT.md is stale and validate never ran
#   4. same again with --set-sync-point -> state.yaml's last_sync_* moved although the run failed
#   5. patch ONLY the sandbox copy of build_context.py (write_bytes) and re-run under PY_OLD ->
#      index/context/validate all pass, which also proves the kwarg is the only 3.10+ dependency
#      on the cards-only path
set -u

REPO="$(git rev-parse --show-toplevel)"
PY_OLD="${PY_OLD:-/usr/bin/python3}"
PY_GOOD="${PY_GOOD:-$REPO/backend/.venv/bin/python}"
SB="$(mktemp -d "${TMPDIR:-/tmp}/qa-kb-051-sandbox.XXXXXX")"
trap '[ "${KEEP:-0}" = 1 ] || rm -rf "$SB"' EXIT

sum() { shasum -a 256 "$1" | cut -c1-12; }
show_state() {
  printf '  INDEX.md   sha=%s  header: %s\n' "$(sum .knowledge/INDEX.md)" "$(grep -m1 ' cards\.' .knowledge/INDEX.md | cut -c1-12)"
  printf '  state.yaml sha=%s  %s | %s | %s\n' "$(sum .knowledge/state.yaml)" \
    "$(grep cards_count .knowledge/state.yaml)" "$(grep last_sync_date .knowledge/state.yaml)" \
    "$(grep last_sync_commit .knowledge/state.yaml | cut -c1-30)"
  printf '  CONTEXT.md sha=%s  %s\n' "$(sum .knowledge/CONTEXT.md)" "$(grep cards_indexed .knowledge/CONTEXT.md)"
}
add_card() { # add_card BUG-9999
  sed -e "s/^id: BUG-127\$/id: $1/" "$REPO/.knowledge/cards/20260918-BUG-127.md" > ".knowledge/cards/20260918-$1.md"
}

echo "interpreters: OLD=$PY_OLD ($("$PY_OLD" -c 'import sys;print(sys.version.split()[0])'))  GOOD=$PY_GOOD ($("$PY_GOOD" -c 'import sys;print(sys.version.split()[0])'))"
echo "sandbox: $SB"

mkdir -p "$SB/tools"
cp -R "$REPO/tools/knowledge" "$SB/tools/knowledge"
cp -R "$REPO/.knowledge" "$SB/.knowledge"
find "$SB/tools" -name __pycache__ -type d -prune -exec rm -rf {} +
git -C "$SB" init -q
for e in $(ls -A "$REPO" | grep -v -E '^(\.git|\.knowledge|tools)$'); do ln -s "$REPO/$e" "$SB/$e" 2>/dev/null; done
cd "$SB" || exit 2

echo; echo "== 1. converge under GOOD interpreter"
"$PY_GOOD" tools/knowledge/rebuild_knowledge.py --skip-architecture >/dev/null 2>&1; echo "exit=$?"
show_state

echo; echo "== 2. add one card, cards-only rebuild under OLD interpreter"
add_card BUG-9999
"$PY_OLD" tools/knowledge/rebuild_knowledge.py --skip-architecture 2>&1 | grep -v -E '^  ! +File ' ; echo "exit=${PIPESTATUS[0]}"

echo; echo "== 3. state after the failed run (expect INDEX/state advanced, CONTEXT stale)"
show_state

echo; echo "== 4. sync-point stamp under OLD interpreter (watermark = last_sync_*)"
add_card BUG-9998
echo "before:"; grep -E 'last_sync' .knowledge/state.yaml
"$PY_OLD" tools/knowledge/rebuild_knowledge.py --skip-architecture --set-sync-point 2>&1 | grep -E 'FAILED|Aborted|TypeError' ; echo "exit=${PIPESTATUS[0]}"
echo "after (sandbox has no HEAD so the commit is '' here; in the real repo it is HEAD's sha):"; grep -E 'last_sync' .knowledge/state.yaml
printf 'CONTEXT.md still: %s\n' "$(grep cards_indexed .knowledge/CONTEXT.md)"

echo; echo "== 5. patch ONLY the sandbox copy (write_bytes keeps LF on every OS) and re-run under OLD interpreter"
"$PY_OLD" - <<'EOF'
import pathlib, sys
p = pathlib.Path("tools/knowledge/build_context.py")
s = p.read_text(encoding="utf-8")
old = "    OUT_PATH.write_text(body, encoding='utf-8', newline='\\n')\n"
if s.count(old) != 1:
    sys.exit("build_context.py no longer carries the newline= call - already fixed? nothing to patch")
p.write_text(s.replace(old, "    OUT_PATH.write_bytes(body.encode('utf-8'))\n"), encoding="utf-8")
print("patched sandbox copy")
EOF
"$PY_OLD" tools/knowledge/rebuild_knowledge.py --skip-architecture 2>&1 | grep -E '^\[|Broken|Resolved|All stages|Aborted|FAILED|TypeError'; echo "exit=${PIPESTATUS[0]}"
show_state
printf '  CR bytes in CONTEXT.md: %s\n' "$(grep -c "$(printf '\r')" .knowledge/CONTEXT.md)"
