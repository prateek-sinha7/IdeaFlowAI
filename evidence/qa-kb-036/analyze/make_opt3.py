"""opt3 = revert ONLY FIX-484's ISS-435 change: degraded completions dropped from terminal_seqs again."""
import pathlib, sys
lines = pathlib.Path("app/api/run_commands.py").read_text().splitlines(keepends=True)
assert lines[905].strip() == "+ degraded_complete_seqs", lines[905]      # line 906
assert lines[903].strip() == "terminal_seqs = (", lines[903]            # line 904
del lines[905]
pathlib.Path(sys.argv[1]).write_text("".join(lines))
print("opt3.py written: terminal_seqs without degraded_complete_seqs (pre-ISS-435 behaviour)")
