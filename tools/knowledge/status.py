#!/usr/bin/env python3
"""Report what the knowledge base holds and what has gone stale. Cheap.

Designed so `/velocity status` costs one bash call and ~20 lines of output.
Every check is a file count, a frontmatter header, or a git rev count -- it
never reads card bodies, never runs pydeps or dependency-cruiser, and never
writes anything. Read-only by construction.

    python3 tools/knowledge/status.py            # human-readable report
    python3 tools/knowledge/status.py --json     # same data, machine-readable

Exit code is 0 when everything is current, 1 when any check is STALE, so it
can also gate a pre-commit hook.
"""
from __future__ import annotations

import glob
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
K = ROOT / ".knowledge"

TYPE_CODES = {"FIX", "BUG", "ISS", "ADR"}
# Must stay in step with TYPE_CODE in tools/knowledge/normalize_card_ids.py.
TYPE_FOR = {
    "fix": "FIX", "bug": "BUG", "issue": "ISS", "adr": "ADR",
}
FM_ID = re.compile(r"^id:\s*(.+?)\s*$", re.M)
FM_TYPE = re.compile(r"^type:\s*(.+?)\s*$", re.M)


def git(*args) -> str:
    p = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    return p.stdout.strip() if p.returncode == 0 else ""


def as_int(value, default: int = -1) -> int:
    """Best-effort int. A status check must never crash on bad input.

    `state.yaml` is a generated file, but a half-written or hand-edited one is
    exactly the situation someone runs `status` to diagnose -- so every value
    read from it is untrusted. Returning the default surfaces the problem as a
    STALE row instead of a traceback.
    """
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def read_text_safe(path: Path) -> str:
    """Read a file that may be truncated, binary, or half-written.

    `status` is what you run WHEN things are broken, so every file it reads is
    untrusted -- a corrupt state.yaml or INDEX.md must surface as a STALE row,
    never as a UnicodeDecodeError traceback.
    """
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def read_yaml_ish(path: Path) -> dict:
    """Flat `key: value` scrape. Avoids a yaml dependency for a status check."""
    out = {}
    if not path.is_file():
        return out
    for line in read_text_safe(path).splitlines():
        m = re.match(r"^([a-z_]+):\s*(.*)$", line)
        if m and m.group(2):
            out[m.group(1)] = m.group(2).strip().strip("'\"")
    return out


def worktrees() -> list[dict]:
    """Every checkout of this repo: path, branch, HEAD, and which one is us.

    Reported unconditionally. Two checkouts on different branches produce
    legitimately different numbers, and a reader comparing one session's
    output against another's has no way to tell that apart from drift unless
    each report says which tree it came from.
    """
    out, cur = [], {}
    for line in (git("worktree", "list", "--porcelain") or "").splitlines():
        if line.startswith("worktree "):
            cur = {"path": line[len("worktree "):]}
            out.append(cur)
        elif line.startswith("HEAD ") and cur:
            cur["head"] = line[len("HEAD "):]
        elif line.startswith("branch ") and cur:
            cur["branch"] = line[len("branch "):].replace("refs/heads/", "")
        elif line.strip() == "detached" and cur:
            cur["branch"] = "(detached)"
    me = str(ROOT)
    for w in out:
        w["current"] = (w["path"] == me)
    return out


def read_block(path: Path, key: str) -> dict:
    """Scrape one indented `key:` block (e.g. cards_by_type) into a dict."""
    out = {}
    if not path.is_file():
        return out
    lines = read_text_safe(path).splitlines()
    try:
        start = next(i for i, ln in enumerate(lines) if ln.strip() == f"{key}:")
    except StopIteration:
        return out
    for ln in lines[start + 1:]:
        m = re.match(r"^\s+([A-Za-z_]+):\s*(\S+)\s*$", ln)
        if not m:
            break
        out[m.group(1)] = m.group(2)
    return out


