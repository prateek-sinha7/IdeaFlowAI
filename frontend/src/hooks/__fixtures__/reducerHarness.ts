/**
 * The ONE driver for `handlePipelineMessage` in unit tests.
 *
 * Extracted from `useWorkflow.specRevisionCount.test.ts` when
 * `useWorkflow.accumulators.test.ts` needed the same thing (ISS-082): two copies of a
 * replay harness would be two DIFFERENT definitions of "replay", and the whole point of
 * the accumulator suite is that every spec agrees on what a re-delivery is.
 *
 * Not a `*.test.ts`, so vitest's `include` glob (`src/**\/*.{test,spec}.{ts,tsx}`) never
 * collects it as a suite.
 */
import type { PipelineRunState } from "@/types/index";
import { handlePipelineMessage } from "../useWorkflow";

/** A frame as it reaches the reducer: flat, with `type` plus the payload keys. */
export type ReducerFrame = { type: string; [k: string]: unknown };

/** A run that has not started — the reducer's own INITIAL_STATE shape. */
export const EMPTY_STATE: PipelineRunState = {
  isRunning: false,
  pipeline_type: "",
  agents: [],
  currentAgentIndex: -1,
  totalDuration: null,
  completedCount: 0,
};

/**
 * Feed frames through the reducer the way `useRunStateStore.handleFrame` does:
 * a synchronous dispatch that writes straight back into the same object. This is
 * the replay model — one tight loop with no React commit between frames.
 */
export function runFrames(frames: ReducerFrame[]): PipelineRunState {
  let state: PipelineRunState = { ...EMPTY_STATE };
  const times = { current: {} as Record<string, number> };
  for (const f of frames) {
    handlePipelineMessage(
      f,
      ((updater) => {
        state = typeof updater === "function" ? (updater as (p: PipelineRunState) => PipelineRunState)(state) : updater;
      }) as React.Dispatch<React.SetStateAction<PipelineRunState>>,
      times,
    );
  }
  return state;
}
