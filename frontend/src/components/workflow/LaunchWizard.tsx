"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowRight, Sparkles, ChevronDown, ChevronRight, Layers, Eye, Paperclip,
  Mic, MicOff, X, File, Settings2, Save, Image as ImageIcon, ArrowLeft, Lock,
} from "lucide-react";
import {
  getToken,
  getMe,
  extractFileText,
  createUserWorkflow,
  handleSessionExpiry,
  getWorkflowDetail,
  setWorkflowOverrideEnabled,
} from "@/lib/api";
import { agentsFromManifest } from "@/lib/manifestAgents";
import { buildLoginRedirect } from "@/lib/authRedirect";
import { routes } from "@/lib/routes";
import { agentMatchesPipelineType } from "@/lib/workflowIcons";
import { canRunPipeline, getUpgradeTier, TIER_LABELS, type Tier } from "@/lib/entitlements";
import { ATTACH_MAX_CHARS, truncateAttachmentText } from "@/lib/constants";
import {
  listDesignSystems,
  listPrototypeTemplates,
  type DesignSystemListItem,
  type PrototypeTemplate,
} from "@/lib/prototype-api";
import { listPPTTemplates, type PPTTemplate } from "@/lib/ppt-api";
import { WizardStepper } from "@/components/workflow/WizardStepper";
import { DesignSystemPicker } from "@/components/workflow/prototype/DesignSystemPicker";
import {
  DiscoveryForm,
  EMPTY_ANSWERS,
  type DiscoveryAnswers,
} from "@/components/workflow/prototype/DiscoveryForm";
import { ReviewGatesSection } from "@/components/workflow/ReviewGatesSection";
import { AgentsPopup, type SelectionsMap } from "@/components/workflow/AgentsPopup";
import { useAgentLibrary } from "@/hooks/useAgentLibrary";
import { useSpeechRecognition } from "@/hooks/useSpeechRecognition";
import { NameWorkflowModal } from "@/components/catalog/NameWorkflowModal";
import {
  buildLaunchDraft,
  buildDiscoveryValue,
  DISCOVERY_KEY,
  type LaunchMode,
} from "@/lib/launchDraft";
import type { CustomDesignSystem } from "@/components/workflow/prototype/CustomDesignSystemModal";
import type { CustomTemplate } from "@/components/workflow/prototype/CustomTemplateModal";
import type { AgentDef } from "@/types/index";
import { buildWorkflowManifest, collectAgentIds, instantiateIfTemplate, overrideDescription } from "@/store/api/userWorkflows";

/**
 * LaunchWizard (plan 37-07) — the ONE unified deliverable-launch page. It
 * replaces the two retired route-split pages (prototype/templates +
 * ppt/templates), hosting the WizardStepper chrome (Template → Design System →
 * Discovery + a Web/Deck toggle) and wrapping it with the brief, review gates,
 * agent composer, save-workflow, and launch affordances.
 *
 * SC-001 / INV-1: the page is keyed on a GENERIC `mode` value
 * ("prototype" | "ppt") — the deliverable family the Web/Deck toggle switches —
 * NEVER a per-workflow-name branch. Every mode difference is expressed as data
 * in MODE_CONFIG or the launch-contract library (buildLaunchDraft), so the
 * wizard→dashboard hand-off is byte-identical to the retired flow (proven by
 * the launch-contract parity gate).
 *
 * All colours route through the @theme token layer; NO retired palette.
 */

/** The Web/Deck stepper toggle value ↔ the deliverable mode. `ppt_v2` is a deck
 *  deliverable, so it sits under "deck" alongside `ppt`. */
const STEPPER_MODE: Record<LaunchMode, "web" | "deck"> = { prototype: "web", ppt: "deck", ppt_v2: "deck" };
/** Two deck modes share one stepper slot, so the toggle cannot recover which one
 *  from "deck" alone. `deckMode` is the family this wizard was opened for, which
 *  is what toggling web → deck must restore; without it a ppt_v2 launch would
 *  silently downgrade to ppt on a round-trip through the toggle. */
function modeFromStepper(m: "web" | "deck", deckMode: LaunchMode): LaunchMode {
  return m === "web" ? "prototype" : deckMode;
}

interface ModeConfig {
  /** AgentLibraryData `pipeline_type` for the default lineup. */
  agentPipeline: LaunchMode;
  /** `base_pipeline_type` sent to POST /api/user-workflows on Save — must be
   *  a live catalog id. `od_prototype`/`od_ppt` are retired aliases the
   *  backend no longer accepts (422 "Unsupported base_pipeline_type"). */
  savePipeline: LaunchMode;
  title: string;
  chainingTitle: string;
  eyebrow: string;
  chainingEyebrow: string;
  placeholder: string;
  briefLabel: string;
  saveTitle: string;
}

const MODE_CONFIG: Record<LaunchMode, ModeConfig> = {
  prototype: {
    agentPipeline: "prototype",
    savePipeline: "prototype",
    title: "Configure your prototype",
    chainingTitle: "Pick a template & design system",
    eyebrow: "New prototype",
    chainingEyebrow: "Chained prototype",
    placeholder:
      "e.g. A kanban board for a 5-person growth squad — backlog, doing, review, done. Show real ticket titles and assignee avatars.",
    briefLabel: "Describe what you're building",
    saveTitle: "Save prototype workflow",
  },
  ppt: {
    agentPipeline: "ppt",
    savePipeline: "ppt",
    title: "Configure your presentation",
    chainingTitle: "Pick a template",
    eyebrow: "New presentation",
    chainingEyebrow: "Chained presentation",
    placeholder:
      "e.g. A pitch deck for our Series A fundraise — $5M ask, B2B SaaS, 10 slides for investors.",
    briefLabel: "Describe your presentation",
    saveTitle: "Save presentation workflow",
  },
  // Spec 017. Same deck wizard as `ppt` — same template step, same design
  // systems — because it reuses ppt's first two agents verbatim and needs the
  // same opendesign template context they inject. Only the pipeline it launches
  // and the copy differ.
  ppt_v2: {
    agentPipeline: "ppt_v2",
    savePipeline: "ppt_v2",
    title: "Configure your presentation",
    chainingTitle: "Pick a template",
    eyebrow: "New presentation + PowerPoint",
    chainingEyebrow: "Chained presentation",
    placeholder:
      "e.g. A pitch deck for our Series A fundraise — $5M ask, B2B SaaS, 10 slides for investors.",
    briefLabel: "Describe your presentation",
    saveTitle: "Save presentation workflow",
  },
};

/** Copy for the chain context/banner, keyed on the source pipeline (data map). */
const CHAIN_SOURCE_LABEL: Record<string, string> = {
  ppt: "Presentation", ppt_revision: "Presentation",
  prototype: "Prototype", prototype_revision: "Prototype",
  user_stories: "User Stories", user_stories_revision: "User Stories",
  app_builder: "App Builder", app_builder_revision: "App Builder",
};

const defaultAgentsFor = (libraryAgents: AgentDef[], mode: LaunchMode): AgentDef[] =>
  libraryAgents.filter((a) => agentMatchesPipelineType(a.pipeline_type, MODE_CONFIG[mode].agentPipeline)).sort(
    (a, b) => a.order - b.order,
  );

export interface LaunchWizardProps {
  /** The deliverable family to launch, from the generic `?mode=` route param. */
  initialMode: LaunchMode;
}

