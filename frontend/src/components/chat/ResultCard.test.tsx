import { readFileSync } from "node:fs";
import { join } from "node:path";

import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { ChatMessage } from "@/types/index";
import { ResultCard } from "./ResultCard";

// ─── ResultCard — narrator result cards (5 kinds) + nonce'd deep-link ─────────
// Renders a chat_reply narrator turn BY its generic cardKind (SC-001) and fires
// onRequestOpenTab (the plan-03 seam) into a generic run tab. LOCK-F: the
// deliverable card says "Deliverable". The spec_revision header is the static
// "Revising spec"; its cycle number lives in the narrator text only (ISS-083).

function narrator(
  cardKind: NonNullable<ChatMessage["cardKind"]>,
  overrides: Partial<ChatMessage> = {},
): ChatMessage {
  return {
    id: `m-${cardKind}`,
    chatSessionId: "s1",
    role: "assistant",
    content: `Narrator text for ${cardKind}.`,
    createdAt: new Date().toISOString(),
    cardKind,
    ...overrides,
  };
}

describe("ResultCard", () => {
  it.each([
    ["clarify", "thinking"],
    ["gate", "thinking"],
    ["pipeline", "thinking"],
    ["deliverable", "preview"],
    ["spec_revision", "thinking"],
  ] as const)(
    "renders the %s card with its testid + card-kind and default tab %s",
    (kind, expectedTab) => {
      const onRequestOpenTab = vi.fn();
      render(
        <ResultCard message={narrator(kind)} onRequestOpenTab={onRequestOpenTab} />,
      );
      const card = screen.getByTestId("chat-result-card");
      expect(card).toHaveAttribute("data-card-kind", kind);
      fireEvent.click(screen.getByTestId("chat-result-card-link"));
      expect(onRequestOpenTab).toHaveBeenCalledTimes(1);
      expect(onRequestOpenTab).toHaveBeenCalledWith(expectedTab);
    },
  );

  it("labels the deliverable output 'Deliverable' (LOCK-F) and links to Preview", () => {
    render(
      <ResultCard message={narrator("deliverable")} onRequestOpenTab={vi.fn()} />,
    );
    expect(screen.getByText("Deliverable")).toBeInTheDocument();
    expect(screen.getByText("Open in Preview")).toBeInTheDocument();
  });

  it("renders the revision cycle exactly once, from the narrator text (ISS-083)", () => {
    render(
      <ResultCard
        message={narrator("spec_revision", { content: "Revising spec — cycle 2" })}
        onRequestOpenTab={vi.fn()}
      />,
    );
    const hits = screen.getAllByText(/Revising spec — cycle \d+/);
    expect(hits).toHaveLength(1);
    expect(hits[0]).toHaveTextContent("Revising spec — cycle 2");
  });

  it("locks the spec_revision header to the static CARD_SPECS title (ISS-083)", () => {
    render(
      <ResultCard
        message={narrator("spec_revision", { content: "Revising spec — cycle 2" })}
        onRequestOpenTab={vi.fn()}
      />,
    );
    expect(screen.getByText("Revising spec")).toBeInTheDocument();
  });

  it("honours the stored deepLink tab over the kind default", () => {
    const onRequestOpenTab = vi.fn();
    render(
      <ResultCard
        message={narrator("gate", { deepLink: { tab: "audit", nonce: 7 } })}
        onRequestOpenTab={onRequestOpenTab}
      />,
    );
    fireEvent.click(screen.getByTestId("chat-result-card-link"));
    expect(onRequestOpenTab).toHaveBeenCalledWith("audit");
  });

  // FIX-128 regression: the backend's `deep_link.target` ("run:<id>",
  // "deliverable:<file>", …) is a milestone REFERENCE, not a panel tab id, and must
  // never reach the tab seam — PreviewPanel drops unknown tab ids, which is what
  // broke "Open in Steps" / "Open in Preview". ISS-614 removed the `anchor` field
  // that used to carry it, so a narrator frame with only a `target` now parses to a
  // descriptor with NO tab at all (useRunChat.parseDeepLink) — which is what these
  // fixtures represent. The guarantee under test is unchanged: a descriptor that
  // names no tab falls back to the card kind's generic default, never to something
  // derived from the milestone reference.
  it("falls back to the kind's default tab when the descriptor names none (FIX-128)", () => {
    const onSteps = vi.fn();
    const { unmount } = render(
      <ResultCard
        message={narrator("pipeline", {
          deepLink: { nonce: 0 },
        })}
        onRequestOpenTab={onSteps}
      />,
    );
    expect(screen.getByTestId("chat-result-card-link")).toHaveAttribute(
      "data-target-tab",
      "thinking",
    );
    fireEvent.click(screen.getByTestId("chat-result-card-link"));
    expect(onSteps).toHaveBeenCalledWith("thinking");
    unmount();

    const onPreview = vi.fn();
    render(
      <ResultCard
        message={narrator("deliverable", {
          deepLink: { nonce: 0 },
        })}
        onRequestOpenTab={onPreview}
      />,
    );
    fireEvent.click(screen.getByTestId("chat-result-card-link"));
    expect(onPreview).toHaveBeenCalledWith("preview");
  });

  it("degrades an unknown/absent kind to an inert generic card (T-31-04-T2)", () => {
    const onRequestOpenTab = vi.fn();
    const msg: ChatMessage = {
      id: "m-x",
      chatSessionId: "s1",
      role: "assistant",
      content: "no kind here",
      createdAt: new Date().toISOString(),
    };
    render(<ResultCard message={msg} onRequestOpenTab={onRequestOpenTab} />);
    const card = screen.getByTestId("chat-result-card");
    expect(card).toHaveAttribute("data-card-kind", "unknown");
    // Still safe to interact — falls back to the Steps tab, no crash.
    fireEvent.click(screen.getByTestId("chat-result-card-link"));
    expect(onRequestOpenTab).toHaveBeenCalledWith("thinking");
  });

  it("SC-001: the source carries no workflow-name literal", () => {
    const src = readFileSync(
      join(process.cwd(), "src/components/chat/ResultCard.tsx"),
      "utf8",
    );
    expect(
      /"prototype"|od_ppt|app_builder|user_stories|ppt_revision/.test(src),
    ).toBe(false);
  });

  // ISS-650 / QA-PS-004: a resolved gate card must name the agent whose gate
  // was approved so a multi-gate run's approvals are distinguishable in the
  // chat transcript, instead of all reading the identical literal.
  it(
    "ISS-650: names the agent in a resolved gate approval message",
    () => {
      render(
        <ResultCard
          message={
            {
              ...narrator("gate", { resolved: true }),
              agentName: "Domain Discovery Agent",
            } as ChatMessage
          }
          onRequestOpenTab={vi.fn()}
        />,
      );
      expect(
        screen.getByText(
          "Domain Discovery Agent review approved — build continues",
        ),
      ).toBeInTheDocument();
    },
  );

  // ISS-653 / QA-PS-006: an UNRESOLVED gate card must also name the agent
  // awaiting review, so a multi-gate run's pending prompts are distinguishable
  // in the chat transcript instead of every one reading the identical
  // "Review required" literal (the unresolved sibling of ISS-650, which fixed
  // the resolved branch of the same ternary).
  it.each([false, undefined])(
    "ISS-653: names the agent in an unresolved gate review-required message (resolved=%s)",
    (resolved) => {
      render(
        <ResultCard
          message={
            {
              ...narrator("gate", { resolved }),
              agentName: "Plan Agent",
            } as ChatMessage
          }
          onRequestOpenTab={vi.fn()}
        />,
      );
      expect(screen.getByText("Plan Agent review required")).toBeInTheDocument();
    },
  );

  it("holds no dormant `cycle` prop (ISS-083)", () => {
    const src = readFileSync(
      join(process.cwd(), "src/components/chat/ResultCard.tsx"),
      "utf8",
    );
    expect(src).not.toMatch(/cycle\?:\s*number/);
    expect(src).not.toMatch(/cycle\s*\?\?/);
  });
});
