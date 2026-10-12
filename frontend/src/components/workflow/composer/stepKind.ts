import { Bot, Code, Layers, ListChecks, Waves, type LucideIcon } from "lucide-react";
import type { AgentDef } from "@/types/index";
import type { StepSelection } from "../AgentsPopup";

/** How a step runs — ONE rule for the canvas card's mark and the config
 *  rail's header, so the two can't disagree. Read from the live `selection`
 *  (what the rail's fan-out lever writes, seeded from the manifest on load). */
export interface StepKind {
  key: "code" | "wave" | "fanout" | "loop" | "agent";
  label: string;
  Icon: LucideIcon;
}

export function stepKind(agent: Pick<AgentDef, "mechanical" | "strategy">, selection?: StepSelection): StepKind {
  if (agent.mechanical) return { key: "code", label: "Code step", Icon: Code };
  if (selection?.strategy === "wave_scheduler") return { key: "wave", label: "Wave agent", Icon: Waves };
  if (selection?.strategy === "fanout_batch" || agent.strategy === "fanout")
    return { key: "fanout", label: "Fan-out agent", Icon: Layers };
  if (selection?.strategy === "task_loop") return { key: "loop", label: "Task loop agent", Icon: ListChecks };
  return { key: "agent", label: "AI agent", Icon: Bot };
}
