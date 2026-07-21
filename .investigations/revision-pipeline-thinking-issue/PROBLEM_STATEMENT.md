# Problem Statement — Prototype Revision Pipeline: Fixes Don't Land + No Thinking Visibility

## Original ask (verbatim intent)

> When I run a revision on a prototype via the revision pipeline, the reported
> issue is often still present after the revision completes. Separately, I
> don't see any "thinking" output during the run. Find the root cause of both,
> determine whether extended thinking is enabled, what would happen if we
> turned it on, and produce a fix — with a plan and task breakdown — that
> makes revisions reliably fix what the user asked for. We run this pipeline
> on Haiku.

## Expanded problem statement

This investigation covers two related but distinct defects in the
`prototype_revision` pipeline (`backend/agents/workflows/prototype_revision/workflow.yaml`),
both of which degrade the user's trust that "Request a revision" actually
does what it says:

### Defect A — Revisions don't reliably fix the reported issue

**Symptom**: A user submits a revision instruction against an existing
`prototype.html` (e.g. "the Save button on Settings doesn't do anything" or
"dark mode toggle is broken"). The pipeline completes, reports success, and
the deliverable is updated — but the specific issue the user described is
still present, or only partially addressed.

**Scope questions this investigation answers**:
1. Does the revision pipeline ever check whether the user's *specific
   instruction* was satisfied, as opposed to checking generic structural
   health (blank pages, dead nav, render errors)?
2. Is there a retry/fix-loop, and if so, what does it actually loop on —
   the user's request, or something else?
3. Is a single Haiku pass sufficient to reliably satisfy an arbitrary
   free-text revision instruction with no verification step, and if not,
   what's the cheapest change that closes the loop?
4. Are there failure modes in the edit mechanism itself (`edit_file`
   non-unique/non-matching `old_string`) that can silently no-op an edit
   while the agent still reports success?

### Defect B — No visible "thinking" during any pipeline run

**Symptom**: The UI has full support for rendering a "thinking" stream
(`ThinkingBlock.tsx`, `AgentThinkingTab.tsx`, the `agent_thinking` WS event,
`useWorkflow.ts` state fields `thinking`/`thinkingText`) — but during a live
pipeline run (prototype, prototype_revision, or any other manifest-driven
pipeline) nothing ever populates it. The user sees only final output text,
never the model's reasoning.

**Scope questions this investigation answers**:
1. Is Anthropic/Bedrock extended thinking enabled anywhere in the live
   pipeline path today? What is the exact on/off switch and its default?
2. If it were switched on, would the UI actually show anything new, or
   would it just add latency/cost with no visible effect? (i.e. is the
   pipe end-to-end wired, or broken somewhere in the middle?)
3. Is the `agent_thinking` event that the frontend already knows how to
   render reachable from the manifest-driven `ExecutionEngine` path at all,
   or is it only reachable from an unrelated legacy subsystem?
4. What would it cost (latency, tokens, $ on Haiku) to turn extended
   thinking on for the revision pipeline specifically, and is that the
   right lever for "visibility" versus a separate, cheaper mechanism
   (e.g. narrating tool-call intent)?

### Why this matters together, not separately

Both defects compound: a user who can't see *why* the revision agent made
the edit it made (Defect B) has no way to tell, mid-run, whether the agent
even understood the request — and today they'd be right to suspect it
didn't, because Defect A means there's no automated check either. Fixing
visibility without fixing the verification gap only lets the user watch the
agent fail transparently; fixing verification without visibility leaves
Haiku's interpretation of ambiguous instructions as a black box. Both need
to close for "Request a revision" to be trustworthy.

### Explicit non-goals

- Not investigating the four *other* revision pipelines (`ppt_revision`,
  `user_stories_revision`, `app_builder_revision`, `od_ppt_revision`) in
  depth — they are `revises_existing: false` (whole-artifact regeneration,
  not in-place edit) and structurally different. Findings that generalize
  are called out, but the fix plan targets `prototype_revision` specifically
  since that's what was reported.
- Not proposing a model upgrade off Haiku as the primary fix — the ask is
  "we'll be using Haiku," so the plan treats the model as fixed and designs
  verification/visibility around that constraint (with a *cheap, scoped*
  model-bump as one candidate option, not the default recommendation).
