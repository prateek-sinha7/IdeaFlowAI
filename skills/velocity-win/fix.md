# velocity: fix

Analyze, propose, and (on approval) apply a fix. Root cause first, blast
radius second, approval third, application last. Never claims success
without evidence.

Preconditions: a symptom or bug report from the user (same as `analyze`).

Leaves behind: applied code changes (only if approved); a verification
command handed to the user; a new/updated card recorded via `book-keeping`.

## Procedure

1. Run `analyze` (this skill family's `analyze.md`) in full to establish
   the root cause. Do not skip this even if the cause seems obvious — the
   blast-radius step below depends on knowing exactly which module and
   files are implicated.

2. Read the relevant `.knowledge/architecture/MOD-*.md` card(s) for the
   module(s) touched by the fix. Confirm:
   - Where the fix belongs, per the module's stated `## Shape`.
   - Any `locked_constraints` on cards whose `applies_to.modules` /
     `applies_to.globs` cover the target file(s) — these are invariants
     the fix must not violate.

3. Compute BLAST RADIUS before writing any change:
   - Which files will change.
   - Which other modules import those files — walk `imports` /
     `imported_by` edges in `.knowledge/architecture/modules.json`
     outward from the changed module.
   - Which cards' `applies_to.globs` cover the changed files (these cards
     may need a `book-keeping` update after the fix lands).
   - Which `locked_constraints` are in play and how the fix respects each
     one.

4. List plausible side effects of the fix and, for each, how it would
   surface if it broke something (a specific error, a specific behavior
   change, a specific test that would fail). Be concrete — "might break
   something downstream" is not an acceptable entry.

5. Present to the user, together: the proposed fix (the actual diff or
   the exact change to make), the blast radius from step 3, and the side
   effects from step 4. ASK for approval. Do not proceed without it.

6. Only on approval, apply the fix.

7. State the verification command(s) the user should run to confirm the
   fix (e.g. the specific test file or `pytest` target, a build command).
   Do NOT claim tests pass, the bug is fixed, or verification succeeded —
   you have not run them. Ask the user to run the command and report
   back.

8. Invoke `book-keeping` to record the fix (what changed, why, evidence,
   affected files/modules) as a card, and to flag any architecture cards
   from step 3 that now need an update because the fix changed the
   module's shape.

## Hard rule

NEVER run `git commit`, `git add`, `git push`, or any branch operation. The
user handles all git operations themselves.
