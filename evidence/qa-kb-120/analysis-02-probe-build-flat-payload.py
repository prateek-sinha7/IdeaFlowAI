"""QA-KB-120 analysis probe (3-analyzer, 2026-10-09). NO application source is edited.

Run (from backend/, one file, offline, ~2 s, no model call, no DB write):

    cd backend && ./.venv/bin/python -I ../evidence/qa-kb-120/analysis-02-probe-build-flat-payload.py

What it does, against a REAL RunSandbox + LocalWorkspace + real `git` in a temp RUNS_ROOT:

  [A] ORIGINAL build_flat_payload on a failed run whose declared output (greeting.md) was never
      written, in a fresh family (nothing tracked under .chain/). Records the log lines, the
      Payload, the staged entries and the .chain/ listing.
  [B] The same call with the CANDIDATE FIX applied IN MEMORY (a two-line prune of the missing
      output from `_allowlist`, mirroring engine.py:1674). The patched function is built from
      the function's own source with `exec` into the engine module's globals; engine.py on disk
      is not touched.
  [C] The same unmaterialized run, but the family already TRACKS .chain/greeting.md (a prior
      snapshot committed it). Shows why the failure is conditional on "untracked".
  [D] The WHOLE finalize_terminal_run (DB sessions mocked exactly as test_finalizer_v2.py does)
      with the original and with the patched build_flat_payload: same record, same committed
      tree, only the WARN + traceback differs.
  [E1/E2] SIBLING lead (INFERRED trigger): the allowlist names .chain/logs.jsonl (E1) or
      .chain/summary.md (E2) although the write of that file failed. Same git error from
      stage_exact, and commit_in_sandbox then reports a blocked/staging_failed snapshot that the
      finalizer publishes as `payload_blocked`.

  [F] Every way the declared output can fail to materialize (single_file absent, single_file copy
      raising, streamed_text with an empty stream, ppt with an empty stream, serialized_sandbox
      with nothing written), original vs candidate fix: the same warning, and the same cure.

  [G] The tracked-prior case [C] with the candidate fix: the stale reconciliation untracks the
      deleted output (the same staged deletion as in [C]) and nothing warns.

DATABASE_URL is pointed at a dead port before anything is imported, so an accidental write to the
dev database fails fast instead of landing.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import os
import subprocess
import sys
import tempfile
import traceback
import types
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))

_TMP = tempfile.mkdtemp(prefix="qa-kb-120-")
os.environ["DATABASE_URL"] = "postgresql://nobody:nobody@127.0.0.1:1/none"  # dead port on purpose
os.environ["RUNS_ROOT"] = _TMP
os.environ.setdefault("ENV", "development")

from agents.execution_engine import engine as eng  # noqa: E402
from app.agents.sandbox import RunSandbox  # noqa: E402

LOGGER_NAME = "agents.execution_engine.engine"
OUT: list[str] = []


def say(line: str = "") -> None:
    print(line)
    OUT.append(line)


class Capture(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.rows: list[tuple[str, str, str]] = []

    def emit(self, record: logging.LogRecord) -> None:
        exc = ""
        if record.exc_info:
            exc = traceback.format_exception_only(record.exc_info[0], record.exc_info[1])[-1].strip()
        self.rows.append((record.levelname, record.getMessage(), exc))


def capture() -> Capture:
    h = Capture()
    lg = logging.getLogger(LOGGER_NAME)
    lg.setLevel(logging.DEBUG)
    lg.addHandler(h)
    return h


def release(h: Capture) -> None:
    logging.getLogger(LOGGER_NAME).removeHandler(h)


def new_sandbox(tag: str):
    run_id = str(uuid.uuid4())
    sb = RunSandbox(f"probe-user-{tag}", run_id, runs_root=_TMP)
    sb.ensure()
    sb._ws().git_init_sandbox()
    sb.run_log_path.parent.mkdir(parents=True, exist_ok=True)
    sb.run_log_path.write_text('{"event":"run_terminal"}\n', encoding="utf-8")
    return sb, run_id


def make_ectx(run_id: str, sb, *, status: str = "failed", name: str = "greeting.md"):
    deliverable = types.SimpleNamespace(name=name, strategy="single_file", text_name=None)
    return types.SimpleNamespace(
        run_id=run_id,
        user_id="probe-user",
        owner_id="probe-user",
        workspace_id="probe-ws",
        runner=types.SimpleNamespace(sandbox=sb, registry=None, engine=None),
        final_status=status,
        deliverable=deliverable,
        revision_ordinal=1,
        step_visit_counts={"greet": 1},
        last_commit_blocked=False,
        completed_tasks=[],
        run_trace=None,
        last_streamed="",
    )


def git(sb, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=sb.root, capture_output=True, text=True).stdout.strip()


def patched_build_flat_payload():
    """The CANDIDATE FIX, built in memory from the function's own source (engine.py untouched)."""
    src = inspect.getsource(eng.build_flat_payload)
    anchor = "    # ── Write summary.md — all fields knowable before the commit (Req 4 AC 7)"
    assert src.count(anchor) == 1, "anchor moved; update the probe"
    prune = (
        "    # [probe] candidate fix: an output that was not materialized is not in the payload\n"
        "    if _output_basename and not _materialized:\n"
        "        _allowlist = _allowlist - {f\".chain/{_output_basename}\"}\n\n"
    )
    ns: dict = {}
    exec(compile(src.replace(anchor, prune + anchor, 1), "<patched build_flat_payload>", "exec"), eng.__dict__, ns)
    return ns["build_flat_payload"]


