"""opt2 = the root card's second option: KEEP the dead last-by-seq `degraded`, DELETE FIX-484's degraded_current ladder."""
import pathlib, sys
lines = pathlib.Path("app/api/run_commands.py").read_text().splitlines(keepends=True)
L = lambda n: lines[n - 1]
assert L(945).strip() == "if degraded_current:", L(945)
assert L(947).strip() == "elif current_attempt_completes and not failed_current:", L(947)
assert L(950).strip() == 'new_status = "failed"', L(950)
lines[944] = L(945).replace("degraded_current", "degraded")                       # if degraded:
lines[946] = L(947).replace("current_attempt_completes and not failed_current",    # elif completes and not failed:
                            "completes and not failed")
pathlib.Path(sys.argv[1]).write_text("".join(lines))
print("opt2.py written: ladder reverted to f23625911's `if degraded / elif completes and not failed`")
