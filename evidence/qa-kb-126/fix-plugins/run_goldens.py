"""Run the 10 golden files one per subprocess (cwd = <root>/backend) and print one summary line each."""
import os
import subprocess
import sys

root, py = sys.argv[1], sys.argv[2]
files = [
    "tests/contract/agents/test_characterization_ppt.py",
    "tests/contract/agents/test_characterization_app_builder.py",
    "tests/contract/agents/test_characterization_prototype.py",
    "tests/contract/agents/test_characterization_prototype_revision.py",
    "tests/contract/agents/test_characterization_prototype_large_revision.py",
    "tests/contract/agents/test_characterization_prototype_feature_revision.py",
    "tests/agents/test_characterization_sample_subagents_parallel.py",
    "tests/agents/test_defect_characterization_v2.py",
    "tests/unit/agents/test_phase3_cutover_verify.py",
    "tests/unit/agents/test_sc001_gate_flag.py",
]
env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", DATABASE_URL="sqlite:///:memory:")
for f in files:
    p = subprocess.run([py, "-m", "pytest", f, "-q", "-p", "no:cacheprovider", "-W", "ignore"],
                       cwd=os.path.join(root, "backend"), env=env, capture_output=True, text=True, timeout=300)
    lines = p.stdout.strip().splitlines()
    failed = [l for l in lines if l.startswith("FAILED") or l.startswith("ERROR")]
    print(f"{f}: {' '.join(failed)} {lines[-1] if lines else p.stderr[-200:]}", flush=True)