def report_payload(label: str, sb, payload, rows) -> None:
    say(f"--- {label}")
    say(f"Payload: built={payload.built} materialized={payload.materialized} chainable={payload.chainable} "
        f"reason={payload.non_chainable_reason!r}")
    say(f"Payload.allowlist = {sorted(payload.allowlist)}")
    say(f"staged entries after the call = {sb.staged_entries()}")
    say(f".chain/ on disk = {sorted(p.name for p in (sb.root / '.chain').iterdir())}")
    warn = [r for r in rows if r[0] in ("WARNING", "ERROR")]
    say(f"WARNING/ERROR records = {len(warn)}")
    for lvl, msg, exc in warn:
        say(f"    {lvl}: {msg}")
        if exc:
            say(f"        exc: {exc[:230]}")
    for lvl, msg, _ in rows:
        if "output file not found" in msg:
            say(f"    {lvl}: {msg}   <- the only log the unmaterialized branch emits itself")


# ───────────────────────────────────────────────────────────────────────────────────────────
say("QA-KB-120 probe. git: " + subprocess.run(["git", "--version"], capture_output=True, text=True).stdout.strip())
say("engine.py line of the stage call: build_flat_payload -> sandbox.stage_exact(list(_allowlist))")
say()

# [A] original, fresh family, nothing tracked
say("[A] ORIGINAL build_flat_payload, failed run, greeting.md never written, fresh family")
sb, run_id = new_sandbox("a")
h = capture()
payload = eng.build_flat_payload(run_id, make_ectx(run_id, sb))
release(h)
report_payload("A", sb, payload, h.rows)
a_has_warn = any("stage_exact failed" in m for _, m, _ in h.rows)
say(f"RESULT [A]: stage_exact failed warning present = {a_has_warn}")
say()

# [B] candidate fix, fresh family
say("[B] CANDIDATE FIX (in-memory prune of the missing output), same setup")
sb, run_id = new_sandbox("b")
fixed = patched_build_flat_payload()
h = capture()
payload = fixed(run_id, make_ectx(run_id, sb))
release(h)
report_payload("B", sb, payload, h.rows)
b_has_warn = any("stage_exact failed" in m for _, m, _ in h.rows)
say(f"RESULT [B]: stage_exact failed warning present = {b_has_warn}; "
    f"logs+summary staged = {sorted(sb.staged_entries()) == ['.chain/logs.jsonl', '.chain/summary.md']}")
say()

# [C] family already tracks .chain/greeting.md (a prior snapshot committed it)
say("[C] ORIGINAL, but a PRIOR snapshot already tracks .chain/greeting.md (resume / revision / chained family)")
sb, run_id = new_sandbox("c")
(sb.root / ".chain").mkdir(exist_ok=True)
for n, body in (("summary.md", "v1\n"), ("logs.jsonl", "{}\n"), ("greeting.md", "hello\n")):
    (sb.root / ".chain" / n).write_text(body, encoding="utf-8")
sb.stage_exact([".chain/summary.md", ".chain/logs.jsonl", ".chain/greeting.md"])
git(sb, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "prior snapshot")
h = capture()
payload = eng.build_flat_payload(run_id, make_ectx(run_id, sb))
release(h)
report_payload("C", sb, payload, h.rows)
say(f"git diff --cached --name-status = {git(sb, 'diff', '--cached', '--name-status').splitlines()}")
c_has_warn = any("stage_exact failed" in m for _, m, _ in h.rows)
say(f"RESULT [C]: stage_exact failed warning present = {c_has_warn} (tracked path => git add stages the DELETION)")
say()