export function LaunchWizard({ initialMode }: LaunchWizardProps) {
  const router = useRouter();
  const { libraryAgents } = useAgentLibrary();

  const [authChecked, setAuthChecked] = useState(false);
  // ISS-321: the signed-in tier, for the entitlement gate below. `null` until
  // the profile resolves (or if it fails) — the wizard is never locked on a
  // tier it does not know, so a profile blip cannot brick an entitled user.
  const [tier, setTier] = useState<Tier | null>(null);
  const [mode, setMode] = useState<LaunchMode>(initialMode);
  // Which deck deliverable the Deck half of the toggle means for THIS wizard —
  // see modeFromStepper. Fixed at open; the toggle switches families, not
  // deliverables within a family.
  const deckMode: LaunchMode = initialMode === "ppt_v2" ? "ppt_v2" : "ppt";
  // Chrome (title/eyebrow/brief label/placeholder/save-modal title) MUST track the
  // LIVE mode, not the immutable initialMode — the Web/Deck toggle switches families
  // in-page, and freezing chrome to initialMode mislabels a deck as a prototype.
  const cfg = MODE_CONFIG[mode];

  // ── Template registries (both families fetched so the toggle just swaps). ──
  const [webTemplates, setWebTemplates] = useState<PrototypeTemplate[]>([]);
  const [deckTemplates, setDeckTemplates] = useState<PPTTemplate[]>([]);
  const [systems, setSystems] = useState<DesignSystemListItem[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

  // ── Selection state. Template is per-mode (the toggle preserves nothing:
  //    switching families is a fresh deliverable choice), so it resets on
  //    switch alongside the agent lineup + levers. DS/brief/files/images/
  //    discovery are shared inputs that carry across a toggle. ──
  const [selectedTemplateId, setSelectedTemplateId] = useState<string | null>(null);
  const [customTemplateBody, setCustomTemplateBody] = useState<string | null>(null);
  const [selectedDsId, setSelectedDsId] = useState<string | null>(null);
  const [customDsBody, setCustomDsBody] = useState<string | null>(null);
  const [brief, setBrief] = useState("");
  const [discoveryAnswers, setDiscoveryAnswers] = useState<DiscoveryAnswers>(EMPTY_ANSWERS);

  const [attachedFiles, setAttachedFiles] = useState<{ name: string; size: string }[]>([]);
  // KAN-91: file content stored separately so the textarea stays clean.
  const [attachedFileContents, setAttachedFileContents] = useState<{ name: string; content: string }[]>([]);
  // Image-input Wave 2 (D3): images ride OUT-OF-BAND via the draft `images`
  // field — SEPARATE from attachedFileContents (which is inlined into the brief).
  const [attachedImages, setAttachedImages] = useState<{ name: string; mime_type: string; data: string }[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const preSpeechTextRef = useRef("");
  const { isListening, transcript, startListening, stopListening, isSupported: speechSupported } =
    useSpeechRecognition();

  const [chainFrom, setChainFrom] = useState<string | null>(null);
  const [chainContextBlock, setChainContextBlock] = useState<string | null>(null);
  const [contextExpanded, setContextExpanded] = useState(false);
  const [showAgents, setShowAgents] = useState(false);

  const [pipelineAgents, setPipelineAgents] = useState<AgentDef[]>(() => defaultAgentsFor(libraryAgents, initialMode));

  // ── The compiled plan's steps, for roster completion (spec 017) ─────────────
  // `defaultAgentsFor` filters the agent library by each AGENT.md's single
  // `pipeline_type` field. That is a complete roster only while every step of a
  // workflow declares that workflow. `ppt_v2` REUSES ppt's first two steps, so
  // the library yields 2 of its 4 — a partial lineup, in the one place the user
  // reads to learn what will run. The manifest is the authority; when it lists
  // more steps than the library found, it wins.
  const [planAgents, setPlanAgents] = useState<AgentDef[] | null>(null);

  // ── Spec 016: this user's saved override of the built-in ────────────────────
  // OVERLAY, never replace. `pipelineAgents`'s initial value above stays the
  // library roster: swapping its source wholesale would change this screen for
  // every user, override or not, and the two sources are not guaranteed to agree
  // (the library sorts by AGENT.md `order`; a manifest is the compiled sequence).
  // The effect below returns early unless an ENABLED override exists, so a user
  // without one sees a byte-identical screen having issued one extra GET.
  const [overrideInfo, setOverrideInfo] = useState<{
    id: string;
    enabled: boolean;
  } | null>(null);
  // The override's rows + declared gates, fetched once and held so toggling the
  // checkbox is instant and does not re-hit the API.
  const [overrideAgents, setOverrideAgents] = useState<AgentDef[] | null>(null);
  const [overrideSelections, setOverrideSelections] = useState<
    Record<string, Record<string, unknown>> | undefined
  >(undefined);
  const [showOverride, setShowOverride] = useState(false);
  // The built-in's DECLARED run config, so the Advanced rail shows what this
  // workflow actually does instead of CanvasView's blank-canvas defaults.
  // Read-only — no onRunConfigChange is forwarded, so nothing here is editable
  // or sent; it exists purely so the panel stops misreporting.
  const [declaredRunConfig, setDeclaredRunConfig] = useState<
    import("@/types/index").WorkflowRunConfig | undefined
  >(undefined);

  const selectionsRef = useRef<Record<string, Record<string, unknown>>>({});
  // ISS-247 — the LIVE map the Advanced modal renders from. AgentsPopup used to
  // own this privately (a mount-once seed off `selectionsRef`), so a gate checked
  // in the Review-gates checklist on this page was invisible inside the modal.
  // Every writer below goes through `handleSelectionsChange`, which keeps the ref
  // (read by launch + save) and this state in step.
  const [liveSelections, setLiveSelections] = useState<SelectionsMap>({});
  // The ONE writer of that pair — every restore/reset below routes through it so
  // the ref and the rendered map can never drift apart (ISS-247).
  const handleSelectionsChange = useCallback((s: SelectionsMap) => {
    selectionsRef.current = s;
    setLiveSelections(s);
  }, []);
  // `touched: true` from the start is FIX-323: `gate_agent_ids` is ALWAYS sent, so
  // an empty selection reads as an explicit "no gates" rather than an absent field
  // the backend would fill from its own defaults. ISS-247 changed the live map, not
  // this contract — do not revert it to false.
  const gateSelectionRef = useRef<{ ids: string[]; touched: boolean }>({ ids: [], touched: true });

  // Save-workflow state.
  const [showSaveModal, setShowSaveModal] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [savedConfirm, setSavedConfirm] = useState(false);
  // ISS-167: the saved row's identity, restored from the draft when this wizard
  // was opened from an existing saved workflow — Save then updates it in place
  // instead of always creating a new row + asking for a name.
  const [userWorkflowId, setUserWorkflowId] = useState<string | undefined>(undefined);
  const [savedName, setSavedName] = useState<string | undefined>(undefined);
  const [savedDescription, setSavedDescription] = useState<string | undefined>(undefined);

  const isChaining = Boolean(chainFrom);

  // Auth + chain pickup (mirrors the retired pages).
  useEffect(() => {
    const token = getToken();
    if (!token) { router.replace(buildLoginRedirect()); return; }
    setAuthChecked(true);
    // ISS-321: the wizard is reached from two separate routes (the `[...view]`
    // catch-all's wizardMode branch and the standalone `/workflow/create`
    // page), so it owns the tier lookup rather than taking it as a prop from
    // one of them. Non-fatal: a failure leaves `tier` null and gates nothing.
    getMe(token).then((u) => setTier(u.tier)).catch(() => {});
    const from = sessionStorage.getItem("chain.from");
    if (from) {
      setChainFrom(from);
      sessionStorage.removeItem("chain.from");
    }
    const ctx = sessionStorage.getItem("chain.context_block");
    if (ctx) setChainContextBlock(ctx);
  }, [router]);

  // Restore the draft the dashboard/Saved-workflow hand-off wrote for THIS mode,
  // then clear it (FIX-005: one-shot, so a fresh open never pre-fills stale data).
  // T29 / cold-mount fix: libraryAgents is included in the dependency array so the
  // effect re-runs when agents load, allowing the agentIds→agent mapping to succeed
  // (line 229 uses libraryAgents; without it, a cold mount of /workflows/{id}/run
  // with agents would fail to restore them if libraryAgents hadn't loaded yet).
  useEffect(() => {
    if (!authChecked) return;
    try {
      const chainBrief = sessionStorage.getItem("chain.brief");
      if (chainBrief) {
        setBrief(chainBrief);
        sessionStorage.removeItem("chain.brief");
        sessionStorage.removeItem("chain.from");
        return;
      }
      const draftKey = initialMode === "prototype" ? "prototype.draft" : "ppt.draft";
      const raw = sessionStorage.getItem(draftKey);
      if (!raw) return;
      const d = JSON.parse(raw) as {
        templateId?: string; designSystemId?: string | null; brief?: string;
        customDsBody?: string; customTemplateBody?: string;
        agentIds?: string[]; gateAgentIds?: string[];
        selections?: Record<string, Record<string, unknown>>;
        id?: string; name?: string; description?: string;
      };
      if (d.templateId) setSelectedTemplateId(d.templateId);
      if (d.designSystemId) setSelectedDsId(d.designSystemId);
      if (d.brief) setBrief(d.brief);
      if (d.customDsBody) setCustomDsBody(d.customDsBody);
      if (d.customTemplateBody) setCustomTemplateBody(d.customTemplateBody);
      if (d.agentIds && d.agentIds.length > 0 && libraryAgents.length > 0) {
        const restored = d.agentIds
          .map((id) => libraryAgents.find((a) => a.id === id))
          .filter(Boolean) as AgentDef[];
        if (restored.length > 0) setPipelineAgents(restored);
      }
      if (d.selections) handleSelectionsChange(d.selections);
      if (d.gateAgentIds !== undefined) gateSelectionRef.current = { ids: d.gateAgentIds, touched: true };
      // ISS-167: restored BEFORE the AgentsPopup below (keyed on userWorkflowId)
      // remounts, so its initialSelections seed reads the now-populated ref
      // instead of the empty one from its first mount.
      if (d.id) setUserWorkflowId(d.id);
      if (d.name) setSavedName(d.name);
      if (d.description) setSavedDescription(d.description);
      // Clear draft only if we've successfully processed agents (when libraryAgents is available),
      // or if there are no agents to restore. This allows the effect to re-run when libraryAgents
      // loads if it wasn't available on the first run.
      if (!d.agentIds || d.agentIds.length === 0 || libraryAgents.length > 0) {
        sessionStorage.removeItem(draftKey);
      }
    } catch { /* ignore malformed session data */ }
  }, [authChecked, initialMode, libraryAgents, handleSelectionsChange]);

  // `pipelineAgents`'s initial value (below) is computed once at mount from
  // `libraryAgents` — Redux state populated by an async fetch on sign-in. If
  // that fetch hasn't resolved yet when this component mounts, the lazy
  // initializer captures an empty array, and a plain fresh open with no draft
  // to restore (the effect above only re-populates agents when there IS a
  // draft) never gets another chance — "Advanced" is stuck at 0 agents.
  // Re-derive once real agents arrive, but only while pipelineAgents is still
  // that empty race-loss state, so this never overwrites a user's deliberate
  // removal of every agent.
  // ISS-228: the "still empty" test MUST be a functional updater. This effect
  // shares the `libraryAgents` dependency with the draft-restore effect above,
  // so both run in the same passive-effect flush; reading `pipelineAgents` from
  // the render closure would see the value from BEFORE that sibling's
  // setPipelineAgents(restored) — always 0 on a cold mount — and this effect,
  // declared last, would enqueue the generic per-pipeline roster over the saved
  // workflow's real one. `prev` is resolved against the queued update instead,
  // so a restored roster is visible here and left alone.
  useEffect(() => {
    if (libraryAgents.length === 0) return;
    setPipelineAgents((prev) =>
      prev.length > 0 ? prev : defaultAgentsFor(libraryAgents, mode),
    );
  }, [libraryAgents, mode]);

  // Complete a partial library roster from the compiled plan (see `planAgents`).
  // Guarded on "the plan lists MORE steps than we are showing" so a workflow the
  // library covers fully, and any lineup the user has edited or added to, is
  // left exactly as it is. Plan rows are hydrated from the library where it has
  // the agent, so the shared steps keep their real icon and duration.
  useEffect(() => {
    if (!planAgents) return;
    setPipelineAgents((prev) => {
      if (planAgents.length <= prev.length) return prev;
      const byId = new Map(libraryAgents.map((a) => [a.id, a]));
      return planAgents.map((step) => byId.get(step.id) ?? step);
    });
  }, [planAgents, libraryAgents]);

  // ── Spec 016: fetch this user's override of the built-in, if any ────────────
  // Additive. `is_overridden` is false for every user who has never saved one,
  // so this returns before touching any state and the screen is unchanged.
  useEffect(() => {
    if (!authChecked) return;
    const token = getToken();
    if (!token) return;
    const pipeline = MODE_CONFIG[mode].agentPipeline;
    let cancelled = false;
    // Reset first: switching Web <-> Deck changes which built-in we are asking
    // about, and a stale override from the other family must not survive.
    setOverrideInfo(null);
    setPlanAgents(null);
    setOverrideAgents(null);
    setOverrideSelections(undefined);
    setShowOverride(false);

    setDeclaredRunConfig(undefined);

    getWorkflowDetail(token, pipeline)
      .then((detail) => {
        if (cancelled) return;
        // Declared config first — it is true whether or not an override exists,
        // and the override branch below returns early when there is none.
        setDeclaredRunConfig({
          deliverable: {
            strategy: detail.deliverable?.strategy ?? "streamed_text",
            name: detail.deliverable?.name ?? "output.md",
          },
          // The API types these as plain strings; the composer's config model
          // narrows them. Both are closed sets server-side, so a mismatch means
          // a new manifest value the composer does not model yet — fall back to
          // the safe reading rather than rendering something invented.
          planner: detail.planner === "run" ? "run" : "skip",
          clarify: {
            mode: detail.clarify_mode === "auto" ? "auto" : "skip",
            defaults: detail.clarify_defaults ?? [],
          },
        });
        setPlanAgents(agentsFromManifest(detail, pipeline).agents);
        // ISS-429 (Mechanism A): on a plain /create/ppt or /create/prototype load
        // (no override active), liveSelections was always initialised to {} and
        // only handleSelectionsChange from the override/draft branches ever wrote
        // it — so a manifest-declared before-human gate never reached the
        // ReviewGatesSection's seed. FIX-377 fixed IdeaInputPage.tsx via the
        // selections prop on ReviewGatesSection; this is the matching fix for
        // LaunchWizard: extract the manifest's declared selections and seed the
        // live map ONLY when no override is active (the override branch below
        // overwrites it anyway), preserving display-only semantics (INV-3 —
        // `selectionsRef` is not touched here, so an untouched run still omits
        // `selections` from the launch payload).
        const planProj = agentsFromManifest(detail, pipeline);
        setPlanAgents(planProj.agents);
        if (!detail.has_override || !detail.is_overridden) {
          if (planProj.selections && Object.keys(planProj.selections).length > 0) {
            setLiveSelections(planProj.selections);
          }
        }
        if (!detail.has_override || !detail.override_id) return;
        setOverrideInfo({ id: detail.override_id, enabled: !!detail.is_overridden });
        // `detail` already carries the override's steps whenever it is enabled,
        // so no second request. When it is saved-but-off the payload is the
        // system version; the rows are fetched on demand when the box is ticked.
        if (detail.is_overridden) {
          const proj = agentsFromManifest(detail, pipeline);
          setOverrideAgents(proj.agents);
          setOverrideSelections(proj.selections);
          setShowOverride(true);
          if (proj.agents.length > 0) setPipelineAgents(proj.agents);
          if (proj.selections) handleSelectionsChange(proj.selections);
        }
      })
      .catch(() => {
        // A workflow with no manifest, or a transient failure. The library
        // roster is already rendered — degrade to "no override", never blank
        // the screen over an optional enhancement.
      });
    return () => { cancelled = true; };
  }, [authChecked, mode, handleSelectionsChange]);

  /** Flip between the override's steps and the system ones (spec 016 T8). */
  const handleToggleOverride = useCallback(
    async (next: boolean) => {
      if (!overrideInfo) return;
      const token = getToken();
      if (!token) return;
      setShowOverride(next);

      if (!next) {
        // Back to the system version — the library roster, exactly as a user
        // with no override sees it.
        setPipelineAgents(defaultAgentsFor(libraryAgents, mode));
        handleSelectionsChange({});
      } else if (overrideAgents) {
        setPipelineAgents(overrideAgents);
        handleSelectionsChange(overrideSelections ?? {});
      } else {
        // Saved-but-off at mount, so the rows were never fetched. Enable the row
        // first, then read back the payload the server now serves as overridden.
        try {
          await setWorkflowOverrideEnabled(token, overrideInfo.id, true);
          const detail = await getWorkflowDetail(token, MODE_CONFIG[mode].agentPipeline);
          const proj = agentsFromManifest(detail, MODE_CONFIG[mode].agentPipeline);
          setOverrideAgents(proj.agents);
          setOverrideSelections(proj.selections);
          if (proj.agents.length > 0) setPipelineAgents(proj.agents);
          handleSelectionsChange(proj.selections ?? {});
          setOverrideInfo({ ...overrideInfo, enabled: true });
          return;
        } catch {
          setShowOverride(false);
          return;
        }
      }

      // Persist the choice so the detail page and the RUN agree with what is on
      // screen — a view-only toggle would let the page show one plan while the
      // launch executed the other.
      try {
        await setWorkflowOverrideEnabled(token, overrideInfo.id, next);
        setOverrideInfo({ ...overrideInfo, enabled: next });
      } catch {
        /* the roster already reflects the choice; the flag retries on next toggle */
      }
    },
    [overrideInfo, overrideAgents, overrideSelections, libraryAgents, mode, handleSelectionsChange],
  );

  // Load both template families + the design-system registry once authed.
  useEffect(() => {
    if (!authChecked) return;
    const token = getToken();
    if (!token) return;
    let cancelled = false;

    listPrototypeTemplates(token)
      .then((t) => { if (!cancelled) setWebTemplates(t); })
      .catch((err: Error) => {
        if (cancelled) return;
        if (err.message.startsWith("401")) { handleSessionExpiry(); return; }
        setLoadError(err.message);
      });
    listPPTTemplates(token)
      .then((t) => { if (!cancelled) setDeckTemplates(t); })
      .catch((err: Error) => {
        if (cancelled) return;
        if (err.message.startsWith("401")) { handleSessionExpiry(); }
      });
    listDesignSystems(token)
      .then((s) => {
        if (!cancelled) {
          setSystems(s);
          // FIX-103: Auto-select "Design System Inspired by Apple" on a fresh
          // prototype launch. Only fires when no DS has been selected yet (null)
          // so draft-restored selections and user choices are never overwritten.
          // Gracefully skips if "apple" is not in the loaded list.
          setSelectedDsId((prev) => {
            if (prev !== null) return prev; // preserve draft / user selection
            if (mode !== "prototype") return prev;
            return s.some((ds) => ds.id === "apple") ? "apple" : prev;
          });
        }
      })
      .catch(() => { /* non-fatal — the picker stays empty */ });

    return () => { cancelled = true; };
  }, [authChecked, router]);

  // Mirror speech transcript into the brief textarea (same pattern as the pages).
  useEffect(() => {
    if (transcript) {
      setBrief(preSpeechTextRef.current + (preSpeechTextRef.current ? " " : "") + transcript);
    }
  }, [transcript]);

  const selectedDeckTemplate = useMemo(
    () => deckTemplates.find((t) => t.id === selectedTemplateId) ?? null,
    [deckTemplates, selectedTemplateId],
  );
  const selectedWebTemplate = useMemo(
    () => webTemplates.find((t) => t.id === selectedTemplateId) ?? null,
    [webTemplates, selectedTemplateId],
  );
  // ppt design system is only required for templates that declare it.
  // Spec 017: every branch below asks "is this a DECK deliverable", which is now
  // two modes, not one. Branching on `mode === "ppt"` here is what would have
  // hidden the template step — and with it the design choice — from ppt_v2.
  const isDeck = STEPPER_MODE[mode] === "deck";
  const dsRequired = isDeck && selectedDeckTemplate?.design_system?.requires === true;
  const dsVisible = mode === "prototype" || dsRequired;

  const examplePrompt =
    mode === "prototype" ? selectedWebTemplate?.example_prompt : selectedDeckTemplate?.example_prompt;

  // Optional-agent budget (defaults are free; up to 5 extra), per active lineup.
  const defaultAgentIds = useMemo(
    () => new Set(defaultAgentsFor(libraryAgents, mode).map((a) => a.id)),
    [libraryAgents, mode],
  );
  const optionalAgentCount = pipelineAgents.filter((a) => !defaultAgentIds.has(a.id)).length;
  const canAddMore = optionalAgentCount < 5;

  const handleModeChange = useCallback((next: "web" | "deck") => {
    const nextMode = modeFromStepper(next, deckMode);
    setMode(nextMode);
    // Switching deliverable family is a fresh choice: reset the family-specific
    // selection + lineup + levers; shared inputs (brief/DS/files/images) persist.
    setSelectedTemplateId(null);
    setCustomTemplateBody(null);
    setPipelineAgents(defaultAgentsFor(libraryAgents, nextMode));
    handleSelectionsChange({});
    gateSelectionRef.current = { ids: [], touched: true };
  }, [libraryAgents, deckMode, handleSelectionsChange]);

  const handleAddAgent = useCallback((agent: AgentDef, insertBeforeId?: string) => {
    setPipelineAgents((prev) => {
      // Reusable blank template — mint a fresh instance id per add (R-03).
      const node = instantiateIfTemplate(agent, collectAgentIds(prev));
      if (prev.find((a) => a.id === node.id)) return prev;
      if (prev.filter((a) => !defaultAgentIds.has(a.id)).length >= 5) return prev;
      // Land the new node where the user clicked. `insertBeforeId` names the
      // agent it should go IN FRONT OF, so index 0 prepends — which is the whole
      // point of the canvas's head "+".
      //
      // This used to be `prev.length - 1` unconditionally: every add landed
      // second-to-last regardless of which "+" was clicked, so prepending was
      // impossible even once the affordance existed.
      const at = insertBeforeId ? prev.findIndex((a) => a.id === insertBeforeId) : -1;
      const insertIdx = at >= 0 ? at : prev.length;
      const updated = [...prev];
      updated.splice(insertIdx, 0, { ...node, order: insertIdx + 1 });
      // Keep `order` contiguous after a splice — it drives the display sequence.
      return updated.map((a, i) => ({ ...a, order: i + 1 }));
    });
  }, [defaultAgentIds]);

  const handleRemoveAgent = useCallback((agentId: string) => {
    setPipelineAgents((prev) => prev.filter((a) => a.id !== agentId));
  }, []);

  const handleReorderAgents = useCallback((reordered: AgentDef[]) => {
    setPipelineAgents(reordered);
  }, []);

  const handleGatesChange = useCallback((ids: string[], touched: boolean) => {
    gateSelectionRef.current = { ids, touched };
  }, []);

  const handleSelectTemplate = useCallback((id: string | null) => {
    setSelectedTemplateId(id);
    setCustomTemplateBody(null);
  }, []);
  const handleSelectCustomTemplate = useCallback((ct: CustomTemplate | null) => {
    if (ct) { setSelectedTemplateId(ct.id); setCustomTemplateBody(ct.body); }
    else { setSelectedTemplateId(null); setCustomTemplateBody(null); }
  }, []);
  const handleSelectBuiltInDs = useCallback((id: string | null) => {
    setSelectedDsId(id);
    setCustomDsBody(null);
  }, []);
  const handleSelectCustomDs = useCallback((ds: CustomDesignSystem | null) => {
    if (ds) { setSelectedDsId(ds.id); setCustomDsBody(ds.body); }
    else { setCustomDsBody(null); }
  }, []);

  const removeFile = useCallback((idx: number) => {
    setAttachedFiles((prev) => {
      const removedName = prev[idx]?.name;
      if (removedName) setAttachedFileContents((c) => c.filter((f) => f.name !== removedName));
      return prev.filter((_, i) => i !== idx);
    });
  }, []);

  const onFilesPicked = useCallback((files: FileList) => {
    Array.from(files).forEach((f) => {
      const isImageFile =
        ["image/png", "image/jpeg", "image/webp", "image/gif"].includes(f.type) ||
        /\.(png|jpe?g|webp|gif)$/i.test(f.name);
      if (isImageFile) {
        const reader = new FileReader();
        reader.onload = (ev) => {
          const result = (ev.target?.result as string) ?? "";
          const rawBase64 = result.replace(/^data:[^;]+;base64,/, "");
          setAttachedImages((p) => [...p, { name: f.name, mime_type: f.type || "image/png", data: rawBase64 }]);
        };
        reader.readAsDataURL(f);
        return;
      }
      const meta = {
        name: f.name,
        size: f.size < 1024 ? `${f.size}B` : f.size < 1048576 ? `${(f.size / 1024).toFixed(1)}KB` : `${(f.size / 1048576).toFixed(1)}MB`,
      };
      setAttachedFiles((p) => [...p, meta]);
      const isTextFile = /\.(txt|md|json|csv)$/i.test(f.name);
      const isBinaryFile = /\.(pdf|docx|pptx)$/i.test(f.name);
      if (isTextFile) {
        const reader = new FileReader();
        reader.onload = (ev) => {
          const content = (ev.target?.result as string) ?? "";
          // ISS-423: replicate FIX-374 — the binary branch already appended a
          // visible truncation note; the text branch silently sliced with no
          // indication. Use the same shared truncateAttachmentText helper so
          // both branches are consistent (one guard, no forked logic).
          setAttachedFileContents((p) => [...p, { name: f.name, content: truncateAttachmentText(content) }]);
        };
        reader.readAsText(f);
      } else if (isBinaryFile) {
        const jwt = getToken();
        if (jwt) {
          extractFileText(jwt, f)
            .then((res) => {
              const truncNote = res.truncated ? `\n[Content truncated to ${ATTACH_MAX_CHARS.toLocaleString()} chars]` : "";
              setAttachedFileContents((p) => [...p, { name: res.filename, content: `${res.text}${truncNote}` }]);
            })
            .catch(() => {
              setAttachedFileContents((p) => [...p, { name: f.name, content: "[could not extract text]" }]);
            });
        } else {
          setAttachedFileContents((p) => [...p, { name: f.name, content: "" }]);
        }
      }
    });
  }, []);

  // ISS-155: validate what `handleLaunch` ACTUALLY consumes, not a proxy for it.
  // The previous form was `isChaining || brief.trim()` — chaining WAIVED the brief
  // on the assumption a chain context block would stand in for it, but nothing ever
  // checked that the block exists. `DashboardLayout` swallows a failed
  // `getChainContext` as non-fatal and (FIX-217) now clears `chain.context_block`
  // up front, so "chaining with no context block" is reachable — and `handleLaunch`
  // then falls through to `brief.trim()`, the empty string. Requiring the union of
  // the two things `handleLaunch` reads keeps dev's UX goal (no brief needed when
  // chaining WORKS) while closing the briefless launch.
  const hasBuildInput = Boolean(brief.trim() || chainContextBlock?.trim());

  const canContinue = useMemo(() => {
    if (mode === "prototype") {
      // KAN-87: template optional; DS required (color tokens).
      return Boolean(selectedDsId && hasBuildInput);
    }
    // ppt: template required; DS only when the template declares it.
    return Boolean(selectedTemplateId && hasBuildInput && (!dsRequired || selectedDsId));
  }, [mode, selectedDsId, selectedTemplateId, dsRequired, hasBuildInput]);

  // ISS-321: the deliverable this wizard launches, gated on the same
  // `canRunPipeline` the dashboard catalog card uses (HomeLaunchGrid) and the
  // backend enforces at run creation (`_require_tier_entitlement`). Without it
  // an unentitled tier reached a submit-ready Continue via a direct URL, the
  // one surface the locked catalog card never covers.
  const launchPipeline = MODE_CONFIG[mode].savePipeline;
  const locked = tier !== null && !canRunPipeline(tier, launchPipeline);
  const upgradeTo = tier !== null ? getUpgradeTier(tier, launchPipeline) : null;

  const handleSaveWorkflow = useCallback(async (name: string, description: string) => {
    setShowSaveModal(false);
    setSaveError(null);
    const jwt = getToken();
    if (!jwt) { setSaveError("Not authenticated."); return; }
    const sel = selectionsRef.current;
    const { ids: gateAgentIds, touched: gatesTouched } = gateSelectionRef.current;
    const wizardConfig: Record<string, unknown> = {
      templateId: selectedTemplateId,
      designSystemId: isDeck ? (dsRequired ? selectedDsId : null) : selectedDsId,
      brief,
      ...(gatesTouched ? { gateAgentIds } : {}),
      ...(customDsBody ? { customDsBody } : {}),
      ...(customTemplateBody ? { customTemplateBody } : {}),
    };
    try {
      // Reverted to always-create (not routed through saveUserWorkflow /
      // userWorkflowId) — unconfirmed whether this page-level button should
      // ever update an existing row in place; AgentsPopup's own footer save
      // button is the one confirmed to need that (see AgentsPopup.tsx).
      await createUserWorkflow(jwt, {
        name,
        description: description || undefined,
        base_pipeline_type: MODE_CONFIG[mode].savePipeline,
        agent_ids: pipelineAgents.map((a) => a.id),
        selections: { ...sel, _wizard: wizardConfig },
      });
      setSavedConfirm(true);
      setTimeout(() => setSavedConfirm(false), 2500);
    } catch (e) {
      setSaveError((e as Error)?.message ?? "Failed to save workflow.");
    }
  }, [mode, isDeck, selectedTemplateId, selectedDsId, dsRequired, brief, customDsBody, customTemplateBody, pipelineAgents]);

  /**
   * Save the current lineup as THIS USER'S version of the built-in (spec 016).
   *
   * Distinct from "Save workflow" above, which creates a separate saved
   * workflow and leaves the built-in alone. This one binds to the built-in via
   * `overrides_pipeline_type`, and the server UPSERTS on it — so saving twice
   * updates the same row rather than 409ing on the name.
   *
   * Sends `manifest`, never `selections`: the override resolve reads
   * `manifest_json["steps"]`, and a selections map has no steps in it, so a
   * selections-shaped save would store a row that silently never applies. The
   * two fields are mutually exclusive server-side (422), which is why this is a
   * separate call rather than an extra field on the one above.
   */
  const handleSaveAsOverride = useCallback(async () => {
    setSaveError(null);
    const jwt = getToken();
    if (!jwt) { setSaveError("Not authenticated."); return; }
    const pipeline = MODE_CONFIG[mode].savePipeline;
    try {
      const saved = await createUserWorkflow(jwt, {
        name: `My ${cfg.eyebrow.replace(/^New /, "")}`,
        // ISS-226/ISS-279 — was a hardcoded literal, so the saved row was
        // byte-identical no matter what was on screen. `handleLaunch` below
        // reads exactly these three pieces of state for the same click.
        description: overrideDescription({
          brief,
          templateId: selectedTemplateId,
          designSystemId: isDeck ? (dsRequired ? selectedDsId : null) : selectedDsId,
        }),
        base_pipeline_type: pipeline,
        agent_ids: pipelineAgents.map((a) => a.id),
        manifest: buildWorkflowManifest(
          pipelineAgents,
          undefined,
          selectionsRef.current,
        ) as unknown as Record<string, unknown>,
        overrides_pipeline_type: pipeline,
      });
      setOverrideInfo({ id: saved.id, enabled: true });
      setOverrideAgents(pipelineAgents);
      setOverrideSelections(selectionsRef.current);
      setShowOverride(true);
      setSavedConfirm(true);
      setTimeout(() => setSavedConfirm(false), 2500);
    } catch (e) {
      setSaveError((e as Error)?.message ?? "Failed to save your version.");
    }
  }, [mode, cfg.eyebrow, pipelineAgents, brief, selectedTemplateId, selectedDsId, isDeck, dsRequired]);

  const handleLaunch = useCallback(() => {
    if (!canContinue || locked) return;
    const sourceRunId = isChaining ? (sessionStorage.getItem("chain.source_run_id") ?? undefined) : undefined;
    sessionStorage.removeItem("chain.source_run_id");
    const contextBlock = sessionStorage.getItem("chain.context_block") ?? undefined;
    sessionStorage.removeItem("chain.context_block");

    let finalBrief: string;
    if (isChaining && contextBlock) finalBrief = contextBlock;
    else if (contextBlock && brief.trim()) finalBrief = `${brief.trim()}\n\n${contextBlock}`;
    else finalBrief = brief.trim();

    const fileBlocks = attachedFileContents
      .map((f) => `\n\n=== Attached: ${f.name} ===\n${f.content}\n=== End: ${f.name} ===`)
      .join("");
    if (fileBlocks) finalBrief = `${finalBrief}${fileBlocks}`;

    const { ids: gateAgentIds, touched: gatesTouched } = gateSelectionRef.current;
    const designSystemId = isDeck ? (dsRequired ? selectedDsId : null) : selectedDsId;

    const draft = buildLaunchDraft(mode, {
      templateId: selectedTemplateId,
      designSystemId,
      brief: finalBrief,
      customDsBody,
      customTemplateBody,
      sourceRunId,
      gateAgentIds,
      gatesTouched,
      selections: selectionsRef.current,
      images: attachedImages,
      agentIds: pipelineAgents.map((a) => a.id),
    });

    sessionStorage.setItem(draft.draftKey, draft.draftJson);
    // Prototype discovery hand-off — write the answers, or clear the key so no
    // stale answers leak; ppt has no discovery step.
    if (mode === "prototype") {
      const discovery = buildDiscoveryValue(discoveryAnswers);
      if (discovery) sessionStorage.setItem(DISCOVERY_KEY, discovery);
      else sessionStorage.removeItem(DISCOVERY_KEY);
    }
    sessionStorage.setItem(draft.pendingKey, "true");
    router.push(routes.home());
  }, [
    canContinue, locked, mode, isChaining, brief, attachedFileContents, attachedImages,
    dsRequired, isDeck, selectedDsId, selectedTemplateId, customDsBody, customTemplateBody,
    discoveryAnswers, pipelineAgents, router,
  ]);

  if (!authChecked) {
    return (
      <div className="flex h-screen items-center justify-center bg-surface-paper">
        <div className="text-[13px] text-ink-500">Loading…</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-surface-paper">
      <header className="sticky top-0 z-20 border-b border-line-border bg-surface-paper/95 backdrop-blur">
        <div className="mx-auto flex max-w-5xl items-center gap-3 px-6 py-3.5">
          <button
            type="button"
            onClick={() => router.push(routes.home())}
            aria-label="Back to dashboard"
            className="flex items-center justify-center rounded-[var(--radius-button)] p-1.5 text-ink-500 transition-colors hover:bg-surface-white hover:text-ink-900"
          >
            <ArrowLeft className="h-4 w-4" />
          </button>
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-ink-400">
              {isChaining ? cfg.chainingEyebrow : cfg.eyebrow}
            </p>
            {/* ISS-384: savedName restored into state at line 313 was only ever
                passed to the closed AgentsPopup modal — the header always rendered
                cfg.title, so a saved workflow's launch panel was visually
                indistinguishable from a brand-new one. Render the saved name when
                present, with cfg.title as the fallback for a plain new-workflow open. */}
            <h1 className="font-serif text-[15px] font-normal italic text-ink-900">
              {savedName ?? (isChaining ? cfg.chainingTitle : cfg.title)}
            </h1>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-5xl space-y-8 px-6 py-8 pb-16">
        {/* Chain context panel — expandable preview of the upstream output. */}
        {chainFrom && chainContextBlock && (
          <div className="overflow-hidden rounded-[var(--radius-card)] border border-[var(--status-done-border)] bg-[var(--status-done-fill)]">
            <button
              type="button"
              onClick={() => setContextExpanded((v) => !v)}
              aria-expanded={contextExpanded}
              className="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-[var(--status-done-fill)]"
            >
              <div className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-[var(--radius-button)] bg-surface-white">
                <Layers className="h-3.5 w-3.5 text-status-done" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-[12px] font-semibold text-status-done">Context from previous pipeline</p>
                <p className="truncate text-[10px] text-status-done/80">
                  {CHAIN_SOURCE_LABEL[chainFrom] ?? "Previous pipeline output"} · will be passed to agents
                </p>
              </div>
              <div className="flex flex-shrink-0 items-center gap-2">
                <span className="rounded-[var(--radius-pill)] bg-surface-white px-2 py-0.5 text-[9px] font-medium text-status-done">
                  {contextExpanded ? "Hide" : "Preview"}
                </span>
                {contextExpanded ? (
                  <ChevronDown className="h-4 w-4 text-status-done" />
                ) : (
                  <ChevronRight className="h-4 w-4 text-status-done" />
                )}
              </div>
            </button>
            {contextExpanded && (
              <div className="border-t border-[var(--status-done-border)] px-4 py-3">
                <p className="mb-2 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-status-done">
                  <Eye className="h-3 w-3" /> What agents will receive
                </p>
                <pre className="max-h-[200px] overflow-y-auto whitespace-pre-wrap rounded-[var(--radius-button)] border border-[var(--status-done-border)] bg-surface-white/60 p-3 font-mono text-[10px] leading-relaxed text-ink-800">
                  {chainContextBlock}
                </pre>
                <p className="mt-2 text-[10px] text-status-done/80">
                  This context is automatically appended to your brief when the pipeline runs.
                </p>
              </div>
            )}
          </div>
        )}

        {/* Chain banner (context still loading). */}
        {chainFrom && !chainContextBlock && (
          <div className="flex items-center gap-3 rounded-[var(--radius-card)] border border-[var(--status-running-border)] bg-[var(--status-running-fill)] px-4 py-3">
            <div className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-[var(--radius-pill)] bg-surface-white">
              <span className="text-[11px] text-status-running">→</span>
            </div>
            <p className="text-[12px] text-status-running">
              Continuing from your <strong>{CHAIN_SOURCE_LABEL[chainFrom] ?? chainFrom}</strong> — your brief is pre-filled.
            </p>
          </div>
        )}

        {/* ── Brief (hidden when chaining — topic comes from the previous run). ── */}
        {!isChaining && (
          <section>
            <SectionLabel title={cfg.briefLabel} />
            <div className="mt-3 rounded-[var(--radius-card)] border border-line-border bg-surface-white">
              <textarea
                value={brief}
                onChange={(e) => setBrief(e.target.value)}
                name="brief"
                aria-label="Brief"
                placeholder={isListening ? "Listening... speak your idea" : cfg.placeholder}
                rows={5}
                className="w-full resize-none rounded-[var(--radius-card)] bg-transparent px-5 py-4 text-[14px] leading-relaxed text-ink-900 placeholder:text-ink-400 focus:outline-none"
              />
              {attachedFiles.length > 0 && (
                <div className="flex flex-wrap gap-1.5 px-5 pb-2">
                  {attachedFiles.map((file, idx) => (
                    <span key={`${file.name}-${idx}`} className="inline-flex items-center gap-1 rounded-[var(--radius-button)] bg-surface-warm px-2.5 py-1 text-[10px] text-ink-600">
                      <File className="h-2.5 w-2.5" /> {file.name}
                      <button onClick={() => removeFile(idx)} aria-label={`Remove ${file.name}`} className="ml-1 text-ink-400 hover:text-status-failed">
                        <X className="h-2.5 w-2.5" />
                      </button>
                    </span>
                  ))}
                </div>
              )}
              {attachedImages.length > 0 && (
                <div className="flex flex-wrap gap-1.5 px-5 pb-2">
                  {attachedImages.map((img, idx) => (
                    <span key={`${img.name}-${idx}`} className="inline-flex items-center gap-1 rounded-[var(--radius-button)] bg-surface-warm px-2.5 py-1 text-[10px] text-ink-600">
                      <ImageIcon className="h-2.5 w-2.5" /> {img.name}
                      <button onClick={() => setAttachedImages((p) => p.filter((_, i) => i !== idx))} aria-label={`Remove ${img.name}`} className="ml-1 text-ink-400 hover:text-status-failed">
                        <X className="h-2.5 w-2.5" />
                      </button>
                    </span>
                  ))}
                </div>
              )}
              <div className="flex items-center gap-1 border-t border-line-divider px-4 py-2.5">
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  accept=".pdf,.doc,.docx,.pptx,.txt,.md,.json,.csv,image/png,image/jpeg,image/webp,image/gif"
                  className="hidden"
                  onChange={(e) => { if (e.target.files) onFilesPicked(e.target.files); e.target.value = ""; }}
                />
                <button
                  onClick={() => fileInputRef.current?.click()}
                  className="flex items-center gap-1.5 rounded-[var(--radius-button)] border border-transparent px-2.5 py-1.5 text-[11px] text-ink-400 transition-all hover:border-line-border hover:bg-surface-warm hover:text-ink-700"
                >
                  <Paperclip className="h-3.5 w-3.5" /> + Attach file
                </button>
                {speechSupported && (
                  <button
                    onClick={() => { if (isListening) stopListening(); else { preSpeechTextRef.current = brief; startListening(); } }}
                    className={`flex items-center gap-1.5 rounded-[var(--radius-button)] border px-2.5 py-1.5 text-[11px] transition-all ${
                      isListening
                        ? "animate-pulse border-[var(--status-failed-border)] bg-[var(--status-failed-fill)] text-status-failed"
                        : "border-transparent text-ink-400 hover:border-line-border hover:bg-surface-warm hover:text-ink-700"
                    }`}
                  >
                    {isListening ? <MicOff className="h-3.5 w-3.5" /> : <Mic className="h-3.5 w-3.5" />}
                    {isListening ? "Stop" : "Voice"}
                  </button>
                )}
              </div>
              {examplePrompt && (
                <div className="border-t border-line-divider px-5 py-2.5">
                  <button
                    type="button"
                    onClick={() => setBrief(examplePrompt ?? "")}
                    className="inline-flex items-center gap-1.5 text-[11px] text-ink-500 hover:text-brand"
                  >
                    <Sparkles className="h-3 w-3" />
                    Use template example
                    <span className="italic text-ink-400">&ldquo;{examplePrompt}&rdquo;</span>
                  </button>
                </div>
              )}
            </div>
          </section>
        )}

        {/* Advanced / agent composer trigger. */}
        {!isChaining && (
          <button
            type="button"
            onClick={() => setShowAgents(true)}
            className="flex items-center gap-2 text-[12px] text-ink-400 transition-colors hover:text-ink-700"
          >
            <Settings2 className="h-3.5 w-3.5" />
            <span className="font-medium text-ink-600">Advanced</span>
            <span className="text-ink-400">{pipelineAgents.length} agent{pipelineAgents.length !== 1 ? "s" : ""}</span>
          </button>
        )}

        {/* ── The unified Template → Design System → Discovery stepper. ── */}
        <section>
          {loadError && (
            <div className="mb-3 rounded-[var(--radius-card)] border border-[var(--status-failed-border)] bg-[var(--status-failed-fill)] px-5 py-4 text-[13px] text-status-failed">
              Couldn&apos;t load templates: {loadError}
            </div>
          )}
          <WizardStepper
            mode={STEPPER_MODE[mode]}
            onModeChange={handleModeChange}
            steps={isDeck ? ["template"] : ["template", "design-system", "discovery"]}
            webTemplates={webTemplates}
            webSelectedId={mode === "prototype" && !customTemplateBody ? selectedTemplateId : null}
            onWebSelect={handleSelectTemplate}
            onWebSelectCustomTemplate={handleSelectCustomTemplate}
            webSelectedCustomTemplateId={mode === "prototype" && customTemplateBody ? selectedTemplateId : null}
            deckTemplates={deckTemplates}
            deckSelectedId={isDeck && !customTemplateBody ? selectedTemplateId : null}
            onDeckSelect={handleSelectTemplate}
            onDeckSelectCustomTemplate={handleSelectCustomTemplate}
            deckSelectedCustomTemplateId={isDeck && customTemplateBody ? selectedTemplateId : null}
            dsSlot={
              dsVisible ? (
                systems.length === 0 ? (
                  <div className="h-48 animate-pulse rounded-[var(--radius-card)] bg-surface-white/60" />
                ) : (
                  <DesignSystemPicker
                    systems={systems}
                    selectedId={selectedDsId}
                    onSelect={handleSelectBuiltInDs}
                    onSelectCustom={handleSelectCustomDs}
                  />
                )
              ) : (
                <StepNote>This deck template doesn&apos;t require a design system — the template supplies its own theme.</StepNote>
              )
            }
            discoverySlot={
              mode === "prototype" ? (
                <DiscoveryForm templateInputs={[]} answers={discoveryAnswers} onChange={setDiscoveryAnswers} />
              ) : (
                <StepNote>Discovery questions apply to web prototypes. Your deck brief is enough to generate.</StepNote>
              )
            }
          />
        </section>

        {/* ── Review gates (operate on the active lineup). ── */}
        <section>
          <SectionLabel
            title="Review gates"
            subtitle="Optionally pause the pipeline for your review after specific agents."
          />
          <div className="mt-3">
            <ReviewGatesSection
              agents={pipelineAgents}
              onChange={handleGatesChange}
              selections={liveSelections}
              onSelectionsChange={handleSelectionsChange}
            />
          </div>
        </section>

        {/* ── Launch. ── */}
        <div className="pt-2">
          {/* ISS-321: the same locked state the dashboard catalog card shows
              for this deliverable — reaching the wizard by direct URL must not
              be the one path that hides it. */}
          {locked && (
            <div className="mb-4 flex items-center gap-2 rounded-[var(--radius-button)] border border-brand/20 bg-brand-fill px-3 py-2 text-[11px] font-semibold text-brand">
              <Lock className="h-3.5 w-3.5 flex-shrink-0" />
              {upgradeTo
                ? `Requires ${TIER_LABELS[upgradeTo]} plan — your plan does not include this deliverable.`
                : "Your plan does not include this deliverable."}
            </div>
          )}

          {!canContinue && !locked && (
            <div className="mb-4 flex flex-wrap gap-2">
              {/* ISS-155: keyed on hasBuildInput, NOT on `!isChaining`. A chained
                  launch whose context block failed to load now blocks Continue, and
                  the old condition hid this pill for every chained launch — leaving
                  a disabled button with no stated reason. */}
              {!hasBuildInput && <Pill label="Add a brief" />}
              {isDeck && !selectedTemplateId && <Pill label="Pick a template" />}
              {(mode === "prototype" || dsRequired) && !selectedDsId && <Pill label="Pick a design system" />}
            </div>
          )}

          {saveError && (
            <div className="mb-3 rounded-[var(--radius-button)] border border-[var(--status-failed-border)] bg-[var(--status-failed-fill)] px-3 py-2 text-[11px] text-status-failed">
              {saveError}
            </div>
          )}
          {savedConfirm && (
            <div className="mb-3 rounded-[var(--radius-button)] border border-[var(--status-done-border)] bg-[var(--status-done-fill)] px-3 py-2 text-[11px] font-medium text-status-done">
              Workflow saved to your catalogue
            </div>
          )}

          <div className="flex gap-3">
            <button
              type="button"
              onClick={() => { setSaveError(null); setShowSaveModal(true); }}
              title="Save this workflow configuration to reuse later"
              className="flex flex-shrink-0 items-center gap-2 rounded-[var(--radius-card)] border border-line-border bg-surface-white px-5 py-4 text-[14px] font-semibold text-ink-700 shadow-[var(--elevation-raised)] transition-all hover:border-line-control hover:bg-surface-warm"
            >
              <Save className="h-4 w-4" />
              Save workflow
            </button>
            {/* Spec 016 — bind this lineup to the built-in so it is what THIS
                user gets whenever they open it. Separate from "Save workflow",
                which creates an unrelated saved copy; the two produce different
                rows and a silent mode is how someone overwrites what they meant
                to fork. */}
            <button
              type="button"
              onClick={handleSaveAsOverride}
              title="Make this lineup your default for this workflow"
              className="flex flex-shrink-0 items-center gap-2 rounded-[var(--radius-card)] border border-line-border bg-surface-white px-5 py-4 text-[14px] font-semibold text-ink-700 shadow-[var(--elevation-raised)] transition-all hover:border-line-control hover:bg-surface-warm"
            >
              <Save className="h-4 w-4" />
              Save as my version
            </button>
            <button
              type="button"
              onClick={handleLaunch}
              disabled={!canContinue || locked}
              className="flex flex-1 items-center justify-center gap-2 rounded-[var(--radius-card)] bg-brand px-6 py-4 text-[14px] font-semibold text-white shadow-[var(--elevation-raised)] transition-all hover:bg-brand-pressed disabled:cursor-not-allowed disabled:bg-line-divider disabled:text-ink-400 disabled:shadow-none"
            >
              Continue
              <ArrowRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      </main>

      <AgentsPopup
        // A built-in's lineup — whether run directly or saved as this user's
        // override — may only contain agents that exist as files on disk. The
        // blank template mints a `custom-agent:<instance_id>` step the launch
        // ingress rejects as an invalid agent id for this pipeline, so it is
        // offered only on the composer canvas, never here.
        allowCustomAgentTemplate={false}
        // ISS-167: AgentsPopup seeds its live selections from `initialSelections`
        // ONCE at mount (a useState initializer, not reactive to prop changes) —
        // so on a reopened saved workflow, remount it the moment the draft
        // restore populates selectionsRef.current, or it mounts empty and stays
        // that way for the rest of the session regardless of what the ref holds.
        key={userWorkflowId ?? "new"}
        isOpen={showAgents}
        onClose={() => setShowAgents(false)}
        // "Open in full canvas". LaunchWizard renders OUTSIDE DashboardLayout (a
        // page-level early return in [...view]/page.tsx), so unlike IdeaInputPage it
        // cannot call setSavedComposition directly. Hand off through sessionStorage —
        // the same channel this wizard already uses for prototype.pending/ppt.pending —
        // and let DashboardLayout pick it up when the composer route mounts.
        //
        // agentIds alone is enough here: a wizard pipeline's steps are real library
        // agents with an AGENT.md, so ComposerPage resolves them against
        // ALL_LIBRARY_AGENTS. The manifest-steps channel exists for COMPOSED workflows
        // (custom-agent:<instance_id>), which have no library entry to resolve.
        // "Open in full canvas" — navigation only. The canvas URL names the
        // workflow, so the composer refetches its manifest on mount; a sessionStorage
        // handoff is unnecessary and was read by whatever mounted next, which blanked
        // the launch panel on the way back.
        onOpenInCanvas={() => {
          setShowAgents(false);
          router.push(`/workflows/${encodeURIComponent(MODE_CONFIG[mode].agentPipeline)}/canvas`);
        }}
        agents={pipelineAgents}
        pipelineType={MODE_CONFIG[mode].agentPipeline}
        // Spec 016 — both undefined unless this user saved an override of this
        // built-in, in which case the modal renders a checkbox that swaps the
        // roster between their version and the system one.
        runConfig={declaredRunConfig}
        overrideAvailable={overrideInfo !== null}
        overrideActive={showOverride}
        onToggleOverride={overrideInfo ? handleToggleOverride : undefined}
        onAddAgent={handleAddAgent}
        onRemoveAgent={handleRemoveAgent}
        onReorder={handleReorderAgents}
        canAddMore={canAddMore}
        initialSelections={selectionsRef.current}
        selections={liveSelections}
        onSelectionsChange={handleSelectionsChange}
        userWorkflowId={userWorkflowId}
        savedName={savedName}
        savedDescription={savedDescription}
      />

      {showSaveModal && (
        <NameWorkflowModal
          title={cfg.saveTitle}
          onSave={handleSaveWorkflow}
          onCancel={() => setShowSaveModal(false)}
        />
      )}
    </div>
  );
}

function SectionLabel({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="flex items-start gap-3">
      <div>
        <h2 className="text-[14px] font-semibold text-ink-900">{title}</h2>
        {subtitle && <p className="mt-0.5 text-[12px] text-ink-500">{subtitle}</p>}
      </div>
    </div>
  );
}

function Pill({ label }: { label: string }) {
  return (
    <span className="inline-flex items-center rounded-[var(--radius-pill)] border border-[var(--status-amber-border)] bg-[var(--status-amber-fill)] px-3 py-1 text-[11px] font-medium text-status-amber">
      {label}
    </span>
  );
}

function StepNote({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-[8rem] items-center justify-center rounded-[var(--radius-card)] border border-dashed border-line-control bg-surface-warm px-6 text-center text-[12px] text-ink-500">
      {children}
    </div>
  );
}

export default LaunchWizard;
