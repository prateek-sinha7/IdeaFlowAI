// ─────────────────────────────────────────────────────────────────────────────
// Workstream C2 (POR §5 D4 / §11) — clarify-artifact transform lib. Pure,
// side-effect-free, no DOM. Consumed by the reopen mount (WorkflowHistory →
// getRunArtifacts(kind="clarifications")) and by the Files "Run input" section
// (clarifications.md download).
//
// The persisted kind="clarifications" artifact content is a JSON list of
//   { question_id, question_text, impact_level, answer, round }
// items (a node may carry one round or several). Artifacts have NO created_at
// (api.ts:358), so ordering is BY the content `round` field (POR §11).
// ─────────────────────────────────────────────────────────────────────────────

import type { ClarifyRound } from "@/types/index";

/** One raw clarify Q&A item as persisted in the artifact content JSON list. */
interface RawClarifyItem {
  question_id?: string;
  question_text?: string;
  impact_level?: string;
  answer?: string | null;
  round?: number;
}

/**
 * Decompose the kind="clarifications" artifact nodes into ordered ClarifyRound[].
 * JSON.parse each node's `content` (a list of raw Q&A items), flatten across
 * nodes, group by `round`, and sort rounds ascending. Malformed / empty /
 * non-JSON content is skipped — this NEVER throws and returns `[]` when there is
 * nothing valid to surface.
 */
export function parseClarificationArtifacts(nodes: { content?: string }[]): ClarifyRound[] {
  if (!Array.isArray(nodes) || nodes.length === 0) return [];

  const byRound = new Map<number, ClarifyRound["qa"]>();

  for (const node of nodes) {
    if (!node || typeof node.content !== "string" || node.content.trim() === "") continue;
    let parsed: unknown;
    try {
      parsed = JSON.parse(node.content);
    } catch {
      continue; // malformed / non-JSON → skip, never throw
    }
    if (!Array.isArray(parsed)) continue;

    for (const raw of parsed as RawClarifyItem[]) {
      if (!raw || typeof raw !== "object") continue;
      const round = typeof raw.round === "number" ? raw.round : 0;
      const qa = byRound.get(round) ?? [];
      qa.push({
        question_id: raw.question_id ?? "",
        question_text: raw.question_text ?? "",
        impact_level: raw.impact_level ?? "",
        answer: raw.answer ?? null,
      });
      byRound.set(round, qa);
    }
  }

  return [...byRound.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([round, qa]) => ({ round, qa }));
}

/**
 * Render answered clarify rounds to plain, human-readable markdown for the
 * clarifications.md download (Files "Run input" section). Text-only — never
 * HTML (T-08q-01: the download is a plain markdown Blob, never executed).
 */
export function renderClarificationsMarkdown(rounds: ClarifyRound[]): string {
  if (!Array.isArray(rounds) || rounds.length === 0) return "";

  const lines: string[] = ["# Clarifications", ""];

  for (const { round, qa } of rounds) {
    lines.push(`## Round ${round}`, "");
    for (const item of qa) {
      const impact = item.impact_level ? ` _(${item.impact_level} impact)_` : "";
      lines.push(`### ${item.question_text || item.question_id}${impact}`);
      lines.push(`**Answer:** ${item.answer ?? "(no answer)"}`, "");
    }
  }

  return lines.join("\n").trimEnd() + "\n";
}