# [D] the whole finalizer, original vs patched
def run_finalizer(label: str, build_fn):
    sb, run_id = new_sandbox(label)
    ectx = make_ectx(run_id, sb)
    eng._finalize_terminal_run_started.discard(run_id)
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    h = capture()
    orig = eng.build_flat_payload
    eng.build_flat_payload = build_fn
    try:
        with (
            patch("app.models.database.SessionLocal", return_value=db),
            patch("app.models.workflow.WorkflowRun", MagicMock()),
            patch("app.models.run_finalization.RunFinalization", MagicMock()),
        ):
            rec = asyncio.run(eng.finalize_terminal_run(run_id, ectx, candidate_status="failed"))
    finally:
        eng.build_flat_payload = orig
        release(h)
    head = git(sb, "rev-parse", "HEAD")
    tree = sorted(git(sb, "ls-tree", "-r", "--name-only", head, ".chain/").splitlines())
    return sb, run_id, rec, h.rows, tree


say("[D] finalize_terminal_run(candidate_status='failed'), declared greeting.md never written")
res = {}
for label, fn in (("d-original", eng.build_flat_payload), ("d-patched", patched_build_flat_payload())):
    sb, run_id, rec, rows, tree = run_finalizer(label, fn)
    res[label] = (rec, rows, tree)
    say(f"--- {label}")
    say(f"record: published_status={rec.published_status!r} candidate_status={rec.candidate_status!r} "
        f"payload_built={rec.payload_built} payload_materialized={rec.payload_materialized} "
        f"payload_chainable={rec.payload_chainable} non_chainable_reason={rec.non_chainable_reason!r} "
        f"git_tag={rec.git_tag!r}")
    say(f"committed .chain/ tree at HEAD = {tree}")
    for lvl, msg, exc in rows:
        if lvl in ("WARNING", "ERROR"):
            say(f"    {lvl}: {msg}" + (f"   [exc: {exc[:150]}]" if exc else ""))
o_rec, o_rows, o_tree = res["d-original"]
p_rec, p_rows, p_tree = res["d-patched"]
same_record = (o_rec.published_status, o_rec.non_chainable_reason, o_rec.payload_materialized, o_rec.payload_chainable,
               o_rec.git_tag) == (p_rec.published_status, p_rec.non_chainable_reason, p_rec.payload_materialized,
                                  p_rec.payload_chainable, p_rec.git_tag)
say(f"RESULT [D]: record identical = {same_record}; committed tree identical = {o_tree == p_tree}; "
    f"original warns = {any('stage_exact failed' in m for _, m, _ in o_rows)}; "
    f"patched warns = {any('stage_exact failed' in m for _, m, _ in p_rows)}")
say()

# [E] sibling lead: a file the builder failed to write is still named in the allowlist
import shutil as _real_shutil  # noqa: E402

_real_copy2 = _real_shutil.copy2


def _copy2_fail_on_logs(src, dst, *a, **kw):
    if Path(str(dst)).name == "logs.jsonl":
        raise PermissionError("logs.jsonl is not readable (simulated)")
    return _real_copy2(src, dst, *a, **kw)


def run_materialized_with_broken_write(label: str, breaker):
    """Output IS written, so the payload is chainable; one OTHER payload file fails to write."""
    sb, run_id = new_sandbox(label)
    (sb.root / "greeting.md").write_text("hello\n", encoding="utf-8")
    eng._finalize_terminal_run_started.discard(run_id)
    ectx = make_ectx(run_id, sb, status="completed")
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    h = capture()
    with (
        patch("app.models.database.SessionLocal", return_value=db),
        patch("app.models.workflow.WorkflowRun", MagicMock()),
        patch("app.models.run_finalization.RunFinalization", MagicMock()),
        breaker(),
    ):
        try:
            rec = asyncio.run(eng.finalize_terminal_run(run_id, ectx, candidate_status="completed"))
        except Exception as exc:  # noqa: BLE001
            rec = None
            say(f"    finalize raised {type(exc).__name__}: {exc}")
    release(h)
    head = git(sb, "rev-parse", "HEAD")
    tree = sorted(git(sb, "ls-tree", "-r", "--name-only", head, ".chain/").splitlines())
    return sb, rec, h.rows, tree


say("[E1] SIBLING lead (INFERRED trigger): output materialized, but the logs.jsonl copy fails (PermissionError)")
sb, rec, rows, tree = run_materialized_with_broken_write("e1", lambda: patch("shutil.copy2", _copy2_fail_on_logs))
if rec is not None:
    say(f"record: published_status={rec.published_status!r} payload_materialized={rec.payload_materialized} "
        f"payload_chainable={rec.payload_chainable} non_chainable_reason={rec.non_chainable_reason!r} git_tag={rec.git_tag!r}")
say(f"committed .chain/ tree at HEAD = {tree}")
for lvl, msg, exc in rows:
    if lvl in ("WARNING", "ERROR") and any(k in msg for k in ("logs.jsonl", "stage_exact", "staging failed", "BLOCKED", "Unrecoverable")):
        say(f"    {lvl}: {msg[:170]}" + (f"   [exc: {exc[:90]}]" if exc else ""))
