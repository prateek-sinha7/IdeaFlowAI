"""Static scan: every bare-Name Store/Load of selected locals inside _reconcile_terminal_status."""
import ast, sys
src_path = sys.argv[1]
names = set(sys.argv[2:])
tree = ast.parse(open(src_path).read())
fn = next(n for n in ast.walk(tree)
          if isinstance(n, ast.AsyncFunctionDef) and n.name == "_reconcile_terminal_status")
print(f"function lines {fn.lineno}-{fn.end_lineno}")
for node in ast.walk(fn):
    if isinstance(node, ast.Name) and node.id in names:
        kind = type(node.ctx).__name__
        print(f"  {node.id:<18} {kind:<6} line {node.lineno}")
