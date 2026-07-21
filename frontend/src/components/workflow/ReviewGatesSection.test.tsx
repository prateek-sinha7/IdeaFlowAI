/**
 * Phase 6 (T6 verify gate) — frontend gate-toggle + LIBRARY_AGENTS data integrity.
 *
 * Two layers, both durable:
 *
 *  1. DATA INTEGRITY of the regenerated `LIBRARY_AGENTS` (`AgentLibraryData.ts`):
 *     the prototype block is exactly the real spec-kit ids; the ppt block is the
 *     real od-ppt ids; NO stale/retired ids survive anywhere; every entry carries
 *     a `gate` field; and the ONLY `gate === "Human_Gate"` entries are
 *     `prototype-specify` + `prototype-plan`. These are the front/back-drift
 *     regressions the reconciliation closed — if `AgentLibraryData.ts` is edited
 *     out of sync, these fail.
 *
 *  2. `ReviewGatesSection` COMPONENT behavior (jsdom + @testing-library/react,
 *     the same stack `AgentProgressPanel.test.tsx` uses):
 *       - renders one checkbox per agent;
 *       - `prototype-specify` / `prototype-plan` start CHECKED, the others
 *         unchecked — i.e. the pre-check set == the `gate === "Human_Gate"` set;
 *       - the first `onChange` is `(humanGateIds, touched=false)` → the caller
 *         omits `gate_agent_ids` (backend static default, byte-identical);
 *       - toggling a checkbox fires `onChange(..., touched=true)` with the
 *         updated id set, in pipeline order;
 *       - unchecking ALL gates yields `onChange([], true)` — the "touched, no
 *         gates" payload (`gate_agent_ids: []`).
 */

import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ReviewGatesSection } from "./ReviewGatesSection";
import {
  LIBRARY_AGENTS,
  CUSTOM_AGENTS,
  ALL_LIBRARY_AGENTS,
  PIPELINE_CATEGORIES,
} from "./AgentLibraryData";
import type { AgentDef } from "@/types/index";

// ───────────────────────────────────────────────────────────────────────────
// Shared fixtures
// ───────────────────────────────────────────────────────────────────────────

const REAL_PROTOTYPE_IDS = [
  "prototype-specify",
  "prototype-plan",
  "prototype-analyze",
  "prototype-build",
  "prototype-validate",
];
const REAL_PPT_IDS = ["od-ppt-brief-analyst", "od-ppt-composer", "od-ppt-validator"];

// Ids that MUST NOT survive the regeneration (retired prototype_v1 + the old
// pre-od PPT pipeline). Checked across the whole agent pool.
const STALE_IDS = [
  "requirements-analyst",
  "html-prototype-builder",
  "prototype-polisher",
  "prototype-finalizer",
  "ppt-content-strategist",
  "ppt-visual-designer",
  "ppt-data-storyteller",
  "ppt-deck-builder",
];

const byPipeline = (type: string): AgentDef[] =>
  LIBRARY_AGENTS.filter((a) => a.pipeline_type === type).sort(
    (a, b) => a.order - b.order,
  );

// The pure pre-check predicate the component encodes (mirrors `isDefaultGated`).
const isHumanGate = (a: AgentDef): boolean => a.gate === "Human_Gate";

// ───────────────────────────────────────────────────────────────────────────
// 1. LIBRARY_AGENTS data integrity
// ───────────────────────────────────────────────────────────────────────────