say()

say("[E2] SIBLING lead (INFERRED trigger): output materialized, but the FIRST summary.md render raises")
_real_render = eng.render_summary_md
_calls = {"n": 0}


def _render_fail_once(*a, **kw):
    _calls["n"] += 1
    if _calls["n"] == 1:
        raise OSError("summary.md could not be rendered (simulated, first call only)")
    return _real_render(*a, **kw)


sb, rec, rows, tree = run_materialized_with_broken_write("e2", lambda: patch.object(eng, "render_summary_md", _render_fail_once))
if rec is not None:
    say(f"record: published_status={rec.published_status!r} payload_materialized={rec.payload_materialized} "
        f"payload_chainable={rec.payload_chainable} non_chainable_reason={rec.non_chainable_reason!r} git_tag={rec.git_tag!r}")
say(f"committed .chain/ tree at HEAD = {tree}")
for lvl, msg, exc in rows:
    if lvl in ("WARNING", "ERROR") and any(k in msg for k in ("summary.md", "stage_exact", "staging failed", "BLOCKED", "Unrecoverable")):
        say(f"    {lvl}: {msg[:170]}" + (f"   [exc: {exc[:90]}]" if exc else ""))
say()
# [F] every way the declared output can fail to materialize
say("[F] every way the declared output can fail to materialize (fresh family each; ORIGINAL vs CANDIDATE FIX)")


def variant_ectx(run_id, sb, variant):
    e = make_ectx(run_id, sb, status="failed", name="out.md")
    if variant == "single_file: file absent":
        pass
    elif variant == "single_file: file present but copy raises":
        (sb.root / "out.md").write_text("x\n", encoding="utf-8")
    elif variant == "streamed_text: empty stream":
        e.deliverable.strategy = "streamed_text"
        e.last_streamed = ""
    elif variant == "ppt: empty stream":
        e.deliverable.strategy = "ppt"
        e.last_streamed = ""
    elif variant == "serialized_sandbox: nothing written":
        e.deliverable.strategy = "serialized_sandbox"
        e.runner.count_sandbox_deliverables = lambda root: 0
        e.runner.serialize_sandbox_deliverable = lambda root: ""
    return e


def copy_raises_on_output(src, dst, *a, **kw):
    if Path(str(dst)).name == "out.md":
        raise PermissionError("cannot copy the output (simulated)")
    return _real_copy2(src, dst, *a, **kw)


VARIANTS = [
    "single_file: file absent",
    "single_file: file present but copy raises",
    "streamed_text: empty stream",
    "ppt: empty stream",
    "serialized_sandbox: nothing written",
]
fixed_fn = patched_build_flat_payload()
say(f"{'variant':44s} {'original: warn/staged/out-in-allowlist':44s} candidate fix: warn/staged/out-in-allowlist")
for v in VARIANTS:
    cells = []
    for fn in (eng.build_flat_payload, fixed_fn):
        sb, run_id = new_sandbox("f")
        ectx = variant_ectx(run_id, sb, v)
        h = capture()
        ctx_patch = patch("shutil.copy2", copy_raises_on_output) if "copy raises" in v else patch("os.getcwd", os.getcwd)
        with ctx_patch:
            pl = fn(run_id, ectx)
        release(h)
        warn = any("stage_exact failed" in m for _, m, _ in h.rows)
        cells.append(f"warn={warn!s:5} staged={len(sb.staged_entries())} out_in_allowlist={('.chain/out.md' in pl.allowlist)!s:5} materialized={pl.materialized}")
    say(f"{v:44s} {cells[0]:44s} {cells[1]}")
say()
# [G] tracked-prior case with the candidate fix
say("[G] CANDIDATE FIX where a PRIOR snapshot already tracks .chain/greeting.md (the case-[C] setup)")
sb, run_id = new_sandbox("g")
(sb.root / ".chain").mkdir(exist_ok=True)
for n, body in (("summary.md", "v1\n"), ("logs.jsonl", "{}\n"), ("greeting.md", "hello\n")):
    (sb.root / ".chain" / n).write_text(body, encoding="utf-8")
sb.stage_exact([".chain/summary.md", ".chain/logs.jsonl", ".chain/greeting.md"])
git(sb, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "prior snapshot")
h = capture()
payload = fixed_fn(run_id, make_ectx(run_id, sb))
release(h)
report_payload("G build_flat_payload (fixed)", sb, payload, h.rows)
say(f"git diff --cached --name-status = {git(sb, 'diff', '--cached', '--name-status').splitlines()}")
say("")

say("done")

Path(__file__).with_name("analysis-02-probe-build-flat-payload.txt").write_text("\n".join(OUT) + "\n", encoding="utf-8")
