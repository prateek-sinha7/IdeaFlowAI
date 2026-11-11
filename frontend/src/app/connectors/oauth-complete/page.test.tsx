import { describe, expect, it, vi } from "vitest";
import { render } from "@testing-library/react";

import OAuthCompletePage, { metadata } from "./page";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

describe("oauth-complete page", () => {
  it("asks search engines not to index or follow", () => {
    expect(metadata.robots).toEqual({ index: false, follow: false });
  });

  it("renders the client component inside the Suspense boundary", () => {
    const { container } = render(<OAuthCompletePage />);

    expect(container.querySelector("main")).not.toBeNull();
  });
});
