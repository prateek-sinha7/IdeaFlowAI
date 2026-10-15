"""Run the given test files one per subprocess (cwd = <root>/backend); print -rA outcome lines + summary."""
import os
import subprocess
import sys

root, py, *rest = sys.argv[1:]
extra = []
if "--" in rest:
    i = rest.index("--")
    rest, extra = rest[:i], rest[i + 1:]
env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", DATABASE_URL="sqlite:///:memory:")
for f in rest:
    p = subprocess.run([py, "-m", "pytest", f, "-q", "-p", "no:cacheprovider", "-W", "ignore", "-rA", *extra],
                       cwd=os.path.join(root, "backend"), env=env, capture_output=True, text=True, timeout=300)
    print(f"== {f} {' '.join(extra)}")
    for l in p.stdout.splitlines():
        if l.startswith(("PASSED", "FAILED", "XPASS", "XFAIL", "ERROR")) or " passed" in l or " failed" in l:
            print("  " + l[:230])
