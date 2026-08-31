#!/usr/bin/env python3
"""Cluster the open card store by FIX SITE, not by symptom, into OPEN-ISSUES-DEDUP.md.

The line files one root ISS card plus N sibling cards per bug. Siblings are the same
defect in another caller, so they do not each need their own analyze->fix->verify trip.
This groups them so one fix and one test can close a family.

    python3 bug-hunter/tools/dedup.py

Regenerate rather than editing OPEN-ISSUES-DEDUP.md by hand.

Tiers, most-certain first:
  A'  sibling whose declared root is ALREADY resolved -> the fix exists, replicate it
  A   declared family, root and siblings both still open -> merge, one line trip
  B   same file AND same defect class -> proposed merge, needs a human look
  C   everything else -> stays its own row

A merge is only proposed when cards share a FIX SITE, not merely a symptom class:
two Escape-key bugs in unrelated components are one class and two diffs.
"""
import collections, glob, json, os, re, subprocess, sys
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CARDS = os.path.join(ROOT, ".knowledge", "cards")
OUT = os.path.join(ROOT, "bug-hunter", "OPEN-ISSUES-DEDUP.md")
OPEN_STATUSES = ("open", "deferred")

# A card claims kinship in prose; these are the phrasings the analyzers actually used.
SIBLING = re.compile(
    r"(?:sibling of|siblings? of|same [a-z0-9-]+ (?:as|gap as)|duplicate of|same as"
    r"|shares the same [a-z ]+ as|identical to)\s*\[?((?:ISS|BUG|FIX)-[0-9]+)", re.I)

# Defect class, used ONLY to qualify a same-file merge -- never to merge across files.
CLASS = [
    ("confirm-dialog",  r"window\.confirm|no confirm|zero confirm|without confirmation|confirmation (dialog|prompt)"),
    ("keyboard-a11y",   r"\bEscape\b|focus trap|tabIndex|role=|keyboard|Enter/Space|aria-"),
    ("double-submit",   r"synchronous guard|double[- ]submit|rapid (repeated )?click|duplicate (POST|concurrent)|useRef-based"),
    ("route-depth",     r"depth guard|parseViewPath|head===|sub-path|unreachable route"),
    ("list-cap",        r"caps? at 50|pagination|silently caps|first 50|page size"),
    ("silent-discard",  r"silently (discard|drop|no-op|swallow)|never (persist|calls|sends)|no API call|in-memory (only|ref)"),
    ("stale-state",     r"stale|bleeds? through|not cleared|leaks? (the )?previous|prior run's"),
    ("error-surfacing", r"error (is |)swallow|no error (banner|shown)|silently fails|422 echo|raw JSON"),
]


def repo_tree():
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True)
    return {l.strip() for l in out.stdout.splitlines() if l.strip()}


def repo_index():
    """basename -> paths, so a card that recorded only `useWorkflow.ts` can still be placed."""
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True)
    idx = collections.defaultdict(list)
    for line in out.stdout.splitlines():
        idx[os.path.basename(line.strip())].append(line.strip())
    return idx


def resolve_site(globs, index, tree):
    """Best-effort fix site, anchored to paths that actually exist in the repo.

    Cards were written by many agents over months and their globs are inconsistent:
    full paths, repo-relative-without-prefix (`app/api/runs.py`), bare filenames
    (`useWorkflow.ts`), and a few that are neither (`/tmp/sse_pool_repro2.py`,
    `uvicorn/server.py`). Anything that cannot be anchored is dropped rather than
    carried as a fake fix site -- an unanchored path cannot be collision-checked.
    """
    out = set()
    for g in globs:
        if g in tree:
            out.add(g)
            continue
        for prefix in ("backend/", "frontend/"):          # prefix-stripped paths
            if prefix + g in tree:
                out.add(prefix + g)
                break
        else:
            if "/" not in g:                              # bare filename
                hits = index.get(g, [])
                if len(hits) == 1:                        # ambiguous stays unplaced
                    out.add(hits[0])
    return sorted(out)


