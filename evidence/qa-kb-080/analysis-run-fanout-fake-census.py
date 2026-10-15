"""QA-KB-080 analysis probe: census of every hand-rolled `run_fanout` test double.

Read-only. Pure ast + inspect (the FIX-231 technique: derive the real signature from source,
never restate it). For each fake it answers two questions with `inspect.Signature.bind`, which
is exactly the operation Python performs at the call site:

  FULL   call = (requests, ctx, step=..., event_queue=...)   <- _fanout_wave_stream.py:71,
                                                                _fanout_stream.py:32 (wave_scheduler,
                                                                parallel_group)
  SHORT  call = (requests, ctx, step=...)                    <- fanout_batch.py:127, engine.py:8632
                                                                (_derive_fanout)

Run from the repo root:  backend/.venv/bin/python evidence/qa-kb-080/analysis-run-fanout-fake-census.py
"""
import ast
import inspect
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / "backend"
REAL = BACKEND / "agents/execution_engine/kernel_services.py"
P = inspect.Parameter


def sig_of(fn, drop_self=True):
    a = fn.args
    pos = list(a.posonlyargs) + list(a.args)
    first_def = len(pos) - len(a.defaults)
    params = []
    for i, arg in enumerate(pos):
        if drop_self and i == 0 and arg.arg in ("self", "cls"):
            continue
        params.append(P(arg.arg, P.POSITIONAL_OR_KEYWORD, default=P.empty if i < first_def else ...))
    if a.vararg:
        params.append(P(a.vararg.arg, P.VAR_POSITIONAL))
    for arg, d in zip(a.kwonlyargs, a.kw_defaults):
        params.append(P(arg.arg, P.KEYWORD_ONLY, default=P.empty if d is None else ...))
    if a.kwarg:
        params.append(P(a.kwarg.arg, P.VAR_KEYWORD))
    return inspect.Signature(params)


def run_fanout_defs(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for cls in [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]:
        for m in cls.body:
            if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)) and m.name == "run_fanout":
                yield cls.name, m


# The real signature, derived from source.
(_, real_fn), = [(c, f) for c, f in run_fanout_defs(REAL) if c == "KernelServices"]
real_sig = sig_of(real_fn)
print(f"REAL  KernelServices.run_fanout{real_sig}   ({REAL.relative_to(REPO)}:{real_fn.lineno})\n")

full = dict(step=None, event_queue=None)
short = dict(step=None)
rows = []
for path in sorted((BACKEND / "tests").rglob("*.py")):
    if ".venv" in path.parts:
        continue
    for cls, fn in run_fanout_defs(path):
        s = sig_of(fn)
        def ok(kw):
            try:
                s.bind([], object(), **kw)
                return "ok"
            except TypeError:
                return "TypeError"
        rows.append((path.relative_to(REPO).as_posix(), fn.lineno, cls, ok(full), ok(short)))

print(f"{'fake':<92} {'FULL (wave/parallel_group)':<28} SHORT (fanout_batch/_derive_fanout)")
for rel, line, cls, f, s in rows:
    print(f"{rel + ':' + str(line):<92} {f:<28} {s}   [{cls}]")

bad_full = [r for r in rows if r[3] == "TypeError"]
print(f"\n{len(rows)} fakes | reject the FULL call: {len(bad_full)} | reject the SHORT call: "
      f"{len([r for r in rows if r[4] == 'TypeError'])}")
