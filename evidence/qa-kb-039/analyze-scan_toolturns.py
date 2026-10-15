"""Every turn constructor that carries tool_calls: where does it sit?
 - inside a List (any other element types allowed) -> report position (LAST = suspect)
 - bare (returned / assigned / appended)          -> report enclosing def so callers can be checked
"""
import ast, sys, pathlib

ROOT = pathlib.Path(sys.argv[1])
TURN_NAMES = {"_ScriptedTurn", "ScriptedTurn", "_Turn", "Turn", "_FakeTurn"}

def cname(c):
    f = c.func
    return f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else None)

def tools(c):
    for kw in c.keywords:
        if kw.arg == "tool_calls":
            v = kw.value
            if isinstance(v, ast.List) and not v.elts: return False
            if isinstance(v, ast.Constant) and v.value in (None, False): return False
            return True
    return len(c.args) >= 2

class V(ast.NodeVisitor):
    def __init__(self, rel): self.rel, self.stack, self.parents, self.rows = rel, [], {}, []
    def generic_visit(self, node):
        for ch in ast.iter_child_nodes(node): self.parents[ch] = node
        super().generic_visit(node)
    def visit_FunctionDef(self, n):
        self.stack.append(n.name); self.generic_visit(n); self.stack.pop()
    visit_AsyncFunctionDef = visit_FunctionDef
    def visit_Call(self, n):
        if cname(n) in TURN_NAMES and tools(n):
            par = self.parents.get(n)
            fn = self.stack[-1] if self.stack else "<module>"
            if isinstance(par, ast.List):
                pos = par.elts.index(n); last = pos == len(par.elts) - 1
                self.rows.append((self.rel, n.lineno, fn, f"in-list {pos+1}/{len(par.elts)}", "LAST" if last else "ok"))
            else:
                self.rows.append((self.rel, n.lineno, fn, f"bare({type(par).__name__})", "check-callers"))
        self.generic_visit(n)

rows = []
for p in sorted(ROOT.rglob("*.py")):
    if ".venv" in p.parts: continue
    try: tree = ast.parse(p.read_text(encoding="utf-8"))
    except Exception: continue
    v = V(str(p.relative_to(ROOT.parent)))
    # pre-link parents for whole tree
    for par in ast.walk(tree):
        for ch in ast.iter_child_nodes(par): v.parents[ch] = par
    v.visit(tree); rows += v.rows

print(f"tool-calling turn constructors found: {len(rows)}")
print("\nSUSPECT (last element of its list):")
for r in rows:
    if r[4] == "LAST": print("  ", *r)
print("\nBARE (helper-built; need caller check):")
for r in rows:
    if r[4] == "check-callers": print("  ", *r)
print("\nSummary by position:", {k: sum(1 for r in rows if r[4]==k) for k in ('ok','LAST','check-callers')})
