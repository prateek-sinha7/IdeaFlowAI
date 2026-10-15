"""READ-ONLY survey: which resumable-status runs in the local dev DB would hit a silent
`resume_run` early exit TODAY if the owner clicked "Reopen & fix" (user endpoint) or were adopted by
a backend restart (restore_non_terminal_runs).

Two guards sit IN FRONT of resume_run and are applied first, because they decide whether the engine
is ever reached:
  * user endpoint:  _require_tier_entitlement -> can_run_pipeline(tier, type) against the closed
                    TIER_PIPELINES whitelist (run_commands.py:700, entitlements.py:112); the most
                    permissive tier, enterprise, is used so a refusal here is a refusal for everyone.
  * restart:        _is_resumable_in_flight -> compile_for_run(type) must succeed, else the run is
                    failed loudly by the WR-05 branch (engine.py:13036-13039, :12911-12922).

The DB is only read (one SET TRANSACTION READ ONLY connection). The decision logic below is a
line-for-line copy of what `ExecutionEngine.resume_run` does before it reaches
`_drive_resumed_stream` (engine.py:15628-15735), executed against the real registry/compiler:

  * persisted manifest present -> recompile at its persisted trust   (engine.py:15628-15653)
  * else roster = get_pipeline_agents(resolve_alias(type))           (engine.py:15697)
  * empty roster -> compile_for_run(type) fallback                   (engine.py:15716)
  * still empty -> "empty agent list"                                (engine.py:15729)
"""
import collections
import datetime
import sys

from sqlalchemy import create_engine, text

from app.core.config import settings

OUT = sys.argv[1]
eng = create_engine(settings.DATABASE_URL)

from agents.capabilities.registry import CapabilityRegistry, discover  # noqa: E402
from agents.execution_engine.engine import compile_for_run, resolve_alias  # noqa: E402
from agents.registry import get_pipeline_agents  # noqa: E402
from agents.workflows.compiler import WorkflowCompiler  # noqa: E402
from agents.workflows.manifest import build_manifest_from_dict  # noqa: E402
from app.core.entitlements import can_run_pipeline  # noqa: E402

lines = []


def w(s=""):
    lines.append(s)


def classify(run_id, rtype, manifest):
    """Return (verdict, detail) mirroring resume_run's pre-drive branches."""
    if isinstance(manifest, dict) and manifest.get("steps"):
        try:
            _mf = dict(manifest)
            trust = _mf.pop("_trust", "user") or "user"
            discover()
            WorkflowCompiler().compile(
                build_manifest_from_dict(_mf, f"run:{run_id}"), CapabilityRegistry(), trust=trust
            )
            return "drives", ""
        except Exception as exc:  # noqa: BLE001
            return "SILENT: persisted manifest failed to recompile (engine.py:15642)", f"{type(exc).__name__}: {str(exc)[:110]}"
    try:
        agents = get_pipeline_agents(resolve_alias(rtype))
    except Exception as exc:  # noqa: BLE001
        return "SILENT: cannot resolve agents (engine.py:15698)", f"{type(exc).__name__}: {str(exc)[:110]}"
    if agents:
        try:
            plan = compile_for_run(rtype).steps
        except Exception:  # noqa: BLE001
            plan = []  # a registry roster resumes as it stands (engine.py:15724)
        return "drives", ""
    try:
        compile_for_run(rtype)
    except Exception as exc:  # noqa: BLE001
        return "SILENT: empty roster and plan cannot compile (engine.py:15717)", f"{type(exc).__name__}: {str(exc)[:110]}"
    return "drives", ""


with eng.connect() as conn:
    conn.execute(text("SET TRANSACTION READ ONLY"))
    rows = conn.execute(
        text(
            "SELECT id, type, status, manifest_json, left(coalesce(error,'<NULL>'),60) AS err "
            "FROM workflow_runs WHERE status IN ('failed','cancelled','degraded')"
        )
    ).fetchall()
    conn.rollback()

w(f"# local dev DB read-only + in-process registry/compiler, run {datetime.datetime.now().isoformat(timespec='seconds')}")
w(f"resumable-status runs examined (failed|cancelled|degraded): {len(rows)}")
tally_user = collections.Counter()
tally_restart = collections.Counter()
by_type = collections.defaultdict(collections.Counter)
examples = {}
for rid, rtype, status, manifest, err in rows:
    engine_verdict, detail = classify(str(rid), rtype, manifest)
    allowed, _reason = can_run_pipeline("enterprise", rtype)
    if not allowed:
        user = "REFUSED LOUDLY: HTTP 403 tier_not_entitled at the endpoint (engine never reached)"
    elif engine_verdict.startswith("SILENT"):
        user = engine_verdict
    else:
        user = "drives"
    try:
        compile_for_run(rtype)
        restart_ok = True
    except Exception:  # noqa: BLE001
        restart_ok = False
    if not restart_ok:
        restart = "LOUD: not resumable -> WR-05 abandoned->failed with .error (resume_run never reached)"
    elif engine_verdict.startswith("SILENT"):
        restart = engine_verdict
    else:
        restart = "drives"
    tally_user[user] += 1
    tally_restart[restart] += 1
    by_type[(rtype, status)][user.split(":")[0].split(" (")[0]] += 1
    if user.startswith("SILENT") and user not in examples:
        examples[user] = (str(rid)[:8], rtype, status, detail, err)
w("")
w("USER ENDPOINT (POST /api/runs/{id}/resume) verdict tally:")
for v, n in tally_user.most_common():
    w(f"  {n:4d}  {v}")
w("")
w("RESTART AUTO-RESUME (restore_non_terminal_runs branch b) verdict tally, if these were non-terminal at a restart:")
for v, n in tally_restart.most_common():
    w(f"  {n:4d}  {v}")
w("")
w("per (type, status) -> user-endpoint outcome:")
for (t, st), c in sorted(by_type.items(), key=lambda kv: -sum(kv[1].values())):
    w(f"  {t:34s} {st:10s} " + "  ".join(f"{k}={v}" for k, v in sorted(c.items())))
w("")
w("examples of runs that would be SILENT on the user endpoint (none means the class is not present in this DB):")
if not examples:
    w("  (none)")
for v, ex in examples.items():
    w(f"  {v}\n      run={ex[0]} type={ex[1]} status={ex[2]}\n      exc={ex[3]}\n      error={ex[4]}")
with open(OUT, "w") as fh:
    fh.write("\n".join(lines) + "\n")
print("wrote", OUT)
