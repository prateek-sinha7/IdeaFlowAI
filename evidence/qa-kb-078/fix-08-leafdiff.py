"""Structural review of a re-pinned events golden: every difference must be an ADDED key."""
import json, sys
from collections import Counter

old = json.load(open(sys.argv[1]))
new = json.load(open(sys.argv[2]))
allowed = set(sys.argv[3].split(",")) if len(sys.argv) > 3 else None

def leaves(x, p="$"):
    if isinstance(x, dict):
        for k, v in x.items():
            yield from leaves(v, f"{p}.{k}")
    elif isinstance(x, list):
        for i, v in enumerate(x):
            yield from leaves(v, f"{p}[{i}]")
    else:
        yield p, x

assert len(old) == len(new), (len(old), len(new))
assert [e.get("type") for e in old] == [e.get("type") for e in new], "type sequence changed"
lo, ln = dict(leaves(old)), dict(leaves(new))
removed = sorted(set(lo) - set(ln))
added = sorted(set(ln) - set(lo))
changed = sorted(p for p in set(lo) & set(ln) if lo[p] != ln[p])
print(f"events: {len(old)} -> {len(new)}; type sequence identical")
print(f"leaves: removed={len(removed)} changed={len(changed)} added={len(added)}")
for p in removed[:5] + changed[:5]:
    print("  NOT-AN-ADDITION:", p, repr(lo.get(p))[:120], "->", repr(ln.get(p))[:120])
key_counts = Counter(p.rsplit(".", 1)[-1] for p in added)
print("added keys:", dict(key_counts))
vals = Counter((p.rsplit(".", 1)[-1], type(ln[p]).__name__) for p in added)
print("added (key, value-type):", dict(vals))
per_type = Counter()
for i, e in enumerate(new):
    for k in ("task_id", "task_author_id", "worker_index"):
        if k in (e.get("data") or {}) and k not in (old[i].get("data") or {}):
            per_type[(e["type"], k)] += 1
print("per event type:")
for (t, k), n in sorted(per_type.items()):
    print(f"  {t:20s} {k:15s} {n}")
if allowed is not None:
    bad = [p for p in added if p.rsplit(".", 1)[-1] not in allowed]
    ok = not removed and not changed and not bad
    print("VERDICT:", "only allowed keys added" if ok else f"UNEXPECTED: bad={bad[:5]}")
