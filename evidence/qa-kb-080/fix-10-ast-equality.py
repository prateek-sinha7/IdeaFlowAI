"""QA-KB-080 fix evidence: the three production edits are prose only.

Parses each file at HEAD and in the working tree, strips every docstring (comments are not
in the AST at all), and compares ast.dump. Equal = no executable change.
Run from the repo root: backend/.venv/bin/python evidence/qa-kb-080/fix-10-ast-equality.py
"""
import ast
import subprocess
import sys

FILES = [
    "backend/agents/execution_engine/kernel_services.py",
    "backend/agents/execution_engine/fanout.py",
    "backend/agents/capabilities/strategies/_fanout_stream.py",
]


def stripped(src: str) -> str:
    tree = ast.parse(src)
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(body, list) and body and isinstance(body[0], ast.Expr) \
                and isinstance(getattr(body[0], "value", None), ast.Constant) \
                and isinstance(body[0].value.value, str):
            body[0] = ast.Pass()
    return ast.dump(tree)


ok = True
for f in FILES:
    head = subprocess.run(["git", "show", f"HEAD:{f}"], capture_output=True, text=True, check=True).stdout
    now = open(f, encoding="utf-8").read()
    same = stripped(head) == stripped(now)
    raw = head == now
    ok &= same
    print(f"{f}: text changed={not raw}  executable AST identical={same}")
sys.exit(0 if ok else 1)
