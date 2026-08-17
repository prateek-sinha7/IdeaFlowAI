---
name: code-review
description: Review pull requests, merge requests, branches, or code diffs for security issues, correctness, error handling, test coverage, and style. Use when the user asks to review a PR, MR, branch, or diff, including phrasings like "review pr for X to Y", "review mr from X to Y", "review branch X into Y", "review X against Y", "compare X and Y and review", "check the diff between X and Y", "code review for X to Y", or when a pasted diff/code block is provided for review, or when preparing code for a merge/pull request.
---

# Code Review Skill

Review the provided diff, pull request, or merge request systematically. Do
not just skim for style issues — walk through each concern below in order.

## 0. Reviewing by branch name (local git)

If the request names a source and target branch, get the diff via git
instead of asking the user to paste one. Recognize phrasings such as:

- "review pr for X to Y" / "review pr for X into Y"
- "review mr from X to Y" / "review mr from X into Y"
- "review branch X into Y" / "review branch X against Y"
- "review X against Y" / "compare X and Y and review"
- "check the diff between X and Y"
- "code review for X to Y"

Where X is the source branch and Y is the target branch (the "into"/"to"
side is always the target).

1. Parse the source branch and target branch from the prompt. If only one
   branch name is given, treat it as the source and default the target to
   `dev`.
2. Run the collection script from the workspace root. Pick the script that
   matches the operating system:

   - Windows (PowerShell):
     ```
     powershell -File .kiro/skills/code-review/scripts/collect_diff.ps1 -Source "<source-branch>" -Target "<target-branch>"
     ```
   - Linux / macOS (bash):
     ```
     bash .kiro/skills/code-review/scripts/collect_diff.sh --source "<source-branch>" --target "<target-branch>"
     ```

   Both scripts take the same inputs and print the same JSON shape, so the
   rest of the steps below are identical regardless of which one runs.
3. The script is read-only (fetch + diff/log only — no checkout, merge, or
   push). It prints a JSON result with `diffFile`, `commitCount`,
   `filesChanged`, and `fileList`. If `success` is `false`, report the
   `error` to the user and stop (do not guess branch names or retry blindly).
4. Read the file at `diffFile` for the full diff, stat summary, and commit
   log, then proceed with the checklist below (sections 1-6 and the
   Flowin-specific checks) against that diff content.
5. Use `commitCount` and `filesChanged` from the JSON result for the report
   header — don't recompute them by hand.

If the user pastes a diff directly instead, skip straight to the checklist
below using the pasted content.

## 1. Correctness
- Does the change do what the PR description / commit message claims?
- Are edge cases handled (empty input, null/undefined, zero, negative numbers,
  large inputs, concurrent access)?
- Any off-by-one errors, incorrect operators, or inverted conditionals?

## 2. Security
- No hardcoded secrets, API keys, passwords, or tokens.
- All external input (request bodies, query params, headers, file uploads) is
  validated and sanitized.
- Database access uses parameterized queries — never string-concatenated SQL.
- New endpoints enforce authentication and authorization (not just login, but
  ownership/role checks on the specific resource).
- Error responses returned to users are generic; no stack traces, SQL errors,
  or internal paths leaked.
- No sensitive data (passwords, tokens, PII) written to logs.

## 3. Error handling
- Errors are caught at the right layer, not swallowed silently.
- Failure paths leave the system in a consistent state (no partial writes,
  no leaked resources/connections).
- User-facing errors are clear without exposing internals.

## 4. Tests
- New logic has test coverage for the happy path and at least one failure/edge
  case.
- Existing tests still make sense given the change (no tests weakened just to
  make them pass).
- No tests were deleted/skipped without a documented reason.

## 5. Readability & maintainability
- Naming is clear and consistent with the rest of the codebase.
- No dead code, commented-out blocks, or leftover debug statements
  (console.log, print, etc.).
- Functions/methods are reasonably scoped — flag anything doing too much.
- Duplication that could reasonably be shared is called out (but don't demand
  premature abstraction for a one-off).

## 6. Dependencies & config
- New dependencies are pinned to exact/known-good versions, not open ranges.
- No unfamiliar or suspicious package names (possible typosquatting).
- No debug flags, verbose logging, or permissive CORS left enabled for
  production paths.

## Flowin-specific checks

