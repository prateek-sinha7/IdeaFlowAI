"""Read-only projection of the two surfaces QA-KB-117 says disagree.

grid    = what AccountSettings.tsx:85-88 renders (TIER_PIPELINES minus *_revision, kept only if PIPELINE_DISPLAY has it)
catalog = what HomeLaunchGrid.tsx renders as ENABLED (user_launchable, not beta, canRunPipeline(tier,id))
modal   = UpgradePlanModal.tsx:37-41 'unlocks N more deliverable types'
"""
import re, sys, yaml
from pathlib import Path

REPO = Path(sys.argv[1])
FE_ENT = (REPO / "frontend/src/lib/entitlements.ts").read_text()
SETTINGS = (REPO / "frontend/src/components/settings/AccountSettings.tsx").read_text()
WF = REPO / "backend/agents/workflows"

# same parser the repo's own parity test uses (backend/tests/unit/services/test_entitlement_parity.py:42-55)
block = re.search(r"TIER_PIPELINES[^=]*=\s*\{(.*?)\n\};", FE_ENT, re.S).group(1)
block = re.sub(r"//[^\n]*", "", block)
tiers = {t: set(re.findall(r'"([\w]+)"', e)) for t, e in re.findall(r"(\w+):\s*new Set\(\[(.*?)\]\)", block, re.S)}

disp = re.search(r"const PIPELINE_DISPLAY[^=]*=\s*\{(.*?)\n\};", SETTINGS, re.S).group(1)
display_keys = set(re.findall(r"^\s*(\w+):\s*\{\s*label", disp, re.M))

man = {}
for d in sorted(WF.iterdir()):
    f = d / "workflow.yaml"
    if f.is_file():
        y = yaml.safe_load(f.read_text())
        man[y["id"]] = dict(launchable=bool(y.get("user_launchable")), beta=bool(y.get("is_beta")), name=y.get("display_name"))

EX = re.compile(r"^(ex_|sample_|sc001)", re.I)
print("PIPELINE_DISPLAY keys:", sorted(display_keys))
print()
for t in ("basic", "hexaware", "pro", "enterprise"):
    base = {p for p in tiers[t] if not p.endswith("_revision")}
    grid = {p for p in base if p in display_keys}
    cat_launch = {i for i, m in man.items() if m["launchable"]}
    cat_enabled = {i for i in cat_launch if not man[i]["beta"] and i in tiers[t]}
    cat_examples = {i for i in cat_enabled if EX.match(i)}
    cat_product = cat_enabled - cat_examples
    cat_beta_entitled = {i for i in cat_launch if man[i]["beta"] and i in tiers[t]}
    print(f"== {t}")
    print("  grid (renders)                     :", sorted(grid))
    print("  catalog enabled product            :", sorted(cat_product))
    print("  catalog enabled engine examples    :", sorted(cat_examples))
    print("  catalog Coming Soon but entitled   :", sorted(cat_beta_entitled))
    print("  OMITTED by grid (catalog offers)   :", sorted((cat_product | cat_examples) - grid))
    print("  LISTED by grid but catalog does not enable:", sorted(grid - (cat_product | cat_examples)))
    print("  entitled base ids with no manifest :", sorted(p for p in base if p not in man))
print()
order = ["basic", "pro", "enterprise"]
for cur, nxt in (("basic", "pro"), ("pro", "enterprise"), ("hexaware", "enterprise"), ("basic", "enterprise")):
    modal = {p for p in tiers[nxt] if not p.endswith("_revision") and p not in tiers[cur]}
    gridcur = {p for p in tiers[cur] if not p.endswith("_revision") and p in display_keys}
    gridnxt = {p for p in tiers[nxt] if not p.endswith("_revision") and p in display_keys}
    print(f"modal {cur}->{nxt}: says 'unlocks {len(modal)} more deliverable types' ; grid delta = {len(gridnxt - gridcur)} ; modal-only ids = {sorted(modal - (gridnxt - gridcur))}")
