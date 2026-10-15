"""Build patched COPIES of run_commands.py in the scratchpad. Never writes under backend/."""
import pathlib, sys
SRC = pathlib.Path("app/api/run_commands.py")
OUT = pathlib.Path(sys.argv[1])
lines = SRC.read_text().splitlines(keepends=True)

def L(n):  # 1-based accessor
    return lines[n - 1]

# anchor on CONTENT, not just numbers, so a drifted file fails loudly
assert L(838).strip().startswith("failed = any("), L(838)
assert L(840).strip().startswith("# FIX-247: the degraded verdict"), L(840)
assert L(849).strip().startswith("# completed all 11 steps cleanly"), L(849)
assert L(850).strip().startswith("_latest_complete = max("), L(850)
assert L(851).strip().startswith("degraded = bool("), L(851)
assert L(855).strip() == ")", L(855)
assert L(856).strip().startswith("# KAN-120"), L(856)

def build(name, drop):
    keep = [l for i, l in enumerate(lines, 1) if i not in drop]
    (OUT / name).write_text("".join(keep))
    print(f"{name}: dropped {len(drop)} lines")

# 1) BUGS.md "agreed minimal fix": delete the FIX-247 comment AND the _latest_complete / degraded assignment (840-855)
build("agreed.py", set(range(840, 856)))
# 2) narrowed fix: comment (840-849) + dead `degraded` (851-855) + dead `failed` (838); KEEP _latest_complete (850)
build("narrow.py", {838} | set(range(840, 850)) | set(range(851, 856)))