### PRIMARY GATE — `.planning/IMPLEMENTATION-REGISTER.md` (read this first, every review)

This register is the single stitched knowledge layer over the entire
`.planning/` history. It is the most important check in this skill — a change
that passes generic code review but violates the register is still a
**Blocking** finding. Before judging any diff on this project, open
`.planning/IMPLEMENTATION-REGISTER.md` and use it actively:

1. **Read the Overview first** (§2 SC-001, §4 Architecture & Hard Constraints,
   the locked-decisions and leak-map sections). These bind every phase.
2. **Locate the phase(s) the diff touches** via the Phase Navigation table,
   then read that phase's parts §4 (what was deleted/superseded) and §5
   (locked decisions & constraints).
3. Check the diff against the register on these axes and report each explicitly
   in the report's register-check subsection (state which phase(s) you
   consulted):
   - **Duplicating an existing capability** — the register indexes ~70
     registered capabilities/modules. If the diff re-implements logic that
     already exists as a registered capability, flag it (Blocking) and point
     to the phase/section where it already lives. Adding behavior should mean
     "add a module + `@register`", not re-writing kernel logic.
   - **Resurrecting deleted code** — each phase §4 lists code that was
     deliberately deleted/superseded (e.g. the Phase-3 echo stub, leaks
     L1–L16 / F1–F5, the orphaned `WorkflowComposer.tsx`/`CapabilityPalette.tsx`).
     If the diff brings any of it back, that is Blocking — name the item and
     the phase that removed it.
   - **Contradicting a locked decision** — Overview §4 + each phase §5 record
     locked decisions (e.g. SC-001, INV-1, thin no-DSL compiler INV-5,
     security-defaults-OFF, additive-migrations-only, deepagents-only INV-13).
     Flag any diff that reverses one.
   - **INV-3 goldens** — the 5 characterization goldens must stay
     byte/event-identical unless the change is *intentionally* output-changing.
     If the diff would alter deterministic deliverables without saying so,
     flag it and call out that goldens would need regenerating with
     justification.

If you cannot access or parse the register, say so in the report rather than
silently skipping this gate.

### Secondary registers & invariants

- `.planning/FIX-REGISTER.md` — flag if this duplicates or contradicts a
  previously logged fix for the same area; reuse the established root-cause
  pattern where one exists.
- `.planning/ISSUES-REGISTER.md` — confirm the change isn't re-opening a
  WONTFIX/DEFERRED item or duplicating an already-FIXED one.
- Architecture invariants to check for violations (these mirror register §4):
  - INV-1: no `if pipeline_type == ...` / `spec.id == ...` branching in the
    engine kernel — behavior must live in registered capabilities.
  - INV-12: no dual implementations left behind after a move/refactor.
  - INV-13: `create_deep_agent` is only called inside `deep_agent_runner.py`.
  - Security gates (`exec` / `network` / `secrets` / `spawn_subagents`) must
    stay off unless explicitly enabled by a gate.
  - New tables/migrations are additive Alembic migrations with `owner_id` +
    `workspace_id`.

## Output format

Start the report with a header (only include branch/commit info when the
diff came from the branch-comparison flow in section 0):

```
## PR Review: <source> -> <target>
Commits: <commitCount>  |  Files changed: <filesChanged>  |  +<added>/-<removed> lines
```

Then summarize findings grouped by severity:

- **Blocking** — must fix before merge (security holes, broken logic, missing
  auth checks, data loss risks, invariant violations)
- **Should fix** — real issues but not merge-blocking (missing edge case test,
  unclear naming, minor duplication)
- **Nit** — optional style/preference comments, clearly labeled as such

For each finding, reference the file and line, explain the risk in one or two
sentences, and suggest a concrete fix. If the diff has no issues in a
category, say so briefly rather than omitting it silently.

Close with a **Flowin invariant/register check** subsection. Lead it with the
`IMPLEMENTATION-REGISTER.md` result — name the phase(s) you consulted and give
a pass/fail on each axis (duplicate capability / resurrected deleted code /
contradicts locked decision / INV-3 goldens), then the secondary registers and
invariants. Any register violation is a **Blocking** finding and forces a
**Request changes** verdict regardless of how clean the rest of the diff is.

End with an overall **verdict**: Approve / Approve with comments / Request
changes. This is advisory only — never merge, push, or modify branches as part
of a review.
