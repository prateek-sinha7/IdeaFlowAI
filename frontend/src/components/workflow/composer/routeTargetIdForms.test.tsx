/**
 * A route target works in EITHER id form, everywhere on the canvas.
 *
 * The backend has always accepted both — `_validate_route_targets` resolves
 * against `{every step's agent_id} ∪ {every step's instance_id}`, the file
 * workflows use the bare `instance_id`, and an engine-shaped manifest uses
 * `custom-agent:<instance_id>`. Four canvas consumers compared the raw target
 * to a node id by string equality, so the prefixed form silently failed in all
 * four at once: no edge drawn, the picker showing a raw id, the target flagged
 * "Not connected", and the layout parking it away from the flow as an orphan.
 *
 * These tests run the SAME graph twice, once in each form, and require the
 * results to agree. That is what stops the bare-id path regressing while the
 * prefixed one is fixed, or the reverse.
 */
import { describe, expect, it } from "vitest";

import type { AgentDef } from "@/types/index";
import {
  CUSTOM_AGENT_PREFIX,
  resolveRouteTargetId,
} from "@/store/api/userWorkflows";
import { computeRootLayout } from "./graphLayout";

const step = (id: string, route?: AgentDef["route"]): AgentDef =>
  ({ id, name: id, instance_id: id, agent: "custom-agent", route }) as unknown as AgentDef;

/** gate → { pass: forward to `after`, fail: back to `build` }. */
const graph = (target: (id: string) => string): AgentDef[] => [
  step("spec"),
  step("build"),
  step("gate", {
    outcomes: {
      pass: { trigger: "step", target: target("after") },
      fail: { trigger: "step", target: target("build") },
    },
    loop_max_iterations: 3,
  }),
  step("after"),
];

const BARE = (id: string) => id;
const PREFIXED = (id: string) => `${CUSTOM_AGENT_PREFIX}${id}`;
const SELECTIONS = { gate: { gates: ["conditional"] } } as never;

/** `rowPortOffset` is half a card's height; the value only scales the output. */
const layout = (agents: AgentDef[]) =>
  computeRootLayout(agents, SELECTIONS, 60).rootLayout;

describe("resolveRouteTargetId", () => {
  const knows = (id: string) => ["build", "after"].includes(id);

  it("returns a canvas id untouched", () => {
    expect(resolveRouteTargetId("build", knows)).toBe("build");
  });

  it("strips the backend prefix to reach the same step", () => {
    expect(resolveRouteTargetId(`${CUSTOM_AGENT_PREFIX}build`, knows)).toBe("build");
  });

  it("leaves a genuinely dangling target alone rather than hiding it", () => {
    expect(resolveRouteTargetId("nope", knows)).toBe("nope");
    expect(resolveRouteTargetId(`${CUSTOM_AGENT_PREFIX}nope`, knows)).toBe(
      `${CUSTOM_AGENT_PREFIX}nope`,
    );
  });

  it("prefers an exact match over stripping", () => {
    // A step literally named with the prefix resolves to itself, not to a
    // shorter id that happens to exist.
    const odd = (id: string) => id === `${CUSTOM_AGENT_PREFIX}build`;
    expect(resolveRouteTargetId(`${CUSTOM_AGENT_PREFIX}build`, odd)).toBe(
      `${CUSTOM_AGENT_PREFIX}build`,
    );
  });

  it("handles an empty target", () => {
    expect(resolveRouteTargetId("", knows)).toBe("");
  });
});

describe("canvas layout — both id forms rank the same", () => {
  it("places every node identically whichever form the route used", () => {
    const bare = layout(graph(BARE));
    const prefixed = layout(graph(PREFIXED));
    for (const id of ["spec", "build", "gate", "after"]) {
      expect(prefixed.get(id)).toEqual(bare.get(id));
    }
  });

  it("does not strand the forward route target in either form", () => {
    // The bug's signature: with the prefixed form the target was ranked as an
    // orphan and laid out away from the flow, left of and below its own gate.
    for (const form of [BARE, PREFIXED]) {
      const positions = layout(graph(form));
      // `col` is the layer: a forward route target must rank AFTER its gate.
      expect(positions.get("after")!.col).toBeGreaterThan(positions.get("gate")!.col);
    }
  });
});