def source_files() -> int:
    """Same file set build_architecture.py walks -- imported, not re-derived."""
    prev = sys.dont_write_bytecode
    try:
        # Importing a sibling module would drop tools/__pycache__/ on disk,
        # which breaks this module's read-only contract for the sake of a
        # bytecode cache nobody asked for.
        sys.dont_write_bytecode = True
        sys.path.insert(0, str(ROOT / "tools" / "knowledge"))
        import build_architecture as B  # noqa: PLC0415
        return len(B.scan_source_files())
    except Exception:
        return -1
    finally:
        sys.dont_write_bytecode = prev


def main() -> int:
    as_json = "--json" in sys.argv
    checks: list[tuple[str, str, str, str]] = []  # (area, found, expected, verdict)

    head = git("rev-parse", "HEAD")
    state = read_yaml_ish(K / "state.yaml")
    ctx = read_yaml_ish(K / "CONTEXT.md")

    # --- cards on disk vs what the index recorded ---
    #
    # Count files that are actually CARDS, not every *.md in the directory.
    # A stray README or scratch note is not a card, and counting it made this
    # row disagree with what build_index.py indexes -- producing a permanent
    # phantom STALE that no rebuild could ever clear. Non-cards are reported
    # separately so they stay visible rather than silently dropped.
    card_paths, noncard_paths = [], []
    for p in sorted(glob.glob(str(K / "cards" / "*.md"))):
        snippet = ""
        try:
            with open(p, encoding="utf-8", errors="replace") as fh:
                snippet = fh.read(1200)
        except OSError:
            pass
        (card_paths if snippet.lstrip("﻿ \t\r\n").startswith("---") else noncard_paths).append(p)
    cards_disk = len(card_paths)
    cards_state = as_int(state.get("cards_count"))
    checks.append((
        "cards", str(cards_disk), str(cards_state),
        "OK" if cards_disk == cards_state else "STALE",
    ))

    # --- architecture cards vs state + modules.json ---
    mod_disk = len(glob.glob(str(K / "architecture" / "MOD-*.md")))
    arch_state = as_int(state.get("architecture_count"))
    checks.append((
        "architecture cards", str(mod_disk), str(arch_state),
        "OK" if mod_disk == arch_state else "STALE",
    ))

    # --- architecture CONTENT freshness: files it covers vs files on disk ---
    mj = K / "architecture" / "modules.json"
    covered = -1
    if mj.is_file():
        try:
            covered = sum(m.get("file_count", 0) for m in json.loads(read_text_safe(mj))["modules"])
        except Exception:
            covered = -1
    on_disk = source_files()
    checks.append((
        "source files covered", str(covered), str(on_disk),
        "OK" if covered == on_disk and covered >= 0 else "STALE",
    ))

    # --- INDEX.md lines vs cards ---
    idx = K / "INDEX.md"
    idx_lines = sum(
        1 for ln in read_text_safe(idx).splitlines() if ln.startswith("- ")
    ) if idx.is_file() else -1
    checks.append((
        "INDEX.md entries", str(idx_lines), str(cards_disk),
        "OK" if idx_lines == cards_disk else "STALE",
    ))

    # --- is CONTEXT.md current? ---
    # Compare CONTENT, not commits. Two earlier attempts keyed this on
    # `built_from_commit`, and both were wrong for the same reason: the pack is
    # generated from the WORKING TREE, so its stamp is whatever HEAD happened to
    # be at build time -- which is one commit behind the moment the pack itself
    # is committed, and further behind if it was built over uncommitted cards
    # (importing 12 ADRs did exactly that). Neither is drift.
    #
    # The pack records how many cards and modules it folded in. Comparing those
    # to what is on disk answers the actual question and cannot be confused by
    # commit timing at all. `built_from_commit` stays in the frontmatter as
    # provenance; it just no longer decides the verdict.
    ctx_cards = as_int(ctx.get("cards_indexed"), -1)
    ctx_mods = as_int(ctx.get("modules_indexed"), -1)
    checks.append((
        "CONTEXT.md cards", str(ctx_cards), str(cards_disk),
        "OK" if ctx_cards == cards_disk else "STALE",
    ))
    checks.append((
        "CONTEXT.md modules", str(ctx_mods), str(mod_disk),
        "OK" if ctx_mods == mod_disk else "STALE",
    ))

    # --- how far the sync point trails HEAD ---
    # Same reasoning: commits alone are not drift. What matters is whether any
    # SOURCE file moved since the sync point, because that is what would make
    # the architecture stale. Commits touching only docs, tooling or the
    # knowledge base itself leave nothing for `sync` to reconcile.
    sync_commit = state.get("last_sync_commit", "")
    behind = git("rev-list", "--count", f"{sync_commit}..HEAD") if sync_commit else ""
    behind_n = int(behind) if behind.isdigit() else -1
    src_drift = ""
    if sync_commit and behind_n > 0:
        src_drift = git("diff", "--name-only", f"{sync_commit}..HEAD",
                        "--", "backend", "frontend")
    if behind_n == 0:
        sync_found, sync_verdict = "0", "OK"
    elif behind_n > 0 and src_drift == "":
        sync_found, sync_verdict = f"{behind_n} (no source change)", "OK"
    else:
        sync_found = str(behind_n if behind_n >= 0 else "?")
        sync_verdict = "STALE"
    checks.append(("commits since sync", sync_found, "0", sync_verdict))

    # --- source churn since the sync point (does architecture need a rebuild?) ---
    changed = -1
    if sync_commit:
        diff = git("diff", "--name-only", f"{sync_commit}..HEAD", "--", "backend", "frontend")
        changed = len([ln for ln in diff.splitlines() if ln.strip()]) if diff else 0
    checks.append((
        "source files changed", str(changed if changed >= 0 else "?"), "0",
        "OK" if changed == 0 else "STALE",
    ))

    # --- ID scheme conformance (reads frontmatter head only) ---
    #
    # Checks the id against the card's OWN `type:`, not just "is the first
    # token a known code". `REQ-REQ-DEL-01` starts with a valid code and so
    # passes the naive test while being exactly the corruption worth catching,
    # so a doubled type code is called out explicitly.
    bad_ids = 0
    for p in card_paths:
        with open(p, encoding="utf-8", errors="replace") as fh:
            headtext = fh.read(1200)
        m, mt = FM_ID.search(headtext), FM_TYPE.search(headtext)
        if not m or not mt:
            bad_ids += 1
            continue
        cid = m.group(1).strip("'\"")
        code = TYPE_FOR.get(mt.group(1).strip("'\"").lower())
        if code is None or not cid.upper().startswith(code + "-"):
            bad_ids += 1
            continue
        rest = cid[len(code) + 1:]
        if rest.upper().startswith(code + "-"):   # doubled prefix, e.g. REQ-REQ-...
            bad_ids += 1
    checks.append((
        "ID scheme conformance", str(cards_disk - bad_ids), str(cards_disk),
        "OK" if bad_ids == 0 else "STALE",
    ))

    # --- pending staged proposals ---
    staged = len([p for p in (K / ".stage").rglob("*") if p.is_file()]) if (K / ".stage").is_dir() else 0
    checks.append(("staged proposals", str(staged), "0", "OK" if staged == 0 else "PENDING"))
    checks.append((
        "non-card files in cards/", str(len(noncard_paths)), "0",
        "OK" if not noncard_paths else "NOTE",
    ))

    # Dotfiles are invisible to EVERY tool here -- glob("*.md") never matches
    # a leading dot, so a real card named `.foo.md` is silently absent from
    # the index, the context pack and any migration, with nothing anywhere
    # saying so. Surfacing it is the whole point: the file is not wrong, the
    # silence is.
    hidden = [p for p in (K / "cards").glob(".*.md")] if (K / "cards").is_dir() else []
    checks.append((
        "hidden .md in cards/", str(len(hidden)), "0",
        "OK" if not hidden else "NOTE",
    ))

    # --- domain prose freshness -------------------------------------------
    # A DURABLE signal, deliberately not a terminal message.
    #
    # The pre-commit hook re-authors stale domain cards, and when it cannot --
    # no `claude` on PATH, a timeout, more cards than the cap -- it prints a
    # handoff telling the developer to run `/velocity diagrams`. That works in
    # a terminal and nowhere else. A GUI client (Fork, VS Code, Kiro) runs the
    # hook with no controlling terminal AND commonly shows hook output only on
    # FAILURE, so a passing hook's handoff is never displayed. The cards then
    # rot with nobody told -- the exact failure this system exists to prevent.
    #
    # `status` is read on demand and reads frontmatter only, so this costs a
    # glob and no extractor. It is the signal that survives not being watched.
    arch_dir = K / "architecture"
    stale_domains, unauthored_domains = [], []
    for card in sorted(arch_dir.glob("DOMAIN-*.md")) if arch_dir.is_dir() else []:
        head = card.read_text(encoding="utf-8", errors="replace")[:2000]
        got = dict(re.findall(
            r"^(prose_signature|code_signature):\s*(\S+)\s*$", head, re.M))
        if not got.get("code_signature"):
            continue
        if not got.get("prose_signature"):
            unauthored_domains.append(card.stem)
        elif got["prose_signature"] != got["code_signature"]:
            stale_domains.append(card.stem)
    n_domains = len(list(arch_dir.glob("DOMAIN-*.md"))) if arch_dir.is_dir() else 0
    checks.append((
        "domain prose", f"{n_domains - len(stale_domains) - len(unauthored_domains)}",
        str(n_domains),
        "OK" if not (stale_domains or unauthored_domains) else "STALE",
    ))

    stale = [c for c in checks if c[3] == "STALE"]

    if as_json:
        trees = worktrees()
        print(json.dumps({
            "tree": str(ROOT),
            "branch": next((w.get("branch") for w in trees if w.get("current")), None),
            "head": head,
            "other_checkouts": [
                {k: w.get(k) for k in ("path", "branch", "head")}
                for w in trees if not w.get("current")
            ],
            "checks": [dict(zip(("area", "found", "expected", "verdict"), c)) for c in checks],
            "stale": len(stale),
        }, indent=2))
        return 1 if stale else 0

    trees = worktrees()
    here = next((w for w in trees if w.get("current")), None)
    print(f"tree:   {ROOT}")
    print(f"branch: {here.get('branch', '?') if here else '?'} @ {(head or '?')[:8]}"
          f"   last sync {state.get('last_sync_date', '?')} ({(sync_commit or '?')[:8]})")
    others = [w for w in trees if not w.get("current")]
    if others:
        print(f"\nNOTE: {len(others)} other checkout(s) of this repo exist. Numbers below "
              "describe THIS tree only:")
        for w in others:
            print(f"  - {w['path']}  [{w.get('branch', '?')} @ {w.get('head', '?')[:8]}]")
    print()
    print(f"{'':<24}{'found':>10}{'expected':>12}   verdict")
    for area, found, expected, verdict in checks:
        print(f"{area:<24}{found:>10}{expected:>12}   {verdict}")

    by_type = read_block(K / "state.yaml", "cards_by_type")
    print("\ncards by type: " + (
        ", ".join(f"{t}={n}" for t, n in sorted(by_type.items(), key=lambda kv: -as_int(kv[1])))
        if by_type else "(unknown)"
    ))

    if not stale:
        print("\nEverything current. Nothing to run.")
        return 0

    print(f"\n{len(stale)} stale: " + ", ".join(c[0] for c in stale))
    # Name the cards and give the command. A count alone tells a reader
    # something is wrong and not what to do about it.
    if stale_domains or unauthored_domains:
        named = stale_domains + unauthored_domains
        print("  domain cards needing a pass: " + " ".join(named))
        print("  Fix: /velocity diagrams " + " ".join(named))
    needs_arch = any(c[0] in ("source files covered", "source files changed") for c in stale)
    print("Fix: python3 tools/knowledge/rebuild_knowledge.py"
          + ("" if needs_arch else " --skip-architecture"))
    if any(c[0] == "ID scheme conformance" for c in stale):
        print("     python3 tools/knowledge/normalize_card_ids.py --check   (ID scheme drift)")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
