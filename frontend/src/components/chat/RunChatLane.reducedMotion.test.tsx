/**
 * QA-KB-001 / BUG-018-GROUNDED-CONTEXT / ISS-889 — RunChatLane's two collapsible footer panels
 * (settled run-summary strip, live Pipeline mini) must not tween when the OS asks for
 * reduced motion. Separate file: the motion/react mock below would change the other tests.
 * Fixed: both panels now gate their transition on useReducedMotion.
 */
import { describe, expect, it, vi } from "vitest";
import { renderWithProviders, screen } from "@/test/renderWithProviders";
import { RunChatLane, type RunChatLaneProps } from "./RunChatLane";

const osReduce = vi.hoisted(() => ({ value: false }));
vi.mock("motion/react", async (importOriginal) => {
  const actual = await importOriginal<typeof import("motion/react")>();
  const React = await import("react");
  const Div = React.forwardRef<HTMLDivElement, Record<string, unknown>>(function Probe(props, ref) {
    const { animate: _a, initial: _i, transition, ...rest } = props;
    return React.createElement("div", { ref, "data-transition": JSON.stringify(transition), ...rest });
  });
  return {
    ...actual,
    useReducedMotion: () => osReduce.value,
    motion: new Proxy(actual.motion, { get: (t, k) => (k === "div" ? Div : (t as never)[k as never]) }),
  };
});

const ps = (o: Record<string, unknown>) => ({
  isRunning: false,
  pipeline_type: "generic",
  agents: [],
  currentAgentIndex: 0,
  totalDuration: null,
  completedCount: 0,
  ...o,
});
const agent = (n: number, status: string) => ({
  id: `a${n}`, name: `Agent ${n}`, role: "", icon: "", status,
  output: "", thinking: "", duration: null, error: null, index: n,
});
const props = (o: Record<string, unknown>) =>
  ({ messages: [], runState: "idle", sendMessage: vi.fn(), ...o }) as unknown as RunChatLaneProps;

const settled = () =>
  renderWithProviders(
    <RunChatLane
      {...props({
        runState: "complete",
        pipelineState: ps({
          completedCount: 2,
          deliverableFilename: "a.html",
          deliverableVersion: 1,
          agents: [agent(1, "done"), agent(2, "done")],
        }),
      })}
    />,
  );
const live = () =>
  renderWithProviders(
    <RunChatLane
      {...props({
        runState: "building",
        pipelineState: ps({
          isRunning: true,
          completedCount: 3,
          agents: [1, 2, 3, 4, 5].map((n) => agent(n, n <= 3 ? "done" : n === 4 ? "running" : "idle")),
        }),
      })}
    />,
  );

const settledT = () => screen.getByTestId("lane-adornments").getAttribute("data-transition");
const liveT = () =>
  screen.getByTestId("lane-pipeline-mini-toggle").nextElementSibling!.getAttribute("data-transition");
const INSTANT = '{"duration":0}';
const TWEEN = '{"duration":0.22,"ease":"easeOut"}';

describe("QA-KB-001 reduced motion — RunChatLane footer panels", () => {
  it("ISS-889/BUG-018: settled run-summary strip is instant when OS=reduce", () => {
    osReduce.value = true;
    settled();
    expect(settledT()).toBe(INSTANT);
  });

  it("ISS-889: live Pipeline mini is instant when OS=reduce", () => {
    osReduce.value = true;
    live();
    expect(liveT()).toBe(INSTANT);
  });

  it("guard: settled strip keeps the 0.22s tween when OS does not request reduce", () => {
    osReduce.value = false;
    settled();
    expect(settledT()).toBe(TWEEN);
  });

  it("guard: live Pipeline mini keeps the 0.22s tween when OS does not request reduce", () => {
    osReduce.value = false;
    live();
    expect(liveT()).toBe(TWEEN);
  });
});