def load_cards():
    cards = {}
    for path in glob.glob(os.path.join(CARDS, "*.md")):
        text = open(path, encoding="utf-8").read()
        m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
        if not m:
            continue
        try:
            fm = yaml.safe_load(m.group(1)) or {}
        except yaml.YAMLError:
            continue
        if not isinstance(fm, dict) or not fm.get("id"):
            continue
        body = m.group(2)
        applies = fm.get("applies_to") or {}
        globs = [str(x) for x in (applies.get("globs") or [])] if isinstance(applies, dict) else []
        modules = [str(x) for x in (applies.get("modules") or [])] if isinstance(applies, dict) else []
        depends = []
        rel = re.search(r"<!-- RELATED -->(.*?)<!-- /RELATED -->", body, re.S)
        if rel:
            dm = re.search(r"\*\*Depends on:\*\*(.*?)(?:\n\n|\*\*Referenced|\Z)", rel.group(1), re.S)
            if dm:
                depends = re.findall(r"\[((?:ISS|BUG|FIX|ADR)-[0-9A-Za-z-]+)\]", dm.group(1))
        cards[str(fm["id"])] = dict(
            cid=str(fm["id"]), file=os.path.basename(path), type=str(fm.get("type", "")),
            status=str(fm.get("status", "")), title=str(fm.get("title", "")),
            summary=str(fm.get("compact_summary", "")), globs=globs, depends=depends,
            date=str(fm.get("last_updated", "")), text=text)
    return cards



# --- work batches -----------------------------------------------------------
#
# Grouping for EXECUTION, not for merging. A batch is not "one fix" -- it is one
# worker holding one file's context and clearing every open card in it.
#
# Three things make this pay:
#   1. Comprehension is amortised. DashboardLayout.tsx is ~2400 lines; reading it
#      once for 11 cards beats reading it 11 times.
#   2. One test run and one browser verify per batch instead of per card.
#
# Assignment is a greedy max-coverage partition: every card lands in exactly one
# batch, and a card with several globs goes to whichever file carries the most of
# its unassigned neighbours.
#
# A partition by CARD is not by itself safe to run in parallel. A card with globs
# [A, B] sits in batch A but still WRITES B, so it collides with the batch that
# owns B -- measured, 20 such conflicts. Merging every conflicting pair instead
# collapses the frontend into one 124-card component, which is not schedulable.
# So batches carry a conflict graph and are coloured into ROUNDS (see schedule):
# two batches share a round only when the files they write are disjoint.

DOMAIN_RULES = [
    (r"^frontend/src/components/workflow/composer/", "frontend · composer"),
    (r"^frontend/src/components/workflow/",          "frontend · workflow"),
    (r"^frontend/src/components/library/",           "frontend · library"),
    (r"^frontend/src/components/history/",           "frontend · history"),
    (r"^frontend/src/components/settings/",          "frontend · settings"),
    (r"^frontend/src/components/preview/",           "frontend · preview"),
    (r"^frontend/src/components/layout/",            "frontend · layout"),
    (r"^frontend/src/components/",                   "frontend · components"),
    (r"^frontend/src/hooks/",                        "frontend · hooks"),
    (r"^frontend/src/(lib|context|types)/",          "frontend · lib"),
    (r"^frontend/src/app/",                          "frontend · routes"),
    (r"^frontend/",                                  "frontend · other"),
    (r"^backend/app/api/",                           "backend · api"),
    (r"^backend/app/(core|engine|services)/",        "backend · engine"),
    (r"^backend/",                                   "backend · other"),
    (r"^tests/integration/",                         "tests · integration"),
    (r"^tests/",                                     "tests · other"),
    (r"^(\.planning|docs)/",                         "docs · planning"),
    (r"^(\.claude|tools|scripts)/",                  "tooling"),
    (r"^bug-hunter/",                                "tooling"),
]


def domain_of(path):
    for pat, name in DOMAIN_RULES:
        if re.match(pat, path):
            return name
    return "unclassified"


