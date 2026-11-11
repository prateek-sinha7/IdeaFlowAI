import fc from "fast-check";
import { describe, expect, it } from "vitest";

import type { RevisionKind } from "@/types/workflowBuilder";

import { undoTargetMessageId } from "./builderSelectors";

// Fixed seed keeps failures reproducible; 100 runs per property, as the spec requires.
const PROPERTY_OPTIONS = { seed: 20240611, numRuns: 100 } as const;

interface RevisionEntry {
  revision: number;
  kind: RevisionKind;
}

interface MessageEntry {
  id: string;
  seq: number;
  role: "user" | "assistant";
  revision: number | null;
}

const revisionKind = fc.constantFrom<RevisionKind>("seed", "accepted", "undo", "unproposed");

// Revision numbers are unique per session, but the list may arrive in any order.
const revisionList: fc.Arbitrary<RevisionEntry[]> = fc.uniqueArray(
  fc.record({ revision: fc.integer({ min: 0, max: 15 }), kind: revisionKind }),
  { selector: (entry) => entry.revision, maxLength: 8 },
);

// Message seq is unique per session. A message's revision may point at any number,
// including non-accepted revisions and numbers absent from the list, so the rule must filter.
const transcriptList: fc.Arbitrary<MessageEntry[]> = fc
  .uniqueArray(
    fc.record({
      seq: fc.integer({ min: 1, max: 40 }),
      role: fc.constantFrom<"user" | "assistant">("user", "assistant"),
      revision: fc.option(fc.integer({ min: 0, max: 17 }), { nil: null }),
    }),
    { selector: (entry) => entry.seq, maxLength: 12 },
  )
  .map((entries) => entries.map((entry, index) => ({ id: `m${index}`, ...entry })));

/**
 * Independent reading of Property 35. Offer Undo only when the latest revision is
 * accepted, and then on the assistant message with the highest seq among those whose
 * revision is that accepted revision. Sorting here instead of the selector's loop keeps
 * the oracle from copying the implementation.
 */
function expectedUndoTarget(transcript: MessageEntry[], revisions: RevisionEntry[]): string | null {
  const newestFirst = [...revisions].sort((a, b) => b.revision - a.revision);
  const latest = newestFirst[0];
  if (latest === undefined || latest.kind !== "accepted") {
    return null;
  }
  const candidates = transcript
    .filter((message) => message.role === "assistant" && message.revision === latest.revision)
    .sort((a, b) => b.seq - a.seq);
  return candidates[0]?.id ?? null;
}

describe("undoTargetMessageId properties", () => {
  // Feature: ai-workflow-builder, Property 35: Undo is offered on the right message only
  // **Validates: Requirements 8.3**
  it("offers Undo on at most one message, exactly the latest assistant message of the latest accepted revision", () => {
    fc.assert(
      fc.property(transcriptList, revisionList, (transcript, revisions) => {
        const target = undoTargetMessageId(transcript, revisions);

        expect(target).toBe(expectedUndoTarget(transcript, revisions));

        if (target !== null) {
          const offered = transcript.filter((message) => message.id === target);
          expect(offered).toHaveLength(1);
          expect(offered[0]?.role).toBe("assistant");
        }
      }),
      PROPERTY_OPTIONS,
    );
  });
});
