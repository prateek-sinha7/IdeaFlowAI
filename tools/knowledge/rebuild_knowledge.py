#!/usr/bin/env python3
"""Regenerate every derived artifact in .knowledge/, in dependency order.

One entry point, so "update the knowledge base" is a single command that
cannot be run half-way or in the wrong order. Each stage is an existing,
independently runnable script -- this only sequences them and fails fast.

    architecture  tools/knowledge/build_architecture.py   backend/ + frontend/src/ (live source)
                                                 -> architecture/MOD-*.md, modules.json
    index         tools/knowledge/build_index.py           cards/  -> INDEX.md, state.yaml
    context       tools/knowledge/build_context.py         cards/ + modules.json + MOD-*.md
                                                 -> CONTEXT.md
    validate      tools/knowledge/validate_links.py        every .knowledge/ link resolves

Order is load-bearing: build_context reads modules.json and the MOD-*.md
`## Purpose` sections that build_architecture writes, and build_index counts
the architecture cards. Running context before architecture bakes in stale
module data.

Nothing here writes cards. Card CONTENT is agent work (see
skills/velocity/book-keeping.md); these scripts only rebuild what is
mechanically derivable from cards + source, which is why re-running is
always safe and always idempotent.

    python3 tools/knowledge/rebuild_knowledge.py --check   # dry-run every stage
    python3 tools/knowledge/rebuild_knowledge.py           # full regeneration
    python3 tools/knowledge/rebuild_knowledge.py --skip-architecture

`--skip-architecture` exists because that stage shells out to pydeps and
dependency-cruiser over the whole codebase (~1-2 min); the other three are
fast and card-only. Skip it when only cards changed, never when source did.

This script does NOT run git. Committing the regenerated files is yours.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
TOOLS = ROOT / "tools" / "knowledge"

# (stage name, script, has a --check flag, is read-only)
# Read-only stages still run under --check -- they write nothing, and their
# report is the whole point of a dry run.
STAGES = [
    ("architecture", "build_architecture.py", True, False),
    ("index", "build_index.py", False, False),
    ("context", "build_context.py", False, False),
    ("validate", "validate_links.py", False, True),
]


def run_stage(script: str, supports_check: bool, readonly: bool, check: bool) -> bool:
    path = TOOLS / script
    if not path.is_file():
        print(f"  MISSING: {path.relative_to(ROOT)} -- cannot continue.")
        return False

    if check and not supports_check and not readonly:
        print("  skipped in --check (no dry-run mode; it would write)")
        return True

    cmd = [sys.executable, str(path)] + (["--check"] if check and supports_check else [])
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    out = (proc.stdout or "").rstrip()
    if out:
        for line in out.splitlines()[-12:]:
            print(f"  {line}")
    if proc.returncode != 0:
        err = (proc.stderr or "").rstrip()
        if err:
            for line in err.splitlines()[-12:]:
                print(f"  ! {line}")
        print(f"  FAILED (exit {proc.returncode})")
        return False
    return True


BAR = "─" * 66


def _open_tty():
    """A handle on the real terminal, or None.

    pre-commit CAPTURES a hook's stdout and stderr and replays them only after
    the hook exits -- `verbose: true` changes whether the capture is printed,
    not when. So a hook that streams perfectly still looks frozen: the child
    writes into a pipe nobody drains until it is over, and a developer watching
    a 40-second extractor run or a multi-minute model call sees a stuck
    terminal with no way to tell slow from hung.

    Writing to /dev/tty goes straight to the terminal, past the capture. It is
    the only way to show live progress from inside a pre-commit hook.

    None when there is no controlling terminal -- CI, a GUI client, a piped
    run. Callers fall back to stdout, which those environments do collect.
    """
    try:
        return open("/dev/tty", "w", buffering=1)
    except OSError:
        return None


_TTY = _open_tty()


def say(msg: str = "", bold: bool = False) -> None:
    """Print to the terminal live, AND to stdout for the captured log.

    Both, deliberately. The tty copy is what a human watching the commit sees
    as it happens; the stdout copy is what pre-commit replays afterwards and
    what CI keeps. Dropping either loses one of the two audiences.
    """
    line = f"\033[1m{msg}\033[0m" if bold and _TTY else msg
    if _TTY is not None:
        try:
            _TTY.write(line + "\n")
        except OSError:
            pass
    print(msg, flush=True)


def _run(argv: list[str], label: str, tail: int = 14, filt=None) -> int:
    """Run one step, STREAMING its output live under a heading.

    Streaming, not capturing. The two slow steps here are a ~40s extractor run
    and a headless model call measured in minutes; buffering their output until
    they finish means a developer watching a commit sees a frozen terminal for
    the entire time and cannot tell a slow run from a hung one. That is the
    difference between "verbose" and "silent, then a wall of text".

    `-u` forces the child unbuffered, without which Python's own block
    buffering re-introduces exactly the stall we are removing: the child would
    hold its prints in a 8KB buffer and flush them all at exit.

    An empty label prints no heading -- for steps whose caller wrote one.
    `filt` may rewrite or drop a line: return None to skip it.
    """
    if label:
        say("")
        say(label, bold=True)
    proc = subprocess.Popen(
        [sys.executable, "-u"] + argv, cwd=ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
    )
    assert proc.stdout is not None
    for raw in proc.stdout:
        line = raw.rstrip()
        if filt is not None:
            line = filt(line)
            if line is None:
                continue
        say(f"  {line}")
    return proc.wait()


def hook_mode() -> int:
    """Everything the commit hook does, in one place, logging as it goes.

    This replaced three separate pre-commit hooks. They had to run in a fixed
    order, shared a `git add`, and each printed its own disconnected block --
    so a developer watching a commit saw three unlabelled stanzas and no way to
    tell which one had actually done something. Worse, the ordering constraint
    lived in a YAML file where nothing enforced it, and getting it wrong failed
    intermittently: a commit that deleted a source file failed twice and passed
    on the third try as the two hooks converged.

    One hook, three phases, explicit headings, one exit code.

    Only phase 3 can fail the commit. Phase 1 is a regeneration and phase 2 is
    an optional documentation refresh -- neither is a reason to stop someone
    committing. A broken link IS.
    """
    arch = TOOLS / "build_architecture.py"
    say(BAR)
    say("knowledge base — keeping .knowledge/ in step with this commit")
    say(BAR)

    # ── 1. architecture ────────────────────────────────────────────────
    # Two-step: the cheap glob decides whether the ~40s extractor run is
    # warranted. Exit 0 from --needs-rebuild means no file was added or
    # removed, so there is nothing for the scan to find.
    say("")
    say("[1/3] architecture", bold=True)
    probe = _run([str(arch), "--needs-rebuild"], "")
    if probe != 0:
        rc = _run([str(arch)], "      rebuilding (pydeps + dependency-cruiser, ~40s)")
        if rc != 0:
            say("  ! architecture rebuild failed — continuing; "
                  "the commit is not blocked by this phase")
        else:
            _git_add(".knowledge/architecture", ".knowledge/ARCHITECTURE.md")
    else:
        say("  nothing added or removed — skipped the 40s scan")

    # ── 2. domains ─────────────────────────────────────────────────────
    # Say what is being considered before saying what happened. "affects no
    # domain card" on its own is ambiguous -- it reads the same whether there
    # are fourteen domains or none, and a config mistake that finds zero cards
    # would look exactly like a quiet commit.
    say("")
    say("[2/3] domain cards", bold=True)
    n_cards = len(list((ROOT / ".knowledge" / "architecture").glob("DOMAIN-*.md")))
    staged = subprocess.run(["git", "diff", "--name-only", "--cached"],
                            cwd=ROOT, capture_output=True, text=True).stdout.split()
    src = [f for f in staged if not f.startswith(".knowledge/")]
    say(f"  {n_cards} domain card(s) known; "
          f"{len(src)} source file(s) staged of {len(staged)} total")
    rc = _run([str(arch), "--refresh-affected"], "", tail=20)
    if rc != 0:
        say("  ! domain refresh reported a problem — continuing; "
              "documentation never blocks a commit")
    _git_add(".knowledge/architecture", ".knowledge/ARCHITECTURE.md")

    # ── 3. derived artifacts ───────────────────────────────────────────
    # The only phase that can fail the commit. INDEX.md, CONTEXT.md and the
    # `## Related` blocks are pure derivatives with exactly one correct value,
    # and a broken link means a card nobody will find.
    say("")
    say("[3/3] index, context, links", bold=True)
    # Flatten the inner run's own stage numbering as it streams. It prints its
    # own "[1/3] index" headings, which nested inside this phase's "[3/3]" gave
    # two competing counters and read as a bug.
    noise = ("Rebuilding .knowledge/", "All stages completed", "--check complete",
             "Regenerated files")
    def _flatten(line: str):
        s = line.strip()
        if not s or s.startswith(noise):
            return None
        m = re.match(r"^\[\d+/\d+\]\s", s)
        return s.split("]", 1)[1].strip() if m else s

    rc = _run([str(Path(__file__).resolve()), "--skip-architecture"], "",
              filt=_flatten)
    if rc != 0:
        say(BAR)
        say("COMMIT BLOCKED: a derived artifact could not be rebuilt.")
        say("Read the output above — a broken link or unparseable frontmatter")
        say("is a real failure, not churn. Re-running will not fix it.")
        say(BAR)
        return 1
    _git_add(".knowledge/INDEX.md", ".knowledge/state.yaml",
             ".knowledge/CONTEXT.md", ".knowledge/cards")

    say(BAR)
    say("knowledge base up to date; regenerated files staged into this commit")
    say(BAR)
    return 0


def _git_add(*paths: str) -> None:
    """Stage regenerated artifacts so they land in the same commit."""
    live = [p for p in paths if (ROOT / p).exists()]
    if live:
        subprocess.run(["git", "add", *live], cwd=ROOT, capture_output=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="dry-run where supported")
    ap.add_argument("--skip-architecture", action="store_true",
                    help="skip the slow source-scanning stage (cards-only changes)")
    ap.add_argument("--hook", action="store_true",
                    help="everything the pre-commit hook does, in three logged "
                         "phases: architecture, domain refresh, derived "
                         "artifacts. Only the last can fail the commit.")
    args = ap.parse_args()

    if args.hook:
        return hook_mode()

    stages = [s for s in STAGES if not (args.skip_architecture and s[0] == "architecture")]

    # `validate` inspects ALL of .knowledge/, including the architecture cards
    # it does not itself produce. That makes stage ORDER load-bearing in a way
    # the list above does not announce: run validate before architecture and it
    # reports cards pointing at a source file the architecture stage was about
    # to remove. It happened -- a pre-commit config with the two hooks in the
    # wrong order failed twice and passed on the third attempt as they
    # converged. Assert the invariant here so a reordering fails loudly at the
    # one place that owns the pipeline, instead of intermittently at a commit.
    names = [s[0] for s in stages]
    if "validate" in names and "architecture" in names:
        if names.index("validate") < names.index("architecture"):
            print("ERROR: 'validate' is ordered before 'architecture'. It checks "
                  "links INTO architecture cards, so it must run after they are "
                  "regenerated. Fix STAGES.")
            return 1
    if "validate" in names and names[-1] != "validate":
        print(f"ERROR: 'validate' must run last; STAGES ends with {names[-1]!r}.")
        return 1

    print(f"Rebuilding .knowledge/ ({len(stages)} stages)"
          + (" [--check: no writes]" if args.check else ""))
    for i, (name, script, supports_check, readonly) in enumerate(stages, 1):
        print(f"\n[{i}/{len(stages)}] {name}  ({script})")
        if not run_stage(script, supports_check, readonly, args.check):
            print(f"\nAborted at stage {name!r}. Nothing further was run.")
            return 1

    print("\nAll stages completed." if not args.check else "\n--check complete.")
    print("Regenerated files are uncommitted -- review and commit them yourself.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
