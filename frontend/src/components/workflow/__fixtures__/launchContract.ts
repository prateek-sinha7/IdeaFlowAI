/**
 * Launch-contract GOLDEN fixtures (plan 37-07) — the frozen snapshot of the
 * retired route-split launch flow's sessionStorage hand-off, per deliverable
 * mode. These strings are the ORACLE: they were captured from the real old
 * `prototype/templates` + `ppt/templates` pages by a transitional render-oracle
 * test (retired with those pages; preserved in git history) that rendered them
 * and asserted their output equalled these strings. They now guard the unified
 * LaunchWizard forever via the launchDraft.parity test, which asserts
 * `buildLaunchDraft` reproduces them byte-for-byte.
 *
 * DO NOT hand-edit a golden to make a test pass — a divergence here is a
 * launch-contract regression the dashboard would silently mis-read.
 */

import type { LaunchMode, LaunchDraftInputs } from "@/lib/launchDraft";
import type { DiscoveryAnswers } from "@/components/workflow/prototype/DiscoveryForm";

/** The default prototype pipeline agent lineup (AgentLibraryData, order 1..5). */
export const PROTO_AGENTS = [
  "prototype-specify",
  "prototype-plan",
  "prototype-analyze",
  "prototype-build",
  "prototype-validate",
];

/** The default ppt pipeline agent lineup (AgentLibraryData, order 1..3). */
export const PPT_AGENTS = ["od-ppt-brief-analyst", "od-ppt-composer", "od-ppt-validator"];

export interface DraftScenario {
  name: string;
  mode: LaunchMode;
  inputs: LaunchDraftInputs;
  /** Whether this scenario is exercised by the transitional render-oracle. */
  oracle: boolean;
  expected: {
    draftKey: string;
    pendingKey: string;
    draftJson: string;
  };
}

const PROTO_KEYS = { draftKey: "prototype.draft", pendingKey: "od_prototype.pending" };
const PPT_KEYS = { draftKey: "ppt.draft", pendingKey: "od_ppt.pending" };