describe("LIBRARY_AGENTS data integrity (reconciliation)", () => {
  it("prototype block is exactly the real spec-kit ids, in order", () => {
    expect(byPipeline("prototype").map((a) => a.id)).toEqual(REAL_PROTOTYPE_IDS);
  });

  it("ppt block is exactly the real od-ppt ids, in order", () => {
    expect(byPipeline("ppt").map((a) => a.id)).toEqual(REAL_PPT_IDS);
  });

  it("contains no stale / retired ids anywhere in the agent pool", () => {
    const allIds = new Set(ALL_LIBRARY_AGENTS.map((a) => a.id));
    const leaked = STALE_IDS.filter((id) => allIds.has(id));
    expect(leaked).toEqual([]);
  });

  it("every agent entry carries a `gate` field (string or null)", () => {
    for (const a of ALL_LIBRARY_AGENTS) {
      // The key must be present; value is "Human_Gate" | "Validation_Gate" | null.
      expect(Object.prototype.hasOwnProperty.call(a, "gate")).toBe(true);
      expect(a.gate === null || typeof a.gate === "string").toBe(true);
    }
  });

  it("the ONLY Human_Gate agents are prototype-specify + prototype-plan + prototype-analyze", () => {
    const humanGateIds = ALL_LIBRARY_AGENTS.filter(isHumanGate)
      .map((a) => a.id)
      .sort();
    expect(humanGateIds).toEqual(["prototype-analyze", "prototype-plan", "prototype-specify"]);
  });

  it("prototype build/validate are ungated (gate === null)", () => {
    const gateById = Object.fromEntries(
      byPipeline("prototype").map((a) => [a.id, a.gate]),
    );
    expect(gateById["prototype-specify"]).toBe("Human_Gate");
    expect(gateById["prototype-plan"]).toBe("Human_Gate");
    expect(gateById["prototype-analyze"]).toBe("Human_Gate");
    expect(gateById["prototype-build"]).toBeNull();
    expect(gateById["prototype-validate"]).toBeNull();
  });

  it("PIPELINE_CATEGORIES counts are reconciled (ppt=3, prototype=5, all=55)", () => {
    const counts = Object.fromEntries(
      PIPELINE_CATEGORIES.map((c) => [c.key, c.count]),
    );
    expect(counts.ppt).toBe(3);
    expect(counts.prototype).toBe(5);
    // `all` counts the LIBRARY_AGENTS pool (CUSTOM_AGENTS is a separate array).
    expect(counts.all).toBe(LIBRARY_AGENTS.length);
    expect(counts.all).toBe(55);
    expect(counts.custom).toBe(CUSTOM_AGENTS.length);
  });

  it("each non-custom category count matches the LIBRARY_AGENTS membership", () => {
    for (const c of PIPELINE_CATEGORIES) {
      if (c.key === "all" || c.key === "custom") continue;
      expect(byPipeline(c.key).length).toBe(c.count);
    }
  });
});

// ───────────────────────────────────────────────────────────────────────────
// 2. The pure pre-check predicate (data-level, no DOM)
// ───────────────────────────────────────────────────────────────────────────

describe("pre-check predicate (gate === Human_Gate)", () => {
  it("selects exactly the default-gated agents for the prototype pipeline", () => {
    const prototypeAgents = byPipeline("prototype");
    const preChecked = prototypeAgents.filter(isHumanGate).map((a) => a.id);
    expect(preChecked).toEqual(["prototype-specify", "prototype-plan", "prototype-analyze"]);
  });

  it("selects nothing for the ppt pipeline (no default gates)", () => {
    expect(byPipeline("ppt").filter(isHumanGate)).toEqual([]);
  });
});

// ───────────────────────────────────────────────────────────────────────────
// 3. ReviewGatesSection component behavior (jsdom)
// ───────────────────────────────────────────────────────────────────────────

