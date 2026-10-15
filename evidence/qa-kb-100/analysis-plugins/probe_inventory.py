"""READ-ONLY probe: which registered capabilities are user_allowed=False, by kind."""
from collections import defaultdict
from agents.execution_engine.engine import _CAPABILITY_REGISTRY as R
from agents.capabilities import registry as reg

R.is_user_allowed("gate", "security")  # forces discover()
by_kind_no = defaultdict(list)
by_kind_yes = defaultdict(list)
for (kind, name), allowed in sorted(reg._TRUST.items()):
    (by_kind_yes if allowed else by_kind_no)[kind].append(name)
print("registered (kind,name) pairs with a recorded flag:", len(reg._TRUST))
print("user_allowed=False (these are what CAP-03 keeps off a user manifest):")
for kind in sorted(by_kind_no):
    print(f"  {kind:16s} {by_kind_no[kind]}")
print("user_allowed=True:")
for kind in sorted(by_kind_yes):
    print(f"  {kind:16s} {by_kind_yes[kind]}")
# names registered in _KNOWN with NO flag recorded (default False)
noflag = sorted(k for k in reg._KNOWN if k not in reg._TRUST)
print("registered but no flag recorded (is_user_allowed() defaults False):", noflag)
