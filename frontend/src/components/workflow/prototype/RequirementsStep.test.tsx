/**
 * RequirementsStep unit tests (T3.2)
 *
 * Covers per tasks.md:
 * - Renders the upload zone and optional textarea.
 * - onValidityChange(false) is called on mount (no files yet).
 * - hasStagedPDF=true → onValidityChange(true) is called.
 * - hasStagedPDF=false with attachedFiles present → warning banner shown.
 * - Warning banner hidden on initial render (no files, no interaction).
 * - Additional context textarea fires onAdditionalContextChange on input.
 * - Clicking Attach PDF button calls onPickFiles.
 * - Remove button calls onRemoveFile with correct index.
 */

import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { RequirementsStep } from "./RequirementsStep";
import type { RequirementsStepProps } from "./RequirementsStep";
import type { StagedDocument } from "@/hooks/useStagedDocuments";

// UploadChipStatus renders a small status indicator — shallow-enough to mock.
vi.mock("@/components/workflow/UploadChipStatus", () => ({
  UploadChipStatus: () => null,
}));

vi.mock("@/lib/uploadErrors", () => ({
  UPLOAD_TOO_LARGE_MESSAGE: "File too large",
}));

const staged: StagedDocument = { key: 0, name: "req.pdf", status: "staged", stageId: "s1" };

function makeProps(overrides: Partial<RequirementsStepProps> = {}): RequirementsStepProps {
  return {
    isValid: false,
    onValidityChange: vi.fn(),
    stagedDocuments: [],
    attachedFiles: [],
    previewFailedKeys: [],
    onPickFiles: vi.fn(),
    onRemoveFile: vi.fn(),
    onRetryFile: vi.fn(),
    additionalContext: "",
    onAdditionalContextChange: vi.fn(),
    ...overrides,
  };
}

describe("RequirementsStep", () => {
  it("renders the attach button and textarea", () => {
    render(<RequirementsStep {...makeProps()} />);
    expect(screen.getByTestId("attach-pdf-button")).toBeInTheDocument();
    expect(screen.getByTestId("additional-context")).toBeInTheDocument();
  });

  it("calls onValidityChange(false) on mount when no files staged", () => {
    const onValidityChange = vi.fn();
    render(<RequirementsStep {...makeProps({ isValid: false, onValidityChange })} />);
    expect(onValidityChange).toHaveBeenCalledWith(false);
  });

  it("calls onValidityChange(true) when isValid=true is passed", () => {
    const onValidityChange = vi.fn();
    render(
      <RequirementsStep
        {...makeProps({
          isValid: true,
          onValidityChange,
          stagedDocuments: [staged],
          attachedFiles: [{ name: "req.pdf", size: "10 KB", stageKey: 0 }],
        })}
      />,
    );
    expect(onValidityChange).toHaveBeenCalledWith(true);
  });

  it("does NOT show the warning banner when no files are attached yet", () => {
    render(<RequirementsStep {...makeProps({ isValid: false, attachedFiles: [] })} />);
    expect(screen.queryByTestId("requirements-warning")).not.toBeInTheDocument();
  });

  it("shows warning when files are attached but none is valid (staged)", () => {
    const failedDoc: StagedDocument = { key: 0, name: "req.pdf", status: "failed", reason: "network error" };
    render(
      <RequirementsStep
        {...makeProps({
          isValid: false,
          stagedDocuments: [failedDoc],
          attachedFiles: [{ name: "req.pdf", size: "10 KB", stageKey: 0 }],
        })}
      />,
    );
    expect(screen.getByTestId("requirements-warning")).toBeInTheDocument();
  });

  it("clicking attach PDF button calls onPickFiles", () => {
    const onPickFiles = vi.fn();
    render(<RequirementsStep {...makeProps({ onPickFiles })} />);
    fireEvent.click(screen.getByTestId("attach-pdf-button"));
    expect(onPickFiles).toHaveBeenCalledOnce();
  });

  it("additional context textarea fires onAdditionalContextChange", () => {
    const onAdditionalContextChange = vi.fn();
    render(<RequirementsStep {...makeProps({ onAdditionalContextChange })} />);
    fireEvent.change(screen.getByTestId("additional-context"), {
      target: { value: "Use Stripe branding" },
    });
    expect(onAdditionalContextChange).toHaveBeenCalledWith("Use Stripe branding");
  });

  it("remove button calls onRemoveFile with the correct index", () => {
    const onRemoveFile = vi.fn();
    render(
      <RequirementsStep
        {...makeProps({
          isValid: true,
          stagedDocuments: [staged],
          attachedFiles: [{ name: "req.pdf", size: "10 KB", stageKey: 0 }],
          onRemoveFile,
        })}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /Remove req\.pdf/i }));
    expect(onRemoveFile).toHaveBeenCalledWith(0);
  });

  it("shows 'Attach another PDF' label when files already attached", () => {
    render(
      <RequirementsStep
        {...makeProps({
          isValid: true,
          stagedDocuments: [staged],
          attachedFiles: [{ name: "req.pdf", size: "10 KB", stageKey: 0 }],
        })}
      />,
    );
    expect(screen.getByTestId("attach-pdf-button")).toHaveTextContent("Attach another PDF");
  });

  it("does NOT call onValidityChange again if isValid prop does not change", () => {
    const onValidityChange = vi.fn();
    const { rerender } = render(
      <RequirementsStep {...makeProps({ isValid: false, onValidityChange })} />,
    );
    expect(onValidityChange).toHaveBeenCalledTimes(1);
    // Re-render with the same isValid — no second call.
    rerender(<RequirementsStep {...makeProps({ isValid: false, onValidityChange })} />);
    expect(onValidityChange).toHaveBeenCalledTimes(1);
  });
});
