"""QA-KB-075: build scratch COPIES of run_commands.py with one reconcile rule changed. Never writes under backend/.

Anchored on quoted CODE (not line numbers), because concurrent fixers move the lines; a drifted file fails loudly.
  opt2 = the DEAD last-by-seq rule restored (f23625911's ladder): `if degraded` (latest completion by seq) /
         `elif completes and not failed` (whole-tail), i.e. what the stale comments describe.
  opt4 = ONLY the `completed` rung un-scoped: `elif completes and not failed_current` (FIX-484's other two scopings kept).
"""
import pathlib, sys

SRC = pathlib.Path("app/api/run_commands.py")
OUT = pathlib.Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
text = SRC.read_text()


def once(s, needle):
    n = s.count(needle)
    assert n == 1, f"anchor appears {n}x, expected 1: {needle!r}"


LATEST = "        _latest_complete = max(completes, key=lambda e: e.seq) if completes else None\n"
IF_DEG = "            if degraded_current:\n"
ELIF = "            elif current_attempt_completes and not failed_current:\n"
for a in (LATEST, IF_DEG, ELIF):
    once(text, a)

dead_locals = (
    '        failed = any(e.type == "pipeline_failed" for e in events)\n'
    "        degraded = bool(\n"
    "            _latest_complete is not None\n"
    "            and isinstance(_latest_complete.payload_json, dict)\n"
    '            and _latest_complete.payload_json.get("status") == "degraded"\n'
    "        )\n"
)
opt2 = (
    text.replace(LATEST, LATEST + dead_locals)
    .replace(IF_DEG, "            if degraded:\n")
    .replace(ELIF, "            elif completes and not failed:\n")
)
opt4 = text.replace(ELIF, "            elif completes and not failed_current:\n")
(OUT / "opt2.py").write_text(opt2)
(OUT / "opt4.py").write_text(opt4)
print("opt2.py: dead last-by-seq rule restored | opt4.py: completed rung un-scoped (current_attempt_completes -> completes)")
