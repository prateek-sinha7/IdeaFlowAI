"""The one path owner. Every run-folder path — JSON, logs, artifacts — goes
through here; nothing else in this package touches `pathlib` for run paths.

Layout, flat at the run root (not one subfolder per phase — that's what made
the old run folder hard to browse):

    .runs/<run_id>/
      config.json          snapshot_config(), before the first dispatch
      run.json              {phase: [rows]}    — dispatch results
      judge.json             {phase: [rows]}    — judge verdicts
      score.json              {phase: {...}}      — deterministic check findings
      logs/<phase>.log      every row's transcript, appended, one file per phase
      artifacts/<phase>.md|html   the phase's own response, a real openable file
      superseded/            whole prior <kind>.json files, numbered, never lost

Writes are append-only: a second write to a phase already present in a
`<kind>.json` moves the WHOLE prior file into `superseded/` first (R-07) —
simpler and safer than reconciling a partial diff, and the other phases in
that file are carried forward unchanged into the new write.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

RUNS_ROOT = Path(__file__).resolve().parent / ".runs"


def new_run_id(dataset_id: str) -> str:
    """Mint `{YYMMDD-HHMMSS}-{dataset_id}` — timestamp first so runs sort."""
    return f"{datetime.now().strftime('%y%m%d-%H%M%S')}-{dataset_id}"


def run_dir(run_id: str) -> Path:
    """`.runs/<run_id>/` — created if absent."""
    path = RUNS_ROOT / run_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def snapshot_config(run_id: str, config: dict) -> None:
    """Write `config.json` at the run root, BEFORE the first dispatch.

    So a crashed run is still re-runnable / readable from its own folder.
    """
    _write_json(run_dir(run_id) / "config.json", config)


def read_config(run_id: str) -> dict:
    """Read back the config snapshot for a run."""
    path = run_dir(run_id) / "config.json"
    if not path.exists():
        raise FileNotFoundError(f"no config snapshot at {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def write_phase(run_id: str, kind: str, phase: str, payload) -> Path:
    """Write one phase's data into `<kind>.json` (`run` | `judge` | `score`).

    Merges into whatever else is already in the file; superseding the WHOLE
    file first only when this phase already had data (a genuine re-run), so
    a fresh phase never costs the others their history.
    """
    path = run_dir(run_id) / f"{kind}.json"
    data = _read_json(path) or {}
    if phase in data and data[phase] != payload:
        _supersede(run_id, kind)
    data[phase] = payload
    _write_json(path, data)
    return path


def read_phase(run_id: str, kind: str, phase: str):
    """Read one phase's data back out of `<kind>.json`."""
    data = _read_json(run_dir(run_id) / f"{kind}.json")
    if not data or phase not in data:
        raise FileNotFoundError(f"no {kind!r} data for phase {phase!r} in run {run_id}")
    return data[phase]


def read_all(run_id: str, kind: str) -> dict:
    """Every phase currently recorded for one kind — `{}` if never written."""
    return _read_json(run_dir(run_id) / f"{kind}.json") or {}


def list_runs() -> list[str]:
    """Every run id on disk, newest first (run ids are timestamp-prefixed).

    Dot-directories are NOT runs. `.runs/.archive/` (where old runs get moved
    to start a clean sweep) was being returned as a run id called ".archive",
    which the report then tried to summarise. A run id is minted by
    `new_run_id` and always starts with a digit, so anything else under here
    is bookkeeping, not data.
    """
    if not RUNS_ROOT.exists():
        return []
    return sorted(
        (p.name for p in RUNS_ROOT.iterdir() if p.is_dir() and not p.name.startswith(".")),
        reverse=True,
    )


def list_phases(run_id: str) -> list[str]:
    """Every phase this run has dispatched, from `run.json`'s own keys."""
    return list(read_all(run_id, "run").keys())


def log_path(run_id: str, phase: str) -> Path:
    """`logs/<phase>.log` — one file per phase; callers append, never overwrite."""
    path = run_dir(run_id) / "logs" / f"{phase}.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def append_log(run_id: str, phase: str, text: str) -> Path:
    """Append one row's transcript onto this phase's shared log file."""
    path = log_path(run_id, phase)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(text)
    return path


def calls_path(run_id: str) -> Path:
    """`logs/calls.jsonl` — ONE file per run, every phase appended in order."""
    path = run_dir(run_id) / "logs" / "calls.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def log_call(run_id: str, phase: str, record: dict) -> Path:
    """Append one raw LLM call — prompt, reply, error — to `logs/calls.jsonl`.

    Every model call this harness makes, verbatim, so a bad verdict is READ
    rather than inferred from the error string it produced. This exists
    because several judge failures in a row were diagnosed by guessing at
    what the model must have returned; the schema bug behind them
    (`dimensions` returning one element) was only provable once the raw reply
    could be inspected.

    ONE file for the whole run, not one per phase: every record carries its
    own `stage`, so splitting by filename bought nothing and cost you the
    ability to read a stage-by-stage chain in the order it actually happened.

    JSONL, not JSON: appended per call, so a crashed or killed run still
    leaves every completed call readable instead of a truncated array.
    Failures are logged too — those are the ones worth reading.
    """
    with calls_path(run_id).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"stage": phase, **record}, ensure_ascii=False, default=str) + "\n")
    return calls_path(run_id)


def read_calls(run_id: str, phase: str | None = None) -> list[dict]:
    """Every logged call, oldest first — all phases, or just one. `[]` if none."""
    path = run_dir(run_id) / "logs" / "calls.jsonl"
    if not path.exists():
        return []
    records = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    return [r for r in records if phase is None or r.get("stage") == phase]


def artifact_path(run_id: str, phase: str, ext: str, *, suffix: str = "") -> Path:
    """`artifacts/<phase><suffix>.<ext>` — a real, openable file, not JSON."""
    path = run_dir(run_id) / "artifacts" / f"{phase}{suffix}.{ext}"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def write_artifact(run_id: str, phase: str, ext: str, content: str, *, suffix: str = "") -> Path:
    """Write one phase's own output as a real file — `cat` it, don't unpack JSON."""
    path = artifact_path(run_id, phase, ext, suffix=suffix)
    path.write_text(content, encoding="utf-8")
    return path


def _supersede(run_id: str, kind: str) -> None:
    """Move the whole `<kind>.json` into `superseded/`, numbered, never lost."""
    path = run_dir(run_id) / f"{kind}.json"
    target_dir = run_dir(run_id) / "superseded"
    target_dir.mkdir(parents=True, exist_ok=True)
    attempt = 1 + sum(1 for _ in target_dir.glob(f"{kind}.*.json"))
    path.rename(target_dir / f"{kind}.{attempt}.json")


def _read_json(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload) -> None:
    """Write one JSON artifact, pretty-printed and newline-terminated."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
