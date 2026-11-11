/**
 * Regression: a Composer save must PERSIST the per-step model and effort.
 *
 * Found by a real end-to-end run, not by a unit test. Four agents were each set
 * to a different model in the canvas rail (Haiku 4.5 / GPT-5.6 Luna+high /
 * Sonnet 5+on / GPT-5.6 Sol+xhigh), saved, and run — and every one of them
 * executed on the workflow default. The PATCH body carried prompts, tools,
 * gates and routes but no `model` key on any step.
 *
 * Cause: `agentToManifestStep` read `selections[agent.id]` for `.gates`,
 * `.tools`, `.strategy`, `.task_source`, `.fanout` and `.on_conflict` — but
 * never `.model` or `.effort`. So the full-manifest save branch (taken once any
 * step has a skill, a custom prompt, a route or a sub-agent tree) silently
 * dropped the author's model override. The Model dropdown predates spec 020,
 * so this was broken for model long before effort existed.
 *
 * The shape asserted here is the backend compiler's ModelPolicy mapping
 * (`_parse_model`, compiler.py) — `{model, effort}`, never a bare string.
 */
import { describe, it, expect } from "vitest";
import { agentsToManifestSteps } from "./userWorkflows";
import type { AgentDef } from "@/types/index";

function agent(id: string, over: Partial<AgentDef> = {}): AgentDef {
  return {
    id,
    name: id,
    role: "r",
    description: "d",
    pipeline_type: "custom",
    order: 1,
    icon: "",
    estimated_duration: 1,
    has_skill: false,
    isCustom: true,
    instance_id: id,
    prompt: "do a thing",
    ...over,
  } as AgentDef;
}

describe("agentsToManifestSteps — per-step model + effort (spec 020)", () => {
  it("writes the selected model onto the step as a ModelPolicy mapping", () => {
    const steps = agentsToManifestSteps([agent("a")], {
      a: { model: "global.openai.gpt-5.6-luna" },
    });
    expect(steps[0].model).toEqual({ model: "global.openai.gpt-5.6-luna" });
  });

  it("writes model AND effort together", () => {
    const steps = agentsToManifestSteps([agent("a")], {
      a: { model: "global.openai.gpt-5.6-sol", effort: "xhigh" },
    });
    expect(steps[0].model).toEqual({
      model: "global.openai.gpt-5.6-sol",
      effort: "xhigh",
    });
  });

  it("keeps each agent's own model — the bug was all four sharing the default", () => {
    const steps = agentsToManifestSteps(
      [agent("emoji"), agent("greet"), agent("check"), agent("done")],
      {
        emoji: { model: "eu.anthropic.claude-haiku-4-5-20251001-v1:0" },
        greet: { model: "global.openai.gpt-5.6-luna", effort: "high" },
        check: { model: "eu.anthropic.claude-sonnet-5", effort: "on" },
        done: { model: "global.openai.gpt-5.6-sol", effort: "xhigh" },
      },
    );
    expect(steps.map((s) => s.model)).toEqual([
      { model: "eu.anthropic.claude-haiku-4-5-20251001-v1:0" },
      { model: "global.openai.gpt-5.6-luna", effort: "high" },
      { model: "eu.anthropic.claude-sonnet-5", effort: "on" },
      { model: "global.openai.gpt-5.6-sol", effort: "xhigh" },
    ]);
  });

  it("emits NO model key when the author set neither", () => {
    // Parity: an untouched step must serialise exactly as it did before, so a
    // saved workflow does not suddenly pin itself to the default model.
    const steps = agentsToManifestSteps([agent("a")], { a: {} });
    expect(steps[0].model).toBeUndefined();
  });

  it("preserves hand-authored model keys the canvas cannot edit", () => {
    // `max_tokens` / `fallback` ride in via AgentDef.extra. Overwriting the whole
    // mapping would silently drop a fallback chain the author wrote by hand.
    const steps = agentsToManifestSteps(
      [agent("a", { extra: { model: { max_tokens: 4096, fallback: ["eu.anthropic.claude-sonnet-4-6"] } } })],
      { a: { model: "global.openai.gpt-5.6-luna", effort: "high" } },
    );
    expect(steps[0].model).toEqual({
      max_tokens: 4096,
      fallback: ["eu.anthropic.claude-sonnet-4-6"],
      model: "global.openai.gpt-5.6-luna",
      effort: "high",
    });
  });

  it("drops the draft's old effort — keeping hand-authored keys — when the rail changed the model", () => {
    // The draft step carried {GPT, xhigh}; the user switched to Haiku and the rail
    // cleared the effort. The inherited effort must not come back on save.
    const steps = agentsToManifestSteps(
      [
        agent("a", {
          extra: { model: { model: "global.openai.gpt-5.6-sol", effort: "xhigh", max_tokens: 4096 } },
        }),
      ],
      { a: { model: "eu.anthropic.claude-haiku-4-5-20251001-v1:0" } },
    );
    expect(steps[0].model).toEqual({
      model: "eu.anthropic.claude-haiku-4-5-20251001-v1:0",
      max_tokens: 4096,
    });
  });

  it("keeps the rail's effort over the inherited one when both are present", () => {
    const steps = agentsToManifestSteps(
      [agent("a", { extra: { model: { model: "global.openai.gpt-5.6-sol", effort: "xhigh" } } })],
      { a: { model: "global.openai.gpt-5.6-sol", effort: "low" } },
    );
    expect(steps[0].model).toEqual({ model: "global.openai.gpt-5.6-sol", effort: "low" });
  });

  it("leaves the inherited policy untouched when the step has no selection", () => {
    const steps = agentsToManifestSteps(
      [agent("a", { extra: { model: { model: "global.openai.gpt-5.6-sol", effort: "xhigh" } } })],
      {},
    );
    expect(steps[0].model).toEqual({ model: "global.openai.gpt-5.6-sol", effort: "xhigh" });
  });
});
