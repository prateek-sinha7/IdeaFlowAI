"""Structural scan: every `self._x` used inside a ScopedStore method must exist on the class.

Run from backend/:  .venv/bin/python <this file>
Finds the two methods that still call the deleted `_acquire` (write_provenance_audit, update_wave_run_merge_state).
The same ~10 lines make the regression guard proposed in the ISS card (no I/O, belongs in tests/unit).
"""
import ast, pathlib

src = pathlib.Path("agents/authz.py").read_text()
cls = next(n for n in ast.parse(src).body if isinstance(n, ast.ClassDef) and n.name == "ScopedStore")
methods = {n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
defined = {m.name for m in methods} | {"_owner_id", "_workspace_id", "_session"}
bad = {
    m.name: sorted(
        a.attr
        for a in ast.walk(m)
        if isinstance(a, ast.Attribute) and isinstance(a.value, ast.Name) and a.value.id == "self" and a.attr not in defined
    )
    for m in methods
}
bad = {k: v for k, v in bad.items() if v}
print("methods referencing a missing self attribute:", bad)
assert not bad
