import { describe, it, expect } from "vitest";
import { mergePlanWithLibrary } from "./LaunchWizard";
import type { AgentDef } from "@/types";

const lib = (id: string, over: Partial<AgentDef> = {}): AgentDef => ({
  id, name: `lib ${id}`, role: "lib role", description: "lib desc",
  pipeline_type: "custom", order: 1, icon: "📚", estimated_duration: 42,
  has_skill: false, ...over,
});

describe("mergePlanWithLibrary", () => {
  it("keeps a fan-out parent's children even when the library knows the id", () => {
    const child = { ...lib("custom-agent:apple"), name: "Apple Writer" };
    const plan: AgentDef[] = [
      { ...lib("prototype-build"), name: "", icon: "", estimated_duration: 0,
        strategy: "parallel", maxParallel: 5, children: [child] } as AgentDef,
    ];
    const [out] = mergePlanWithLibrary(plan, [lib("prototype-build")]);
    expect(out.children?.map((c) => c.name)).toEqual(["Apple Writer"]);
    expect(out.strategy).toBe("parallel");
    expect(out.maxParallel).toBe(5);
    // presentation IS hydrated from the library
    expect(out.icon).toBe("📚");
    expect(out.estimated_duration).toBe(42);
    expect(out.name).toBe("lib prototype-build");
  });

  it("never lets the library overwrite the plan's authoring fields", () => {
    const plan: AgentDef[] = [
      { ...lib("prototype-build"), name: "Screen Builders", prompt: "mine",
        route: { outcomes: {}, default_next: "x" } } as AgentDef,
    ];
    const [out] = mergePlanWithLibrary(plan, [lib("prototype-build")]);
    expect(out.name).toBe("Screen Builders");
    expect(out.prompt).toBe("mine");
    expect(out.route).toEqual({ outcomes: {}, default_next: "x" });
  });

  it("passes custom-agent instances through untouched", () => {
    const plan: AgentDef[] = [
      { ...lib("custom-agent:page"), name: "Page Builder", isCustom: true,
        children: [{ ...lib("custom-agent:ball"), name: "Ball Writer" }] } as AgentDef,
    ];
    const [out] = mergePlanWithLibrary(plan, [lib("custom-agent")]);
    expect(out.name).toBe("Page Builder");
    expect(out.children?.[0].name).toBe("Ball Writer");
  });
});
