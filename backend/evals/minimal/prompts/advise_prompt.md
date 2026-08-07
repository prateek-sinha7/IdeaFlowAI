Propose edits to an AI agent's system prompt, from what a judge found in that agent's real output. Make the SMALLEST set of edits that fixes the weaknesses without breaking the strengths. Do not rewrite wholesale.

=== CURRENT SYSTEM PROMPT ===
{system_prompt}
=== END ===

=== WEAKNESSES (most-cited first — fix these) ===
{weaknesses}
=== END ===

=== STRENGTHS (do NOT break these) ===
{strengths}
=== END ===

=== CATEGORIES (use one of these ids verbatim) ===
{categories}
=== END ===

Return ONE list, `advice`. Every entry carries all five fields — never split them across separate lists:

- `action` — `add` for a new instruction, `remove` for wording ALREADY IN the prompt above that causes a weakness. For `remove`, quote the existing wording. Do not invent removals.
- `description` — the instruction itself, one self-contained sentence, pasteable as-is. No preamble, no "you should consider".
- `advisory_score` — 0-100. 0 = optional (MAY), 100 = mandatory (MUST). Price it by what the weakness actually costs, not by how confident you feel. A cosmetic nit is not a 100.
- `category` — one of the ids listed above, verbatim. This groups the suggestion with the same problem seen in other runs, so an invented category hides the pattern.
- `reason` — one line naming the observed weakness this addresses. Cite the evidence, not the intent.

Every entry must trace to a weakness above. Do not propose edits for problems that were not observed.
