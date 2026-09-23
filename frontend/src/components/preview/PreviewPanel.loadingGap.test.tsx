/**
 * ISS-739 / ISS-740 — QA-PS-014: a cold `/runs/{id}*` reopen has no
 * fetch-in-flight signal anywhere. `handleSelectWorkflowRun` (page.tsx) sets
 * no loading flag, so `PreviewPanel`'s only in-progress gate — `isStillRunning`
 * (`!!(isStreaming || pipelineState?.isRunning)`) — is false for the whole
 * fetch window on a reopened terminal run, and `hasContent` is unpopulated
 * until the fetch resolves. With both false, the neutral `!hasContent` branch
 * ("Output will appear here") fires identically for "still fetching" and
 * "genuinely empty" (ISS-739).
 *
 * ISS-740 is the same gap on the failure/cancelled/degraded/diverted axis:
 * `reopenedRunStatus` is reset to `undefined` at fetch start and only set once
 * the fetch resolves (page.tsx), so `reopenFailureSignal`/`isDivertedTerminal`
 * are `false` by construction during the fetch — a reopen that will turn out
 * to be failed/cancelled/diverted shows the same neutral, success-shaped
 * placeholder before flipping to its real affordance a moment later.
 *
 * There is today no prop PreviewPanel can be given that distinguishes "still
 * fetching" from "confirmed empty terminal run" — these tests render the
 * neutral-branch inputs (no content, no running signal, no reopen status) and
 * assert the neutral copy must NOT be the thing shown once a fetch-in-flight
 * signal exists. They fail today because no such signal exists to change the
 * outcome; see `.knowledge/cards/20260922-1407-ISS-739.md` and
 * `20260922-1408-ISS-740.md`.
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";
import { PreviewPanel } from "./PreviewPanel";
import type { PipelineRunState, WorkflowStatus } from "@/types/index";

const STRIPPED_MOTION_PROPS = new Set([
  "initial", "animate", "exit", "transition", "whileHover",
  "whileTap", "whileFocus", "whileInView", "viewport", "layout",
  "layoutId", "drag", "dragConstraints", "variants", "custom",
]);
vi.mock("motion/react", () => ({
  motion: new Proxy(
    {},
    {
      get: (_target, prop: string) =>
        ({ children, ...rest }: { children?: React.ReactNode } & Record<string, unknown>) => {
          const cleaned = Object.fromEntries(
            Object.entries(rest).filter(([k]) => !STRIPPED_MOTION_PROPS.has(k)),
          );
          return React.createElement(prop, cleaned, children);
        },
    },
  ),
  AnimatePresence: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
}));
vi.mock("./UserStoryPreview", () => ({ UserStoryPreview: () => <div data-testid="user-story-preview" /> }));
vi.mock("./PPTPreview", () => ({ PPTPreview: () => <div data-testid="ppt-preview" /> }));
vi.mock("./PrototypePreview", () => ({ PrototypePreview: () => <div data-testid="proto-preview" /> }));
vi.mock("./MarkdownPreview", () => ({ MarkdownPreview: () => <div data-testid="markdown-preview" /> }));
vi.mock("./AppBuilderPreview", () => ({ AppBuilderPreview: () => <div data-testid="appbuilder-preview" /> }));
vi.mock("@/components/results/FilesTab", () => ({
  FilesTab: () => <div data-testid="files-tab" />,
  deriveDeliverableFilename: () => "deliverable",
}));
vi.mock("@/components/results/AgentThinkingTab", () => ({ AgentThinkingTab: () => <div data-testid="thinking-tab" /> }));
vi.mock("@/components/results/AuditTab", () => ({ AuditTab: () => <div data-testid="audit-tab" /> }));

function makePipelineState(overrides: Partial<PipelineRunState> = {}): PipelineRunState {
  return {
    isRunning: false,
    pipeline_type: "user_stories",
    agents: [],
    currentAgentIndex: -1,
    totalDuration: null,
    completedCount: 0,
    ...overrides,
  };
}

const NEUTRAL_COPY = /output will appear here/i;

// PreviewPanel has no fetch-in-flight prop today — this cast lets the tests
// express the intended future signal without a compile error, mirroring the
// card's proposed `isLoadingRunData`. Until the fixer wires it in, the extra
// prop is silently ignored and the component behaves exactly as it does
// today, which is precisely the defect these tests pin.
const LoadingAwarePreviewPanel = PreviewPanel as unknown as React.FC<
  React.ComponentProps<typeof PreviewPanel> & { isLoadingRunData?: boolean }
>;

describe("ISS-739 — reopened-run fetch in flight must not read as an empty run", () => {
  it(
    "ISS-739 — while the reopen fetch is in flight (no content, not streaming, no pipeline signal), the neutral empty-state must not be shown",
    () => {
      render(
        <LoadingAwarePreviewPanel
          workflowType="user_stories"
          isStreaming={false}
          pipelineState={makePipelineState({ isRunning: false })}
          isLoadingRunData={true}
        />,
      );
      // BUG (ISS-739): isLoadingRunData is not read anywhere yet, so this is
      // indistinguishable from a confirmed-empty terminal run and the neutral
      // "Output will appear here" copy renders regardless.
      expect(screen.queryByText(NEUTRAL_COPY)).not.toBeInTheDocument();
    },
  );
});

describe("ISS-740 — a reopen that will turn out failed/cancelled/diverted must not show the neutral copy first", () => {
  it(
    "ISS-740 — while reopenedRunStatus is still undefined (fetch in flight) for a run that will resolve to a failure/cancel/divert, the neutral empty-state must not be shown",
    () => {
      render(
        <LoadingAwarePreviewPanel
          workflowType="prototype"
          isStreaming={false}
          reopenedRunStatus={undefined as unknown as WorkflowStatus}
          isLoadingRunData={true}
        />,
      );
      // BUG (ISS-740): reopenFailureSignal/isDivertedTerminal are both false
      // while reopenedRunStatus is undefined, and isLoadingRunData is not
      // read anywhere — so the neutral "success-shaped" placeholder renders
      // during the same window a failed/cancelled/diverted affordance is
      // about to replace it.
      expect(screen.queryByText(NEUTRAL_COPY)).not.toBeInTheDocument();
    },
  );
});