export const DRAFT_SCENARIOS: DraftScenario[] = [
  // ── Prototype ──────────────────────────────────────────────────────────
  {
    name: "prototype · base (template + ds + brief)",
    mode: "prototype",
    oracle: true,
    inputs: {
      templateId: "kanban",
      designSystemId: "midnight",
      brief: "Build a kanban board",
      agentIds: PROTO_AGENTS,
    },
    expected: {
      ...PROTO_KEYS,
      draftJson:
        '{"templateId":"kanban","designSystemId":"midnight","brief":"Build a kanban board","agentIds":["prototype-specify","prototype-plan","prototype-analyze","prototype-build","prototype-validate"]}',
    },
  },
  {
    name: "prototype · blank canvas (no template)",
    mode: "prototype",
    oracle: true,
    inputs: {
      templateId: null,
      designSystemId: "midnight",
      brief: "Build a kanban board",
      agentIds: PROTO_AGENTS,
    },
    expected: {
      ...PROTO_KEYS,
      draftJson:
        '{"templateId":null,"designSystemId":"midnight","brief":"Build a kanban board","agentIds":["prototype-specify","prototype-plan","prototype-analyze","prototype-build","prototype-validate"]}',
    },
  },
  {
    name: "prototype · rich (custom bodies + chain + gates + levers)",
    mode: "prototype",
    oracle: true,
    inputs: {
      templateId: "ct1",
      designSystemId: "cds1",
      brief: "Rich brief",
      customDsBody: "/* custom ds */",
      customTemplateBody: "<html>custom</html>",
      sourceRunId: "run-123",
      gatesTouched: true,
      gateAgentIds: ["prototype-specify"],
      modelOverrides: { "prototype-build": "claude-sonnet" },
      selections: { "prototype-build": { retryLimit: 2 } },
      agentIds: PROTO_AGENTS,
    },
    expected: {
      ...PROTO_KEYS,
      draftJson:
        '{"templateId":"ct1","designSystemId":"cds1","brief":"Rich brief","customDsBody":"/* custom ds */","customTemplateBody":"<html>custom</html>","sourceRunId":"run-123","gateAgentIds":["prototype-specify"],"modelOverrides":{"prototype-build":"claude-sonnet"},"selections":{"prototype-build":{"retryLimit":2}},"agentIds":["prototype-specify","prototype-plan","prototype-analyze","prototype-build","prototype-validate"]}',
    },
  },
  {
    name: "prototype · gates touched but empty (no gates)",
    mode: "prototype",
    oracle: false,
    inputs: {
      templateId: "kanban",
      designSystemId: "midnight",
      brief: "No gates",
      gatesTouched: true,
      gateAgentIds: [],
      agentIds: PROTO_AGENTS,
    },
    expected: {
      ...PROTO_KEYS,
      draftJson:
        '{"templateId":"kanban","designSystemId":"midnight","brief":"No gates","gateAgentIds":[],"agentIds":["prototype-specify","prototype-plan","prototype-analyze","prototype-build","prototype-validate"]}',
    },
  },
  {
    name: "prototype · out-of-band images",
    mode: "prototype",
    oracle: false,
    inputs: {
      templateId: "kanban",
      designSystemId: "midnight",
      brief: "With image",
      images: [{ name: "shot.png", mime_type: "image/png", data: "iVBORw0KGgo=" }],
      agentIds: PROTO_AGENTS,
    },
    expected: {
      ...PROTO_KEYS,
      draftJson:
        '{"templateId":"kanban","designSystemId":"midnight","brief":"With image","images":[{"name":"shot.png","mime_type":"image/png","data":"iVBORw0KGgo="}],"agentIds":["prototype-specify","prototype-plan","prototype-analyze","prototype-build","prototype-validate"]}',
    },
  },
  // ── PPT / Deck ─────────────────────────────────────────────────────────
  {
    name: "ppt · base (ds required)",
    mode: "ppt",
    oracle: true,
    inputs: {
      templateId: "pitch",
      designSystemId: "midnight",
      brief: "Pitch deck",
      agentIds: PPT_AGENTS,
    },
    expected: {
      ...PPT_KEYS,
      draftJson:
        '{"templateId":"pitch","designSystemId":"midnight","brief":"Pitch deck","agentIds":["od-ppt-brief-analyst","od-ppt-composer","od-ppt-validator"]}',
    },
  },
  {
    name: "ppt · ds not required (designSystemId null)",
    mode: "ppt",
    oracle: true,
    inputs: {
      templateId: "onepager",
      designSystemId: null,
      brief: "Pitch deck",
      agentIds: PPT_AGENTS,
    },
    expected: {
      ...PPT_KEYS,
      draftJson:
        '{"templateId":"onepager","designSystemId":null,"brief":"Pitch deck","agentIds":["od-ppt-brief-analyst","od-ppt-composer","od-ppt-validator"]}',
    },
  },
  {
    // A built-in deck template that REQUIRES a design system (so designSystemId
    // survives) + a custom DS body + chain source + empty gate array + levers.
    // ppt writes designSystemId = dsRequired ? selectedDsId : null, so this
    // scenario deliberately uses a ds-requiring built-in (not a custom template,
    // which would force dsRequired=false → designSystemId:null).
    name: "ppt · rich (ds-requiring template + custom ds + chain + gates empty + levers)",
    mode: "ppt",
    oracle: true,
    inputs: {
      templateId: "pitch",
      designSystemId: "cds1",
      brief: "Rich deck",
      customDsBody: "/* custom ds */",
      sourceRunId: "run-9",
      gatesTouched: true,
      gateAgentIds: [],
      modelOverrides: { "od-ppt-composer": "claude-x" },
      selections: { "od-ppt-composer": { retryLimit: 3 } },
      agentIds: PPT_AGENTS,
    },
    expected: {
      ...PPT_KEYS,
      draftJson:
        '{"templateId":"pitch","designSystemId":"cds1","brief":"Rich deck","customDsBody":"/* custom ds */","sourceRunId":"run-9","gateAgentIds":[],"modelOverrides":{"od-ppt-composer":"claude-x"},"selections":{"od-ppt-composer":{"retryLimit":3}},"agentIds":["od-ppt-brief-analyst","od-ppt-composer","od-ppt-validator"]}',
    },
  },
  {
    // The ONE ppt branch that forces `customTemplateBody` present AND
    // `designSystemId:null` together: a deck CUSTOM template has no registry
    // entry, so the component's `selectedDeckTemplate` is undefined → dsRequired
    // is false → designSystemId resolves to null. Byte-derived from
    // `buildLaunchDraft` (the single source), which the 37-07 re-review confirmed
    // reproduces the retired ppt/templates flow for this case. Closes WR-06.
    name: "ppt · custom template (customTemplateBody + designSystemId null)",
    mode: "ppt",
    oracle: false,
    inputs: {
      templateId: "ct1",
      designSystemId: null,
      brief: "Custom deck",
      customTemplateBody: "<html>custom</html>",
      agentIds: PPT_AGENTS,
    },
    expected: {
      ...PPT_KEYS,
      draftJson:
        '{"templateId":"ct1","designSystemId":null,"brief":"Custom deck","customTemplateBody":"<html>custom</html>","agentIds":["od-ppt-brief-analyst","od-ppt-composer","od-ppt-validator"]}',
    },
  },
];

export interface DiscoveryScenario {
  name: string;
  answers: DiscoveryAnswers;
  expected: string | null;
}

export const DISCOVERY_SCENARIOS: DiscoveryScenario[] = [
  {
    name: "discovery · filled (style answers)",
    answers: { template: {}, surface: "Desktop web", audience: "Developers", tone: "", scale: "", constraints: "" },
    expected:
      '{"template":{},"surface":"Desktop web","audience":"Developers","tone":"","scale":"","constraints":""}',
  },
  {
    name: "discovery · empty (skip → null)",
    answers: { template: {}, surface: "", audience: "", tone: "", scale: "", constraints: "" },
    expected: null,
  },
];
