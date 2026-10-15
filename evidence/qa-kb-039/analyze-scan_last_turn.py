"""AST scan: find every list literal of scripted turns whose LAST turn carries tool_calls.

A tool-calling last turn is replayed forever by a `turns[-1]` fallback model -> the deepagents
react loop never reaches a stop condition -> GraphRecursionError.
"""
import ast, sys, pathlib

ROOT = pathlib.Path(sys.argv[1])
TURN_NAMES = {"_ScriptedTurn", "ScriptedTurn", "_Turn", "Turn", "_turn", "_FakeTurn"}

def call_name(c):
    f = c.func
    if isinstance(f, ast.Name): return f.id
    if isinstance(f, ast.Attribute): return f.attr
    return None

def has_tool_calls(c):
    """True/False/None(unknown) for a turn Call node."""
    for kw in c.keywords:
        if kw.arg == "tool_calls":
            v = kw.value
            if isinstance(v, ast.List) and not v.elts: return False
            if isinstance(v, ast.Constant) and v.value in (None, False): return False
            return True
    # positional (texts, tool_calls, usage)
    if len(c.args) >= 2:
        v = c.args[1]
        if isinstance(v, ast.List) and not v.elts: return False
        if isinstance(v, ast.Constant) and v.value in (None, False): return False
        return True
    return False

hits, total_lists = [], 0
for p in sorted(ROOT.rglob("*.py")):
    if ".venv" in p.parts or "node_modules" in p.parts: continue
    try:
        tree = ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
    except Exception as e:
        print(f"PARSE-FAIL {p}: {e}"); continue
    for node in ast.walk(tree):
        if isinstance(node, ast.List) and node.elts:
            calls = [e for e in node.elts if isinstance(e, ast.Call) and call_name(e) in TURN_NAMES]
            if calls and len(calls) == len(node.elts):
                total_lists += 1
                last = calls[-1]
                tc = has_tool_calls(last)
                if tc:
                    hits.append((str(p.relative_to(ROOT.parent)), node.lineno, len(calls), last.lineno))
print(f"turn-list literals scanned: {total_lists}")
print(f"lists whose LAST turn carries tool_calls: {len(hits)}")
for h in hits:
    print(f"  {h[0]}:{h[1]}  turns={h[2]}  last-turn@line {h[3]}")
