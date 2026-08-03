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

  // FIX-128 regression: the backend's `deep_link.target` anchor ("run:<id>",
  // "deliverable:<file>", …) is a milestone REFERENCE, not a panel tab id. It must
  // NOT be handed to the tab seam — PreviewPanel drops unknown tab ids, which is
  // what broke "Open in Steps" / "Open in Preview". The kind's generic default wins.
  it("ignores the milestone anchor and opens the kind's default tab (FIX-128)", () => {
    const onSteps = vi.fn();
    const { unmount } = render(
      <ResultCard
        message={narrator("pipeline", {
          deepLink: { anchor: "run:93f7ca84-9f63-4d8a-90cf-8fbe8163d4b2", nonce: 0 },
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
          deepLink: { anchor: "deliverable:index.html", nonce: 0 },
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
});
