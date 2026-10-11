import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { ComplianceReportView, TestReportView } from "./ReportViews";
import type { HandoffComplianceFinding } from "./types";

describe("TestReportView", () => {
  it("shows the empty state when no report is given", () => {
    render(<TestReportView />);
    expect(screen.getByText(/test report will appear here/)).toBeInTheDocument();
  });

  it("shows pending verdict and no sections for an empty report", () => {
    render(<TestReportView report={{}} />);
    expect(screen.getByText("pending")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 4 })).not.toBeInTheDocument();
  });

  it.each([
    ["pass", "emerald"],
    ["concerns", "amber"],
    ["fail", "red"],
    ["weird_value", "gray"],
  ])("renders verdict %s", (verdict, color) => {
    render(<TestReportView report={{ verdict }} />);
    const pill = screen.getByText(verdict.replace(/_/g, " "));
    expect(pill.className).toContain(color);
  });

  it("renders all sections with data", () => {
    render(
      <TestReportView
        report={{
          summary: "Summary text",
          verdict: "pass",
          missing_coverage: [{ area: "Login", suggested_test: "test login" }],
          quality_issues: [
            { path: "a.ts", issue: "flaky", severity: "high" },
            { path: "b.ts", issue: "slow", severity: "medium" },
            { path: "c.ts", issue: "meh", severity: "low" },
          ],
          recommended_additions: ["add e2e"],
          tests_present: [{ path: "x.test.ts", covers: "x" }],
        }}
      />
    );
    expect(screen.getByText("Summary text")).toBeInTheDocument();
    expect(screen.getByText("Missing coverage (1)")).toBeInTheDocument();
    expect(screen.getByText("Login")).toBeInTheDocument();
    expect(screen.getByText("Test-quality issues (3)")).toBeInTheDocument();
    expect(screen.getByText("high").className).toContain("red");
    expect(screen.getByText("medium").className).toContain("amber");
    expect(screen.getByText("low").className).toContain("gray");
    expect(screen.getByText("add e2e")).toBeInTheDocument();
    expect(screen.getByText("Existing test coverage")).toBeInTheDocument();
    expect(screen.getByText("x.test.ts")).toBeInTheDocument();
  });

  it("omits sections for empty arrays", () => {
    render(
      <TestReportView
        report={{ missing_coverage: [], quality_issues: [], recommended_additions: [], tests_present: [] }}
      />
    );
    expect(screen.queryByRole("heading", { level: 4 })).not.toBeInTheDocument();
  });
});

describe("ComplianceReportView", () => {
  const f = (severity: string, issue: string, recommendation = ""): HandoffComplianceFinding => ({
    category: "sec",
    severity,
    location: "file.ts:1",
    issue,
    recommendation,
  });

  it("shows the empty state when no report is given", () => {
    render(<ComplianceReportView />);
    expect(screen.getByText(/compliance report will appear here/)).toBeInTheDocument();
  });

  it.each([
    ["approve", "emerald"],
    ["approve_with_changes", "amber"],
    ["request_changes", "red"],
  ])("renders verdict %s", (verdict, color) => {
    render(<ComplianceReportView report={{ verdict }} />);
    expect(screen.getByText(verdict.replace(/_/g, " ")).className).toContain(color);
  });

  it("renders pending verdict and no sections for an empty report", () => {
    render(<ComplianceReportView report={{}} />);
    expect(screen.getByText("pending")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 4 })).not.toBeInTheDocument();
  });

  it("orders findings by severity and treats missing severity as low", () => {
    render(
      <ComplianceReportView
        report={{
          summary: "Looks ok",
          findings: [
            f("low", "issue-low"),
            f("Critical", "issue-critical", "fix it"),
            f("", "issue-blank"),
            f("high", "issue-high"),
            f("medium", "issue-medium"),
          ],
          positives: ["good tests"],
        }}
      />
    );
    expect(screen.getByText("Findings (5)")).toBeInTheDocument();
    expect(screen.getByText("Looks ok")).toBeInTheDocument();
    const order = screen
      .getAllByText(/^issue-/)
      .map((n) => n.textContent);
    expect(order).toEqual(["issue-critical", "issue-high", "issue-medium", "issue-low", "issue-blank"]);
    expect(screen.getByText("fix it")).toBeInTheDocument();
    expect(screen.getByText("good tests")).toBeInTheDocument();
  });

  it("omits findings and positives sections when empty", () => {
    render(<ComplianceReportView report={{ findings: [], positives: [] }} />);
    expect(screen.queryByText(/Findings/)).not.toBeInTheDocument();
    expect(screen.queryByText(/does well/)).not.toBeInTheDocument();
  });
});
