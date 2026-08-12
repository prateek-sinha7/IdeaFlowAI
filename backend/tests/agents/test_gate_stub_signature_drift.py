"""Static conformance guard: every test double for ``_run_review_gate`` must be able to
accept the call the engine actually makes.

This is the fourth generation of one defect. ``ExecutionEngine._run_review_gate`` has grown
six parameters since the Phase-8 harness was written (``redoable`` 2026-06-30,
``cancel_event`` 2026-07-07, ``update_specs_eligible``/``artifact_kind`` 2026-07-08,
``revision_cycle``/``revision_in_flight`` 2026-08-12), and each time a batch of hand-rolled
stubs pinning the old shape started raising ``TypeError`` (KAN-101, FIX-218, FIX-220,
ISS-074). Every call site passes **by keyword**, so drift is an immediate ``TypeError`` —
which the engine's per-agent error handler then swallows, leaving a gated run reporting
``completed`` while the gate silently never opened.

The real signature is DERIVED from ``engine.py`` by AST, never restated here: restating it
would reproduce exactly the drift this guard exists to catch. The predicate is
``inspect.Signature.bind``, because that is precisely the operation Python performs at the
call site — unlike a ``**kwargs`` grep, it cannot disagree with reality.

Scope note: this guard covers *arity*. It cannot see a wrapper that accepts kwargs into a bag
and then forwards nothing (the ISS-074 "def-only" shadow fix) — that is covered behaviourally
by ``test_live_harness.py::TestEngineGate::test_gate_on_pauses_then_auto_resumes_to_complete``.
Nor does it cover attribute drift on hand-rolled context doubles, which is a sibling defect
family with the same cause and a different surface.

Pure ``ast`` + ``inspect``: it imports none of the modules it scans, so it costs no collection
time and triggers no import side effects.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]
ENGINE = BACKEND / "agents" / "execution_engine" / "engine.py"
METHOD = "_run_review_gate"

# Vendored / generated trees carry no stubs and would only slow the sweep.
_SKIP_DIR_PARTS = {".git", "node_modules", "__pycache__", "site-packages", ".venv", "venv"}

# A resolver that silently finds nothing degrades to a vacuous pass over time. These floors
# make that failure loud. They are deliberately slack — they catch "the sweep broke", not
# "someone added a stub".
_MIN_STUBS = 15
_REQUIRED_FILES = ("tests/agents/live_harness.py", "tests/agents/test_gates.py")


# ───────────────────────────── AST helpers ─────────────────────────────


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _is_func(node: ast.AST) -> bool:
    return isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))


def _signature_of(fn: ast.AST, *, drop_self: bool) -> inspect.Signature:
    """Build an ``inspect.Signature`` from a def's AST args.

    Defaults are represented by a sentinel: ``bind`` only cares whether a parameter *has*
    one, never what it is.
    """
    P = inspect.Parameter
    args = fn.args  # type: ignore[attr-defined]
    positional = list(args.posonlyargs) + list(args.args)
    first_defaulted = len(positional) - len(args.defaults)

    params: list[inspect.Parameter] = []
    for index, arg in enumerate(positional):
        if drop_self and index == 0 and arg.arg in ("self", "cls"):
            continue
        kind = P.POSITIONAL_ONLY if index < len(args.posonlyargs) else P.POSITIONAL_OR_KEYWORD
        default = P.empty if index < first_defaulted else ...
        params.append(P(arg.arg, kind, default=default))
    if args.vararg:
        params.append(P(args.vararg.arg, P.VAR_POSITIONAL))
    for arg, node in zip(args.kwonlyargs, args.kw_defaults):
        params.append(P(arg.arg, P.KEYWORD_ONLY, default=(P.empty if node is None else ...)))
    if args.kwarg:
        params.append(P(args.kwarg.arg, P.VAR_KEYWORD))
    return inspect.Signature(params)


def _scope_chain(tree: ast.Module) -> dict[ast.AST, ast.AST | None]:
    """Map every node to its innermost enclosing scope node (Module / def / class)."""
    enclosing: dict[ast.AST, ast.AST | None] = {tree: None}

    def walk(node: ast.AST, scope: ast.AST) -> None:
        for child in ast.iter_child_nodes(node):
            enclosing[child] = scope
            walk(child, child if (_is_func(child) or isinstance(child, ast.ClassDef)) else scope)

    walk(tree, tree)
    return enclosing


def _defs_bound_in(scope: ast.AST) -> dict[str, list[ast.AST]]:
    """Function/class defs bound directly in ``scope`` — not those in nested scopes."""
    found: dict[str, list[ast.AST]] = {}
    stack: list[ast.AST] = list(scope.body)  # type: ignore[attr-defined]
    while stack:
        node = stack.pop()
        if _is_func(node) or isinstance(node, ast.ClassDef):
            found.setdefault(node.name, []).append(node)  # type: ignore[attr-defined]
            continue  # a nested def opens its own scope
        stack.extend(ast.iter_child_nodes(node))
    return found


def _resolve_name(
    name: str, site: ast.AST, tree: ast.Module, enclosing: dict[ast.AST, ast.AST | None]
) -> ast.AST | None:
    """Lexical lookup of ``name`` from ``site``, innermost scope outward.

    Where one scope binds the name more than once (four independent ``_fake_gate`` defs live
    in ``test_redo_gate_safety.py``), the nearest def *preceding* the site wins — that is what
    is actually in effect at the assignment.
    """
    scope: ast.AST | None = enclosing.get(site, tree)
    while scope is not None:
        candidates = _defs_bound_in(scope).get(name)
        if candidates:
            before = [c for c in candidates if c.lineno <= site.lineno]  # type: ignore[attr-defined]
            return max(before or candidates, key=lambda c: c.lineno)  # type: ignore[attr-defined]
        scope = enclosing.get(scope) if scope is not tree else None
    return None


def _returned_inner_def(factory: ast.AST) -> ast.AST | None:
    """The def a stub factory hands back (``def _f(...): async def _gate(...): ...; return _gate``)."""
    for node in ast.walk(factory):
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Name):
            for candidate in ast.walk(factory):
                if _is_func(candidate) and candidate.name == node.value.id:  # type: ignore[attr-defined]
                    return candidate
    return None


# ───────────────────────────── the census ─────────────────────────────


class _Stub:
    def __init__(self, path: Path, lineno: int, label: str, fn: ast.AST | None, drop_self: bool):
        self.rel = path.relative_to(BACKEND).as_posix()
        self.lineno = lineno  # where the stub is installed / declared
        self.label = label
        self.fn = fn
        self.drop_self = drop_self

    @property
    def where(self) -> str:
        """Point at the ``def`` — that is the line the fixer has to edit."""
        if self.fn is None:
            return f"{self.rel}:{self.lineno}"
        def_line = self.fn.lineno  # type: ignore[attr-defined]
        if def_line == self.lineno:
            return f"{self.rel}:{def_line}"
        return f"{self.rel}:{def_line} (installed at :{self.lineno})"


def _python_files() -> list[Path]:
    return sorted(
        p
        for p in BACKEND.rglob("*.py")
        if not _SKIP_DIR_PARTS.intersection(p.parts)
    )


def _collect_stubs() -> list[_Stub]:
    """Every substitute for ``_run_review_gate``: monkeypatched functions, factory-returned
    inner functions, and class-based engine doubles (which no assignment census can see)."""
    stubs: list[_Stub] = []
    for path in _python_files():
        try:
            tree = _parse(path)
        except SyntaxError as exc:  # a file this guard cannot read is a hole, not a pass
            stubs.append(_Stub(path, getattr(exc, "lineno", 0) or 0, f"<unparseable: {exc}>", None, False))
            continue
        enclosing = _scope_chain(tree)

        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Attribute) and t.attr == METHOD for t in node.targets
            ):
                value = node.value
                if isinstance(value, ast.Name):
                    fn = _resolve_name(value.id, node, tree, enclosing)
                    stubs.append(_Stub(path, node.lineno, value.id, fn, drop_self=False))
                elif isinstance(value, ast.Call) and isinstance(value.func, ast.Name):
                    factory = _resolve_name(value.func.id, node, tree, enclosing)
                    inner = _returned_inner_def(factory) if factory is not None else None
                    label = f"{value.func.id}() -> {getattr(inner, 'name', '?')}"
                    stubs.append(_Stub(path, node.lineno, label, inner, drop_self=False))
                else:
                    stubs.append(
                        _Stub(path, node.lineno, f"<unresolvable: {ast.unparse(value)}>", None, False)
                    )

            if isinstance(node, ast.ClassDef):
                for member in node.body:
                    if _is_func(member) and member.name == METHOD:  # type: ignore[attr-defined]
                        if path == ENGINE and node.name == "ExecutionEngine":
                            continue  # the real method, not a double
                        stubs.append(
                            _Stub(path, member.lineno, f"{node.name}.{METHOD}", member, drop_self=True)
                        )
    return stubs


def _real_parameters() -> list[str]:
    tree = _parse(ENGINE)
    for node in ast.walk(tree):
        if _is_func(node) and node.name == METHOD:  # type: ignore[attr-defined]
            args = node.args  # type: ignore[attr-defined]
            names = [a.arg for a in list(args.posonlyargs) + list(args.args) + list(args.kwonlyargs)]
            return [n for n in names if n != "self"]
    raise AssertionError(f"{METHOD} not found in {ENGINE} — this guard's premise is gone")


# ───────────────────────────── the tests ─────────────────────────────


def test_engine_signature_is_discoverable() -> None:
    """The whole guard is derived from this; if it stops resolving, everything else is vacuous."""
    real = _real_parameters()
    assert real[:4] == ["pipeline_run_id", "agent_id", "agent_name", "output"]
    assert len(real) >= 4


def test_stub_census_is_not_vacuous() -> None:
    """A resolver that quietly finds nothing would pass forever. Make that loud."""
    stubs = _collect_stubs()
    assert len(stubs) >= _MIN_STUBS, (
        f"only {len(stubs)} gate stubs found (expected >= {_MIN_STUBS}) — the AST sweep is "
        f"probably broken, not the codebase"
    )
    scanned = {s.rel for s in stubs}
    missing = [f for f in _REQUIRED_FILES if f not in scanned]
    assert not missing, f"the sweep no longer sees known stub sites: {missing}"


def test_every_gate_stub_accepts_the_real_signature() -> None:
    """Every double for ``_run_review_gate`` must bind the engine's full keyword call."""
    real = _real_parameters()
    call = {name: None for name in real}

    unresolved: list[str] = []
    broken: list[str] = []
    for stub in _collect_stubs():
        where = stub.where
        if stub.fn is None:
            unresolved.append(f"  {where} — {stub.label}")
            continue
        try:
            _signature_of(stub.fn, drop_self=stub.drop_self).bind(**call)
        except TypeError as exc:
            accepted = {
                p.arg
                for p in list(stub.fn.args.posonlyargs)  # type: ignore[attr-defined]
                + list(stub.fn.args.args)  # type: ignore[attr-defined]
                + list(stub.fn.args.kwonlyargs)  # type: ignore[attr-defined]
            }
            missing = [p for p in real if p not in accepted]
            broken.append(f"  {where} — {stub.label}(): {exc}\n      cannot accept: {missing}")

    report = []
    if unresolved:
        report.append(
            "Gate stubs this guard could not resolve (make them locally resolvable so the\n"
            "guard keeps covering them — a silent skip is how this defect family survives):\n"
            + "\n".join(unresolved)
        )
    if broken:
        report.append(
            f"Gate stubs that cannot accept the engine's real {METHOD} call.\n"
            f"Real parameters (derived from engine.py): {real}\n"
            "Add **kwargs to each stub below (and FORWARD it, if the stub wraps the original):\n"
            + "\n".join(broken)
        )
    if report:
        pytest.fail("\n\n".join(report), pytrace=False)
