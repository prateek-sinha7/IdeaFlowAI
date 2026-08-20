# velocity: analyze

Find the root cause of a bug or symptom using the knowledge base as the
primary lead source, then the actual source code as the final proof.
Optionally files a Jira ticket. Always ends by invoking `book-keeping`.

Preconditions: a symptom description or bug report from the user.

Leaves behind: a root-cause report to the user; a new card recorded via
`book-keeping`; optionally a Jira issue (only with explicit approval).

## Procedure

1. Invoke `prime` (this skill family's `prime.md`). Skip this call only if
   `CONTEXT.md` was already confirmed fresh earlier in this same session.

2. **Read `.knowledge/INDEX.md` — and nothing else yet.** It is one file
   with one line per card:
   `- [ID](cards/<file>.md) — <compact_summary>`. Every summary states that
   card's root cause, resolution, or mechanism, so the index alone usually
   tells you which cards matter.

   Match the symptom against those lines **semantically, not by exact
   keyword** — a user describes a symptom in their own words, rarely the
   card's. Shortlist the plausible IDs; cast a wide net here, it is cheap.

   **NEVER read or grep `.knowledge/cards/*.md` in bulk.** 469 files will
   blow out the context window and bury the answer. The index exists
   precisely so you never have to. Same for `.knowledge/architecture/*.md` —
   never sweep the directory.

3. Open ONLY the shortlisted cards, by following their index links —
   typically 2-5 files. If the shortlist came back empty, re-read the index
   under a broader reading of the symptom before widening anything else.

4. Follow leads from any matching card:
   - Follow the markdown links to other cards in its body prose.
   - Follow the links in its `## Related` block (body, under the
     frontmatter): `**Depends on:**` and `**Referenced by:**`.
   - Repeat until leads stop producing new relevant cards (typically 1-2
     hops is enough — don't traverse the whole graph).

5. From the cards found, collect candidate modules via each card's
   `applies_to.modules` and `applies_to.globs`. Read the corresponding
   `.knowledge/architecture/MOD-*.md` cards in full (Purpose, Shape, Why
   this shape) to understand intended behavior before reading code.

   **`applies_to.modules` is not always a `MOD-*` id.** Older cards carry
   free-text values (`agents`, `app`, `AGENT`, a bare function name) that
   resolve to no architecture card — `ls .knowledge/architecture/MOD-agents.md`
   simply fails. Do not treat that as a dead end:
   - Try `applies_to.globs` first — but verify each path exists before
     trusting it. Older globs are often recorded relative to a subtree
     (`tests/agents/x.py` when the file is `backend/tests/agents/x.py`). If a
     glob does not resolve, retry it as a suffix:
     `git ls-files | grep -F "<glob>"`.
   - Or map the free-text value against the `path` field in
     `modules.json`. **This can match more than one module** — `agents`
     matches both `MOD-backend-agents` and `MOD-backend-app-agents`. When it
     does, read ALL the matches rather than guessing; they are usually
     adjacent layers of the same story, and the card's own `file:line`
     evidence tells you which one actually contains the code.
   - If nothing resolves, say so in your report and proceed from the card's
     own `file:line` evidence. A stale `applies_to` is a corpus-data gap, not
     a reason to abandon the investigation — and never silently substitute a
     module you merely think is right.

6. Read the actual source files in those modules. Do not stop at the
   architecture card's description — the code is the ground truth. Trace
   the symptom to a specific mechanism.

7. State the ROOT CAUSE with file:line evidence. Structure the report so
   it clearly separates:
   - CONFIRMED — backed by a specific file:line you read and quoted/cited.
   - INFERRED — a reasonable hypothesis not directly proven by what you
     read (state what would confirm or refute it).
   Do not present an inference as a confirmed fact.

8. Report the root cause to the user.

9. Ask whether to file a Jira ticket for this. If the user declines, skip
   to step 11.

10. If yes: draft the ticket (summary line; description containing the root
   cause statement, the file:line evidence, and the list of affected
   files) and SHOW the full draft to the user. Wait for explicit approval
   before creating anything. Only after approval, create it via
   `mcp__jira__jira_create_issue`. It needs a project key and an issue
   type — if you do not already know them, call
   `mcp__jira__jira_get_all_projects` and ask the user which project rather
   than guessing. Report back the created issue key and URL.

11. Invoke `book-keeping` to record this analysis (root cause, evidence,
    affected files/modules, and the Jira key if one was created) as a
    card.
