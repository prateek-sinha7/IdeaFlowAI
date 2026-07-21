import { readFileSync } from "node:fs";
import { join } from "node:path";

import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { ChatMessage } from "@/types/index";
import { ResultCard } from "./ResultCard";

// ─── ResultCard — narrator result cards (5 kinds) + nonce'd deep-link ─────────
// Renders a chat_reply narrator turn BY its generic cardKind (SC-001) and fires
// onRequestOpenTab (the plan-03 seam) into a generic run tab. LOCK-F: the
// deliverable card says "Deliverable". spec_revision → "Revising spec — cycle N".

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
    ["clarify", "steps"],
    ["gate", "steps"],
    ["pipeline", "steps"],
    ["deliverable", "preview"],
    ["spec_revision", "steps"],
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

  it("renders the spec_revision loop-back label 'Revising spec — cycle N'", () => {
    render(
      <ResultCard
        message={narrator("spec_revision")}
        onRequestOpenTab={vi.fn()}
        cycle={3}
      />,
    );
    expect(screen.getByText("Revising spec — cycle 3")).toBeInTheDocument();
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
    expect(onRequestOpenTab).toHaveBeenCalledWith("steps");
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
});