describe("ReviewGatesSection — prototype pipeline", () => {
  const prototypeAgents = byPipeline("prototype");

  /** Render with the body expanded so the checkboxes are in the DOM. */
  async function renderExpanded(onChange = vi.fn()) {
    const user = userEvent.setup();
    render(<ReviewGatesSection agents={prototypeAgents} onChange={onChange} />);
    // Open the expandable section (the header is the first button).
    await user.click(screen.getByRole("button", { name: /review gates/i }));
    return { user, onChange };
  }

  it("renders one checkbox per agent", async () => {
    await renderExpanded();
    expect(screen.getAllByRole("checkbox")).toHaveLength(prototypeAgents.length);
  });

  it("pre-checks ONLY prototype-specify + prototype-plan + prototype-analyze", async () => {
    await renderExpanded();
    // Checkboxes render in pipeline order; map them back to ids.
    const checkboxes = screen.getAllByRole("checkbox") as HTMLInputElement[];
    const checkedById: Record<string, boolean> = {};
    prototypeAgents.forEach((agent, i) => {
      checkedById[agent.id] = checkboxes[i].checked;
    });
    expect(checkedById).toEqual({
      "prototype-specify": true,
      "prototype-plan": true,
      "prototype-analyze": true,
      "prototype-build": false,
      "prototype-validate": false,
    });
  });

  it("the pre-checked set equals the gate===Human_Gate set", async () => {
    await renderExpanded();
    const checkboxes = screen.getAllByRole("checkbox") as HTMLInputElement[];
    const checkedIds = prototypeAgents
      .filter((_, i) => checkboxes[i].checked)
      .map((a) => a.id);
    const humanGateIds = prototypeAgents.filter(isHumanGate).map((a) => a.id);
    expect(checkedIds).toEqual(humanGateIds);
  });

  it("first onChange reports the default gate ids with touched=false", () => {
    const onChange = vi.fn();
    render(<ReviewGatesSection agents={prototypeAgents} onChange={onChange} />);
    // The initial report fires on mount (no expand needed).
    expect(onChange).toHaveBeenCalled();
    const [ids, touched] = onChange.mock.calls[onChange.mock.calls.length - 1];
    expect(ids).toEqual(["prototype-specify", "prototype-plan", "prototype-analyze"]);
    expect(touched).toBe(false);
  });

  it("toggling a checkbox fires onChange with touched=true and the new set", async () => {
    const { user, onChange } = await renderExpanded();
    onChange.mockClear();

    // Check prototype-build (index 3) → it joins the gated set.
    const checkboxes = screen.getAllByRole("checkbox") as HTMLInputElement[];
    await user.click(checkboxes[3]);

    const [ids, touched] = onChange.mock.calls[onChange.mock.calls.length - 1];
    expect(touched).toBe(true);
    // Reported in pipeline order: specify, plan, analyze, build.
    expect(ids).toEqual(["prototype-specify", "prototype-plan", "prototype-analyze", "prototype-build"]);
  });

  it("unchecking a default gate fires onChange(touched=true) without it", async () => {
    const { user, onChange } = await renderExpanded();
    onChange.mockClear();

    // Uncheck prototype-specify (index 0).
    const checkboxes = screen.getAllByRole("checkbox") as HTMLInputElement[];
    await user.click(checkboxes[0]);

    const [ids, touched] = onChange.mock.calls[onChange.mock.calls.length - 1];
    expect(touched).toBe(true);
    expect(ids).toEqual(["prototype-plan", "prototype-analyze"]);
  });

  it("unchecking ALL gates yields onChange([], true) — the no-gates payload", async () => {
    const { user, onChange } = await renderExpanded();
    onChange.mockClear();

    const checkboxes = screen.getAllByRole("checkbox") as HTMLInputElement[];
    await user.click(checkboxes[0]); // uncheck specify
    await user.click(checkboxes[1]); // uncheck plan
    await user.click(checkboxes[2]); // uncheck analyze

    const [ids, touched] = onChange.mock.calls[onChange.mock.calls.length - 1];
    expect(touched).toBe(true);
    expect(ids).toEqual([]);
  });
});

describe("ReviewGatesSection — edge cases", () => {
  it("renders nothing when the agent list is empty", () => {
    const { container } = render(
      <ReviewGatesSection agents={[]} onChange={vi.fn()} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("ppt pipeline starts with zero pre-checked gates", () => {
    const onChange = vi.fn();
    render(<ReviewGatesSection agents={byPipeline("ppt")} onChange={onChange} />);
    const [ids, touched] = onChange.mock.calls[onChange.mock.calls.length - 1];
    expect(ids).toEqual([]);
    expect(touched).toBe(false);
  });
});