def card_domain(card):
    """Every card gets a domain, even one with no usable fix site."""
    doms = [domain_of(p) for p in card["site"]]
    if doms:
        return collections.Counter(doms).most_common(1)[0][0]
    mods = " ".join(str(m) for m in (card.get("modules") or []))
    hay = f"{mods} {card['title']} {card['summary']}".lower()
    for pat, name in (("backend", "backend · unplaced"), ("api", "backend · unplaced"),
                      ("test", "tests · unplaced")):
        if pat in hay:
            return name
    return "frontend · unplaced"


def build_batches(opens):
    """Greedy max-coverage partition of open cards by fix site."""
    unassigned = {cid for cid, c in opens.items() if c["site"]}
    batches = []
    while True:
        counts = collections.Counter()
        for cid in unassigned:
            for site in opens[cid]["site"]:
                counts[site] += 1
        if not counts:
            break
        site, n = counts.most_common(1)[0]
        if n < 2:
            break
        members = sorted(c for c in unassigned if site in opens[c]["site"])
        batches.append({"key": site, "kind": "file", "domain": domain_of(site),
                        "members": members})
        unassigned -= set(members)

    # whatever is left has no file-neighbour: bucket it by domain so a worker still
    # gets a coherent slice rather than 60 unrelated one-offs.
    leftovers = collections.defaultdict(list)
    for cid in sorted(unassigned):
        leftovers[opens[cid]["domain"]].append(cid)
    for dom, members in sorted(leftovers.items()):
        batches.append({"key": dom, "kind": "domain", "domain": dom,
                        "members": sorted(members)})

    # cards with no usable fix site at all (legacy cards with 20+ noisy globs, or none)
    unplaced = collections.defaultdict(list)
    for cid in sorted(cid for cid, c in opens.items() if not c["site"]):
        unplaced[opens[cid]["domain"]].append(cid)
    for dom, members in sorted(unplaced.items()):
        batches.append({"key": f"{dom} — fix site not recorded", "kind": "unsited",
                        "domain": dom, "members": sorted(members)})
    return batches


def schedule(batches, opens):
    """Colour batches into rounds; a round's batches write mutually disjoint files."""
    writes = [set(g for m in b["members"] for g in opens[m]["site"]) for b in batches]
    adj = collections.defaultdict(set)
    for i in range(len(batches)):
        for j in range(i + 1, len(batches)):
            if writes[i] & writes[j]:
                adj[i].add(j)
                adj[j].add(i)
    colour = {}
    # most-constrained first keeps the round count near the clique lower bound
    for i in sorted(range(len(batches)), key=lambda x: -len(adj[x])):
        used = {colour[j] for j in adj[i] if j in colour}
        c = 0
        while c in used:
            c += 1
        colour[i] = c
    for i, b in enumerate(batches):
        b["round"] = colour[i] + 1
        b["writes"] = sorted(writes[i])
    return (max(colour.values()) + 1) if colour else 0


def classify(card):
    hay = f"{card['title']} {card['summary']}"
    return [name for name, pat in CLASS if re.search(pat, hay, re.I)]


