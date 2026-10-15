#!/usr/bin/env bash
# QA-KB-085 fixer proof (FIX for ISS-942 + ISS-1027). Run from the repo root.
# READ-ONLY on the repo: every mutated DashboardLayout.tsx / page.tsx and every test variant is a copy in a
# throwaway dir. Three test variants per mutant:
#   old         = the test as committed at HEAD (dependency-list end anchor)
#   anchor-only = the working-tree test minus its one-hook assertion
#   fixed       = the working-tree test as shipped by the fix
set -euo pipefail
REPO="$(git rev-parse --show-toplevel)"
SCR="$(mktemp -d)"; trap 'rm -rf "$SCR"' EXIT
ln -s "$REPO/frontend/node_modules" "$SCR/node_modules"
printf 'export default { test: { include: ["*.test.ts"], environment: "node" } };\n' > "$SCR/vitest.config.mjs"
V="frontend/src/app/[...view]"
git -C "$REPO" show "HEAD:$V/runTabShallowNav.test.ts" > "$SCR/old_a.src"
git -C "$REPO" show "HEAD:$V/authEffectGuard.iss844.source.test.ts" > "$SCR/old_b.src"
python3 - "$REPO" "$SCR" <<'PY'
import sys, pathlib, re
repo, scr = sys.argv[1], pathlib.Path(sys.argv[2])
V = f"{repo}/frontend/src/app/[...view]"
dl = pathlib.Path(f"{repo}/frontend/src/components/layout/DashboardLayout.tsx").read_text()
page = pathlib.Path(f"{V}/page.tsx").read_text()

def must_replace(s, old, new):
    assert old in s, old
    return s.replace(old, new, 1)

# ---- test variants -------------------------------------------------------------------------------------
HOOK_A = '  expect(dashboardSource.slice(start, end).match(/\\buse(Callback|Effect)\\(/g)).toHaveLength(1);\n'
HOOK_B = '    expect(body.match(/\\buseEffect\\(/g)).toHaveLength(1);\n'
a_new = pathlib.Path(f"{V}/runTabShallowNav.test.ts").read_text()
b_new = pathlib.Path(f"{V}/authEffectGuard.iss844.source.test.ts").read_text()
tests_a = {"old": (scr / "old_a.src").read_text(), "anchor-only": must_replace(a_new, HOOK_A, ""), "fixed": a_new}
tests_b = {"old": (scr / "old_b.src").read_text(), "anchor-only": must_replace(b_new, HOOK_B, ""), "fixed": b_new}

# ---- ISS-942 mutants of DashboardLayout.tsx ------------------------------------------------------------
CLOSE = "    window.history.pushState(null, \"\", targetRoute);\n  }, [contentSourceRunId, pinnedVersion]);"
mut_a = {
    "A1_real": dl,
    "A2_router_push_injected_into_handler": must_replace(dl, CLOSE,
        "    router.push(targetRoute);\n" + CLOSE),
    "A3_new_dep_added_to_handler": must_replace(dl, "  }, [contentSourceRunId, pinnedVersion]);",
        "  }, [contentSourceRunId, pinnedVersion, someFutureDep]);"),
    "A4_handler_deps_list_dropped": must_replace(dl, "  }, [contentSourceRunId, pinnedVersion]);", "  });"),
}
# ---- ISS-1027 mutants of page.tsx ----------------------------------------------------------------------
M, A = "// Auth check on mount", "}, [router, dispatch]);"
GUARD = ("    if (!signedInDispatchedRef.current) {\n      signedInDispatchedRef.current = true;\n"
         "      dispatch(signedIn({ token: storedToken }));\n    }\n")
NOGUARD = "    dispatch(signedIn({ token: storedToken }));\n"
def own_close(p, repl):
    i = p.index(A, p.index(M)); return p[:i] + repl + p[i + len(A):]
deps = lambda p: own_close(p, "}, [router, dispatch, someFutureDep]);")
nodeps = lambda p: own_close(p, "});")
noguard = lambda p: must_replace(p, GUARD, NOGUARD)
mut_b = {
    "B1_real": page,
    "B2_deps_changed": deps(page),
    "B3_guard_removed": noguard(page),
    "B4_guard_removed_and_deps_changed": deps(noguard(page)),
    "B5_guard_removed_and_deps_list_dropped": nodeps(noguard(page)),
}

def emit(tests, muts, src_expr, ext):
    for mname, msrc in muts.items():
        (scr / f"{mname}.{ext}").write_text(msrc)
        for tname, tsrc in tests.items():
            body = tsrc
            for e in src_expr:
                body = body.replace(e, f'"{scr}/{mname}.{ext}"')
            assert f'"{scr}/{mname}.{ext}"' in body
            (scr / f"{mname}__{tname}.test.ts").write_text(body)

# runTabShallowNav reads page.tsx too (cases 2 and 3): point it at the real page, DashboardLayout at the mutant
for k, v in tests_a.items():
    tests_a[k] = v.replace('resolve(__dirname, "page.tsx")', f'"{V}/page.tsx"')
emit(tests_a, mut_a, ['resolve(__dirname, "../../components/layout/DashboardLayout.tsx")'], "dl.tsx")
emit(tests_b, mut_b, ['path.join(__dirname, "page.tsx")'], "page.tsx")
(scr / "order.txt").write_text("\n".join(f"{m}__{t}" for m in [*mut_a, *mut_b] for t in ["old", "anchor-only", "fixed"]) + "\n")
PY
while read -r f; do
  out="$("$REPO/frontend/node_modules/.bin/vitest" --run --root "$SCR" --config "$SCR/vitest.config.mjs" "$f.test.ts" 2>&1 || true)"
  r="$(printf '%s\n' "$out" | grep -E "^\s+Tests " | sed 's/^ *Tests *//; s/ *$//' || true)"
  why="$(printf '%s\n' "$out" | grep -m1 -E "AssertionError" | sed 's/^ *//' | cut -c1-110 || true)"
  printf '%-58s %-24s %s\n' "$f" "$r" "$why"
done < "$SCR/order.txt"
