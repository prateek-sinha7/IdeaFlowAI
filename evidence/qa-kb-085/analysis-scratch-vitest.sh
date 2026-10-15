#!/usr/bin/env bash
# QA-KB-085 analyzer proof. Run from the repo root. READ-ONLY: every modified source and every patched test is a
# copy in a throwaway dir outside the repo; the repo's test files, DashboardLayout.tsx and page.tsx are never written.
set -euo pipefail
REPO="$(git rev-parse --show-toplevel)"
SCR="$(mktemp -d)"; trap 'rm -rf "$SCR"' EXIT
ln -s "$REPO/frontend/node_modules" "$SCR/node_modules"
printf 'export default { test: { include: ["*.test.ts"], environment: "node" } };\n' > "$SCR/vitest.config.mjs"
python3 - "$REPO" "$SCR" <<'PY'
import sys, pathlib, re
repo, scr = sys.argv[1], pathlib.Path(sys.argv[2])
V = f"{repo}/frontend/src/app/[...view]"
nl = lambda s, k: s[:k].count("\n") + 1
dl_path = f"{repo}/frontend/src/components/layout/DashboardLayout.tsx"
dl = pathlib.Path(dl_path).read_text()
# ---- ISS-942: runTabShallowNav.test.ts ---------------------------------------------------------------
t = pathlib.Path(f"{V}/runTabShallowNav.test.ts").read_text()
t = t.replace('resolve(__dirname, "page.tsx")', f'"{V}/page.tsx"').replace('resolve(__dirname, "../../components/layout/DashboardLayout.tsx")', f'"{dl_path}"')
old = 'dashboardSource.indexOf("}, [contentSourceRunId]);", start)'
assert old in t
(scr / "a1_current_anchor.test.ts").write_text(t)                                                # control: repo test as-is
patched = t.replace(old, 'dashboardSource.indexOf("\\n  }, [", start)')                         # proposed fix
(scr / "a2_fixed_anchor.test.ts").write_text(patched)
inj = dl.replace('    window.history.pushState(null, "", targetRoute);\n  }, [contentSourceRunId, pinnedVersion]);',
                 '    router.push(targetRoute);\n    window.history.pushState(null, "", targetRoute);\n  }, [contentSourceRunId, pinnedVersion]);')
assert inj != dl; (scr / "DL.injected.tsx").write_text(inj)
(scr / "a3_fixed_anchor_vs_router_push_injected.test.ts").write_text(patched.replace(f'"{dl_path}"', f'"{scr}/DL.injected.tsx"'))
dr = dl.replace("  }, [contentSourceRunId, pinnedVersion]);", "  }, [contentSourceRunId, pinnedVersion, someFutureDep]);")
assert dr != dl; (scr / "DL.drift.tsx").write_text(dr)
(scr / "a4_fixed_anchor_vs_new_dep_added.test.ts").write_text(patched.replace(f'"{dl_path}"', f'"{scr}/DL.drift.tsx"'))
# ---- ISS-844 sibling: authEffectGuard.iss844.source.test.ts -------------------------------------------
page = pathlib.Path(f"{V}/page.tsx").read_text()
g = pathlib.Path(f"{V}/authEffectGuard.iss844.source.test.ts").read_text().replace('path.join(__dirname, "page.tsx")', f'"{V}/page.tsx"')
(scr / "b1_iss844_real_page.test.ts").write_text(g)
M, A = "// Auth check on mount", "}, [router, dispatch]);"
s = page.index(M); e = page.index(A, s)
guard = "    if (!signedInDispatchedRef.current) {\n      signedInDispatchedRef.current = true;\n      dispatch(signedIn({ token: storedToken }));\n    }\n"
assert guard in page
def drift(p):
    i = p.index(A, p.index(M)); return p[:i] + "}, [router, dispatch, someFutureDep]);" + p[i+len(A):]
variants = {"b2_iss844_deps_changed": drift(page),
            "b3_iss844_guard_removed": page.replace(guard, "    dispatch(signedIn({ token: storedToken }));\n"),
            "b4_iss844_guard_removed_and_deps_changed": drift(page.replace(guard, "    dispatch(signedIn({ token: storedToken }));\n"))}
for name, src in variants.items():
    (scr / f"{name}.tsx").write_text(src)
    (scr / f"{name}.test.ts").write_text(g.replace(f'"{V}/page.tsx"', f'"{scr}/{name}.tsx"'))
    i = src.index(M); j = src.index(A, i)          # the EXACT anchor the test searches for, as the test would find it
    print(f"{name}: window L{nl(src,i)} -> L{nl(src,j)} = {nl(src,j)-nl(src,i)} lines")
print(f"b1_iss844_real_page: window L{nl(page,s)} -> L{nl(page,e)} = {nl(page,e)-nl(page,s)} lines; second '{A}' at L{nl(page, page.index(A, e+1))}")
PY
for f in a1_current_anchor a2_fixed_anchor a3_fixed_anchor_vs_router_push_injected a4_fixed_anchor_vs_new_dep_added b1_iss844_real_page b2_iss844_deps_changed b3_iss844_guard_removed b4_iss844_guard_removed_and_deps_changed; do
  echo "=== $f"
  "$REPO/frontend/node_modules/.bin/vitest" --run --root "$SCR" --config "$SCR/vitest.config.mjs" "$f.test.ts" 2>&1 \
    | grep -E "^\s+Tests |^\s+×|AssertionError" | sed 's/^ */   /' || true
done
