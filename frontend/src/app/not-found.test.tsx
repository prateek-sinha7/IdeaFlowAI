import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";

import NotFoundPage from "./not-found";

// next/link and next/image render real <a>/<img> in jsdom outside the Next
// runtime (Link falls back to a plain anchor with the given href), so neither
// boundary needs a mock. Image is asserted via its rendered alt/src contract.

describe("NotFoundPage", () => {
  it("renders the 404 heading and explanation for the main region", () => {
    render(<NotFoundPage />);

    expect(screen.getByRole("heading", { level: 1, name: "Not found" })).toBeInTheDocument();
    expect(screen.getByText("404")).toBeInTheDocument();
    expect(
      screen.getByText("The page you're looking for doesn't exist or has been moved."),
    ).toBeInTheDocument();
  });

  it("renders the support hint in the footer note", () => {
    render(<NotFoundPage />);

    expect(
      screen.getByText(
        "If you believe this is an error, check the URL for typos or contact support.",
      ),
    ).toBeInTheDocument();
  });

  it.each([
    { name: "Back to dashboard", href: "/dashboard" },
    { name: "Create a workflow", href: "/create" },
    { name: "Sign in", href: "/login" },
  ])("links to $href from the '$name' action", ({ name, href }) => {
    render(<NotFoundPage />);

    const link = screen.getByRole("link", { name });

    expect(link).toHaveAttribute("href", href);
  });

  it("offers exactly three recovery links", () => {
    render(<NotFoundPage />);

    expect(screen.getAllByRole("link")).toHaveLength(3);
  });

  it("renders the Hexaware logo with its alt text in the brand panel", () => {
    render(<NotFoundPage />);

    const panel = screen.getByTestId("not-found-brand-panel");

    expect(within(panel).getByRole("img", { name: "Hexaware" })).toBeInTheDocument();
    expect(within(panel).getByText("VelocityAI")).toBeInTheDocument();
  });

  it("renders the brand statement and decorative tags in the brand panel", () => {
    render(<NotFoundPage />);

    const panel = screen.getByTestId("not-found-brand-panel");

    expect(within(panel).getByRole("heading", { level: 2, name: "Page not found." })).toBeInTheDocument();
    expect(within(panel).getByText("It happens")).toBeInTheDocument();
    for (const tag of ["Lost?", "Typo?", "Moved."]) {
      expect(within(panel).getByText(tag)).toBeInTheDocument();
    }
  });

  it("keeps the brand panel free of interactive controls", () => {
    render(<NotFoundPage />);

    const panel = screen.getByTestId("not-found-brand-panel");

    expect(within(panel).queryByRole("link")).not.toBeInTheDocument();
    expect(within(panel).queryByRole("button")).not.toBeInTheDocument();
  });
});