def main():
    index = repo_index()
    tree = repo_tree()
    cards = load_cards()
    opens = {k: v for k, v in cards.items() if v["status"] in OPEN_STATUSES}
    for c in opens.values():
        c["declared"] = sorted(set(SIBLING.findall(f"{c['title']} || {c['summary']}")))
        # A hunt card names 1-5 real paths. Legacy GROUNDED-CONTEXT cards carry 20+
        # auto-derived ones including bare filenames -- useless as a fix site.
        c["site"] = resolve_site(c["globs"], index, tree)
        c["domain"] = card_domain(c)
        c["wide"] = len(c["site"]) > 5
        c["classes"] = classify(c)

    # --- tier A' : declared root already resolved -------------------------------
    orphan = collections.defaultdict(list)
    # --- tier A  : declared root still open -------------------------------------
    parent = {k: k for k in opens}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for cid, c in opens.items():
        for p in c["declared"]:
            if p in opens:
                ra, rb = find(cid), find(p)
                if ra != rb:
                    parent[max(ra, rb)] = min(ra, rb)
            elif p in cards:
                orphan[p].append(cid)

    grouped = collections.defaultdict(list)
    for cid in opens:
        grouped[find(cid)].append(cid)
    tier_a = {r: sorted(m) for r, m in grouped.items() if len(m) > 1}

    # which FIX card carries the landed diff for each resolved root
    fixfor = collections.defaultdict(set)
    for c in cards.values():
        if c["type"] != "fix":
            continue
        for root in orphan:
            if re.search(rf"\b{re.escape(root)}\b", c["text"]):
                fixfor[root].add(c["cid"])

    claimed = {c for m in tier_a.values() for c in m} | {c for v in orphan.values() for c in v}

    # --- tier B : same file AND same class --------------------------------------
    buckets = collections.defaultdict(set)
    for cid, c in opens.items():
        if cid in claimed:
            continue
        for k in c["classes"]:
            for site in c["site"]:
                buckets[(site, k)].add(cid)
    tier_b = {k: sorted(v) for k, v in buckets.items() if len(v) > 1}
    in_b = {c for v in tier_b.values() for c in v}

    singles = sorted(set(opens) - claimed - in_b)
    batches = build_batches(opens)
    n_rounds = schedule(batches, opens)

    families = len(orphan) + len(tier_a) + len(tier_b)
    rows_after = families + len(singles)

    def link(cid):
        c = cards.get(cid)
        return f"[{cid}](../.knowledge/cards/{c['file']})" if c else f"`{cid}`"

    def desc(cid, n=150):
        c = cards.get(cid, {})
        s = (c.get("summary") or c.get("title") or "").replace("\n", " ").replace("|", "\\|")
        return (s[: n - 1] + "…") if len(s) > n else s

    L = []
    w = L.append
    w("# Open issues — deduplicated by fix site")
    w("")
    w("Every open/deferred card in `.knowledge/`, grouped by **where the fix goes** rather")
    w("than by what the user saw. Companion to [`OPEN-ISSUES.md`](OPEN-ISSUES.md), which is")
    w("the flat per-symptom register.")
    w("")
    w("Generated from the card store — regenerate rather than editing rows by hand:")
    w("")
    w("```")
    w("python3 bug-hunter/tools/dedup.py")
    w("```")
    w("")
    multi_b = [b for b in batches if len(b["members"]) > 1]
    w(f"**{len(opens)} open cards → {rows_after} units of work** "
      f"({families} families + {len(singles)} singletons), "
      f"schedulable as **{len(batches)} work batches** — see "
      f"[Work batches](#work-batches--how-to-actually-run-this) for the execution view.")
    w("")
    w("A merge is proposed only where cards share a **fix site**, not merely a symptom")
    w("class. Two Escape-key bugs in unrelated components are one class and two diffs —")
    w("merging those would close a family while a member is still broken.")
    w("")
    w("| tier | what it means | families | cards |")
    w("|---|---|---|---|")
    w(f"| A′ | root **already fixed**, siblings still open — replicate the landed diff | {len(orphan)} | {sum(len(v) for v in orphan.values())} |")
    w(f"| A | declared family, root and siblings both open — one line trip | {len(tier_a)} | {sum(len(v) for v in tier_a.values())} |")
    w(f"| B | same file **and** same defect class — proposed, needs review | {len(tier_b)} | {len(in_b)} |")
    w(f"| C | no kin found — stays its own row | — | {len(singles)} |")
    w("")
    w("---")
    w("")

    # ---- Tier A' ---------------------------------------------------------------
    w("## Tier A′ — the fix already landed, the siblings were left open")
    w("")
    w("**This is the finding that matters.** For each root below, the line fixed the call")
    w("site the bug report named, wrote a FIX card, and closed the root — while the sibling")
    w("cards naming the *other* call sites stayed open. The expensive phases are already")
    w("paid for: root cause is known, the diff exists, the pattern is proven.")
    w("")
    w("These do not need validate or analyze. They need the named FIX card read and its")
    w("change applied at the sibling's line. Send them straight to **fix**.")
    w("")
    w("| root (resolved) | landed fix | open siblings | what the siblings are |")
    w("|---|---|---|---|")
    for root in sorted(orphan, key=lambda r: (-len(orphan[r]), r)):
        kids = sorted(orphan[root])
        fx = ", ".join(link(f) for f in sorted(fixfor.get(root, ()))) or "**none found**"
        w(f"| {link(root)} | {fx} | {', '.join(link(k) for k in kids)} | {desc(kids[0], 110)} |")
    w("")
    if any(not fixfor.get(r) for r in orphan):
        missing = sorted(r for r in orphan if not fixfor.get(r))
        w(f"> **{len(missing)} root(s) carry no FIX card**: {', '.join(missing)}. The root is marked")
        w("> resolved but nothing records the diff — treat these siblings as tier C until that")
        w("> is explained, because there may be no landed change to replicate.")
        w("")
    w("---")
    w("")

    # ---- Tier A ----------------------------------------------------------------
    w("## Tier A — declared families, both ends still open")
    w("")
    w("The cards name each other. One fix, one test, one verify closes the set.")
    w("")
    for r, members in sorted(tier_a.items(), key=lambda x: -len(x[1])):
        w(f"### {link(r)} + {len(members) - 1} sibling(s)")
        w("")
        w(f"{cards[r]['title']}")
        w("")
        w("| card | fix site | summary |")
        w("|---|---|---|")
        for m in members:
            site = ", ".join(f"`{s}`" for s in cards[m]["site"]) or "—"
            w(f"| {link(m)} | {site} | {desc(m, 130)} |")
        w("")
    w("---")
    w("")

    # ---- Tier B ----------------------------------------------------------------
    w("## Tier B — same file, same defect class (proposed — review before merging)")
    w("")
    w("These share a file *and* a defect class, which is the strongest signal available")
    w("short of a card saying so. It is still a guess: confirm the two really collapse to")
    w("one diff before merging, and split them back out if they do not.")
    w("")
    w("| fix site | class | cards | first card |")
    w("|---|---|---|---|")
    for (site, k), ids in sorted(tier_b.items(), key=lambda x: (-len(x[1]), x[0][0])):
        w(f"| `{site}` | {k} | {', '.join(link(i) for i in ids)} | {desc(ids[0], 100)} |")
    w("")

    # ---- class campaigns -------------------------------------------------------
    campaigns = collections.defaultdict(set)
    for cid, c in opens.items():
        for k in c["classes"]:
            campaigns[k].add(cid)
    w("### Class campaigns (one sweep, many diffs — not one merge)")
    w("")
    w("Same defect class across *different* files. These do **not** merge into one row, but")
    w("one engineer holding the pattern in their head can clear the set far faster than the")
    w("line can trip on each. Batch them onto one worker; keep the rows separate.")
    w("")
    w("| class | cards |")
    w("|---|---|")
    for k, v in sorted(campaigns.items(), key=lambda x: -len(x[1])):
        w(f"| {k} | {len(v)}: {', '.join(link(i) for i in sorted(v))} |")
    w("")
    w("---")
    w("")

    # ---- work batches ----------------------------------------------------------
    w("## Work batches — how to actually run this")
    w("")
    w("The tiers above say what *is* one defect. This says what to hand one worker.")
    w("")
    w("A batch is **not** a merged fix — the cards in it stay separate defects with")
    w("separate tests. It is one worker opening one file once and clearing every open")
    w("card in it. That pays twice:")
    w("")
    w("1. **Comprehension amortises.** `DashboardLayout.tsx` is ~2,400 lines. Reading it")
    w("   once for 11 cards beats reading it 11 times.")
    w("2. **One test run and one browser verify per batch**, not per card. Verify is the")
    w("   lane-bound phase, so this is what actually moves the runtime.")
    w("")
    w("### Rounds — what may run at the same time")
    w("")
    w("Batching by file is **not** on its own safe to parallelise. A card whose `globs`")
    w("name two files sits in one batch but writes both, so it collides with the batch")
    w("that owns the other — there are 20 such conflicts here. Merging every conflicting")
    w("pair instead collapses the frontend into a single 124-card blob.")
    w("")
    w("So batches are coloured into **rounds**: two batches share a round only when the")
    w("files they write are disjoint. **Every batch in a round can run in parallel with")
    w("no possibility of collision. Rounds run one after another.**")
    w("")
    w("| round | batches | cards |")
    w("|---|---|---|")
    for r in range(1, n_rounds + 1):
        rb = [b for b in batches if b.get("round") == r]
        w(f"| {r} | {len(rb)} — all concurrent | {sum(len(b['members']) for b in rb)} |")
    w("")
    w(f"**{len(multi_b)} multi-card batches** carry "
      f"{sum(len(b['members']) for b in multi_b)} of the {len(opens)} cards.")
    w("")
    doms = collections.defaultdict(list)
    for b in batches:
        doms[b["domain"]].append(b)

    w("### Domains — each block is one coherent area of the app")
    w("")
    w("| domain | cards | batches | earliest round |")
    w("|---|---|---|---|")
    for dom in sorted(doms, key=lambda d: -sum(len(b["members"]) for b in doms[d])):
        bs = doms[dom]
        w(f"| [{dom}](#{dom.replace(' · ', '--').replace(' ', '-')}) | "
          f"{sum(len(b['members']) for b in bs)} | {len(bs)} | "
          f"{min(b.get('round', 99) for b in bs)} |")
    w("")
    w("Every card carries a domain — there is no uncategorised bucket. A row marked")
    w("*fix site not recorded* is still domain-placed; what it lacks is a file, so it")
    w("cannot be collision-checked and must be triaged before it is scheduled.")
    w("")

    for dom in sorted(doms, key=lambda d: -sum(len(b["members"]) for b in doms[d])):
        bs = sorted(doms[dom], key=lambda x: (x.get("round", 99), -len(x["members"])))
        w(f"#### {dom}")
        w("")
        w(f"{sum(len(b['members']) for b in bs)} cards across {len(bs)} batch(es).")
        w("")
        w("| round | fix site | cards | members |")
        w("|---|---|---|---|")
        for b in bs:
            key = f"`{b['key']}`" if b["kind"] == "file" else f"**{b['key']}**"
            w(f"| {b.get('round','—')} | {key} | {len(b['members'])} | "
              f"{', '.join(link(m) for m in b['members'])} |")
        w("")

    # ---- Tier C ----------------------------------------------------------------
    w("## Tier C — no kin found")
    w("")
    w(f"{len(singles)} cards with no declared sibling and no same-file/same-class neighbour.")
    w("Each is its own unit of work.")
    w("")
    w("| card | fix site | summary |")
    w("|---|---|---|")
    for cid in singles:
        site = ", ".join(f"`{s}`" for s in cards[cid]["site"]) or "—"
        w(f"| {link(cid)} | {site} | {desc(cid, 120)} |")
    w("")

    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")

    print(f"wrote {OUT}")
    print(f"  {len(opens)} open cards -> {rows_after} units "
          f"({families} families + {len(singles)} singletons)")
    print(f"  tier A' {len(orphan)} roots / {sum(len(v) for v in orphan.values())} siblings")
    print(f"  tier A  {len(tier_a)} families / {sum(len(v) for v in tier_a.values())} cards")
    print(f"  tier B  {len(tier_b)} proposed / {len(in_b)} cards")
    print(f"  tier C  {len(singles)} singletons")
    print(f"  batches {len(batches)} total, {len(multi_b)} multi-card "
          f"covering {sum(len(b['members']) for b in multi_b)} cards")
    for r in range(1, n_rounds + 1):
        rb = [b for b in batches if b.get("round") == r]
        print(f"    round {r}: {len(rb):2} batches / "
              f"{sum(len(b['members']) for b in rb):3} cards, all parallel")


if __name__ == "__main__":
    sys.exit(main())
