"""Apply the PROPOSED two comment hunks to a scratch copy (never to the repo) and write target_fixed.py."""
import pathlib, sys
d = pathlib.Path(sys.argv[1])
t = (d / "target_now.py").read_text()

OLD1 = (
    '        # 13:13 — yet pre-fix the run still read "degraded" forever. The LATEST\n'
    '        # pipeline_complete must decide, not "was ANY completion ever degraded".\n'
)
NEW1 = (
    '        # 13:13 — yet pre-fix the run still read "degraded" forever. Only a degraded\n'
    "        # pipeline_complete at or after the last attempt boundary (run_resuming /\n"
    '        # pipeline_start, FIX-484) counts, not "was ANY completion ever degraded".\n'
)
OLD2 = (
    "        # Reverse order: a clean completion, then a LATER degraded one — latest-wins cuts\n"
    "        # the other way too.\n"
)
NEW2 = (
    "        # Reverse order: a clean completion, then a LATER attempt that ends degraded —\n"
    "        # that completion is at or after the last attempt boundary, so it counts too.\n"
)
for old in (OLD1, OLD2):
    assert t.count(old) == 1, f"anchor appears {t.count(old)}x: {old!r}"
(d / "target_fixed.py").write_text(t.replace(OLD1, NEW1).replace(OLD2, NEW2))
print("target_fixed.py written (2 comment hunks replaced; nothing else changed)")
