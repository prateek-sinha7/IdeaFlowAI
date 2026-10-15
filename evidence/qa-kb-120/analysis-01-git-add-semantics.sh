#!/usr/bin/env bash
# QA-KB-120 analysis probe: git add --force -- <paths> semantics for an absent path.
# Run: bash analysis-01-git-add-semantics.sh   (output: analysis-01-git-add-semantics.txt)
# Mirrors LocalWorkspace._git (local.py:385-404) flags: user.name/email + commit.gpgsign=false.
set -u
cd "$(mktemp -d)"   # throwaway repos live in a temp dir, never inside this checkout
gx() { git -c user.name="Velocity Runtime" -c user.email=runtime@velocity.local -c commit.gpgsign=false "$@"; }

echo "git: $(git --version)"
echo
echo "=== A: first run in a family. .chain/greeting.md was never tracked and never written"
mkdir repoA && cd repoA
git init -q -b main
printf '.chain/\n.chain.staging-*/\n' > .gitignore
gx add .gitignore && gx commit -q -m init
mkdir .chain
echo "# summary" > .chain/summary.md
echo '{}' > .chain/logs.jsonl
gx add --force -- .chain/summary.md .chain/logs.jsonl .chain/greeting.md
echo "exit=$?"
echo "--- staged after the failed add (empty => all-or-nothing):"
git diff --cached --name-only
echo "(end)"
cd ..

echo
echo "=== B: a PRIOR run tracked .chain/greeting.md; this run did not write it (atomic swap removed it)"
mkdir repoB && cd repoB
git init -q -b main
printf '.chain/\n.chain.staging-*/\n' > .gitignore
gx add .gitignore && gx commit -q -m init
mkdir .chain
echo "# summary v1" > .chain/summary.md
echo '{}' > .chain/logs.jsonl
echo hi > .chain/greeting.md
gx add --force -- .chain/summary.md .chain/logs.jsonl .chain/greeting.md && gx commit -q -m "v1 snapshot"
rm -rf .chain && mkdir .chain
echo "# summary v2 failed" > .chain/summary.md
echo '{}' > .chain/logs.jsonl
gx add --force -- .chain/summary.md .chain/logs.jsonl .chain/greeting.md
echo "exit=$?"
echo "--- staged after add (summary M, greeting D expected):"
git diff --cached --name-status
cd ..

echo
echo "=== C: fix shape. Same as A but the absent path is dropped from the pathspec list"
mkdir repoC && cd repoC
git init -q -b main
printf '.chain/\n.chain.staging-*/\n' > .gitignore
gx add .gitignore && gx commit -q -m init
mkdir .chain
echo "# summary" > .chain/summary.md
echo '{}' > .chain/logs.jsonl
gx add --force -- .chain/summary.md .chain/logs.jsonl
echo "exit=$?"
echo "--- staged:"
git diff --cached --name-only
cd ..
