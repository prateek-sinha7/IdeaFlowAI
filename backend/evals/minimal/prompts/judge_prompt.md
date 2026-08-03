Grade this agent response for an automated eval. Return one entry per rubric dimension, each scored 0-100 with evidence quoted from the response. No single overall number.

=== AGENT SYSTEM PROMPT ===
{system_prompt}
=== END ===

=== BRIEF ===
{prompt}
=== END ===

=== RESPONSE ===
{response}
=== END ===

=== RUBRIC ===
{rubric_text}
=== END ===

=== DIMENSIONS (use each id verbatim) ===
{dimensions}
=== END ===
{anchors}
Return exactly one entry per dimension — no more, no fewer. Also return top-level `rationale`, `strengths`, `weaknesses`.
