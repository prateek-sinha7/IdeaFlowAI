# Research — how agentic systems model tool permissions

**Date:** 2026-08-16
**Method:** Sonnet research agent, web sources, primary docs preferred
**Question:** is our two-surface design (AGENT.md tool sets vs. manifest permissions) sound,
and what do mature systems converge on?

> **Framing caveat.** This first pass was commissioned with an authorization framing. That
> framing is partly wrong — see [report-capability-confinement.md](report-capability-confinement.md).
> The findings below about *declaration format*, *intersection*, and *bundles vs. flags*
> hold regardless; the identity-authorization material (Zanzibar/OpenFGA/Cedar-as-authz)
> does not apply and was dropped in the follow-up.

---

## Landscape

| System | Where declared | Granularity | Default posture | Notable mechanism |
|---|---|---|---|---|
| **Claude Code** | Layered `settings.json` (enterprise → CLI → project → user) | Tool + matcher, e.g. `Bash(npm run test *)` | Read-only tools auto-allowed **within cwd**; write/Bash require approval | **Deny > Ask > Allow** in fixed order regardless of specificity — a broad deny beats a specific allow, no exception path |
| **MCP** | Client-side `roots` (fs boundary) + `sampling` | Root = directory boundary | Client always mediates; server has no ambient authority | ⚠️ Both **deprecated as of the 2026-07-28 spec** (12-month removal). Do not model on them. |
| **OpenAI Agents SDK** | `allowed_tools` on the agent/run, `permission_mode` for approval | Named tool ids, `mcp__{server}__{tool}` | Tool must be explicitly allow-listed to be callable | Separates *guardrails* (input/output safety) from *tool access* (a simple allow-list). Finer per-tool authorization is an acknowledged open gap. |
| **LangChain / LangGraph** | Code: `llm.bind_tools([...])` per node | Whatever you bind | None — bind everything, get everything | Community pattern: a **policy node computes `allowed_tools` into graph state each step**, downstream node binds. Permission recomputed per step, not fixed per agent identity. |
| **CrewAI** | `tools=[...]` on the `Agent()` definition | Whole tool objects per agent | No tools unless assigned | See "independent confirmation" below. |
| **Android** | Static manifest + runtime dialog for "dangerous" tier | Named permission classes, grouped by risk | Nothing ambient | **Two-phase**: declaring intent is necessary but not sufficient; a second human-mediated grant gate exists for high-risk classes. |
| **Chrome Manifest V3** | `manifest.json`: `permissions` + separate `host_permissions` | URL match patterns; discrete API permissions | Nothing beyond declared | V3's core change was **forcing declaration granularity up** — splitting host access out of the permissions bundle — specifically because V2's coarse bundles were an abuse vector. |
| **Kubernetes RBAC** | `Role` (what actions exist) + `RoleBinding` (who holds them) | verb × resource × namespace | Deny-by-default | Two independently-authored, independently-auditable objects; admission controllers are a second orthogonal gate. |
| **WASI / Wasmtime** | Host passes capability objects at instantiation | Per-resource-instance (a specific handle, not a class) | **Zero ambient authority** | The capability *is* the only route — no separate permission object checked against a name. If you don't hold the handle the operation is unreachable, not merely disallowed. |

---

## Independent confirmation of our defect

CrewAI's community documented our exact failure mode, in their system, independently:

> "Scope each agent's tools to its role, don't hand everyone the full toolset" — a
> researcher agent given file-write/shell tools **"would occasionally decide to do the
> work itself instead of returning findings for the next agent,"** collapsing the workflow.

That is `story-estimator` writing a backlog instead of returning story points.
([source](https://community.crewai.com/t/field-note-scope-each-agents-tools-to-its-role-dont-hand-everyone-the-full-toolset/7687))

---

## Answers to the design questions

### Per-agent, per-step, per-workflow, or layered?

**Layered, always.** Every mature system that has both a *component author* and an
*operator* uses two objects:

```
Kubernetes   Role (what actions exist)   ×  RoleBinding (who holds them)
Android      manifest (declared need)    ×  runtime grant
OAuth        client registered scopes    ×  user consent
MCP          server capability           ×  client-mediated grant
```

None collapse to a single flat surface when both an untrusted author and an operator
exist. **This argues against deleting our `AGENT.md` declaration.** Our problem is not
that two layers exist — it is that layer 1 is an opaque alias resolved by hardcoded tuples
in code while layer 2 is explicit flags. Fix the *format*, keep the *layer*.

### Deny-by-default, or safe default plus escalation?

Every deliberately security-designed system is **deny-by-default**: WASI, K8s RBAC,
Android dangerous-perms, Manifest V3, MCP roots.

No primary-source agentic framework documents "safe default read access" as an intentional
security posture. Claude Code is the closest — and its default is narrower than it sounds:
**read-only, scoped to the working directory, and write is never defaulted.**

> Practical reading for us: a bounded `read_files` default is defensible. A blanket
> read+write default is exactly the failure mode this class of system exists to prevent —
> and is what caused our incidents.

### Is intersection standard? Does it have a name?

Yes, standard. **No single canonical name** surfaced across sources — flagged as
not fully verifiable. The closest documented instance of exactly two independently-authored
grants ANDed is **OAuth 2.0**:

```
client's requested scopes  ∩  resource owner's consented scopes  ∩  AS policy ceiling
```

Functionally identical three-way AND to our `owner ∩ workflow_ceiling ∩ step_grant`.

**Our intersection model is sound and well-precedented. The defect was never the algebra —
it is that the resolved value has no consumer.**

### Capability vs. permission

WASI/ocap literature draws it cleanest:

- **capability** — this actor holds a reference that makes the action possible (the tool
  object exists)
- **permission** — policy says this actor is allowed to

Systems that **conflate** them — checking a boolean against a shared, always-instantiated
toolset — are structurally exposed to our bug class: the flag can be computed correctly and
simply not checked, because the tool object existed regardless.

Systems that **don't** conflate them (WASI) cannot have that bug, because the unauthorized
tool object is never constructed.

> The actual fix for "computed but never enforced", independent of manifest format:
> **the binding step must construct the tool set from the resolved permissions**, not
> construct a full tool set and separately consult a permission object.

### Named bundles vs. explicit flags

**Manifest V3 is the clearest precedent** — a system that shipped bundles (V2), then
migrated away from them toward explicit granular flags, citing security and user-trust
reasons. Kubernetes' anti-wildcard guidance is the same lesson in another domain.

The agent found **no mature system that started explicit and converged toward opaque
bundles.** Migration direction is always bundle → explicit.

This directly validates retiring `tools: [workspace]`.

> V3 handled the resulting verbosity with `optional_*` permissions (deferred/contextual
> grants), **not** by reintroducing bundles. Our equivalent: presets in the Composer UI
> that expand to explicit flags *at authoring time*, so the runtime only ever sees flags.

### The boolean-can't-express-partial-access trap

Our `ToolPermissions` already avoids the crudest version (separate `read_files` /
`write_files` rather than one `filesystem: bool`).

For finer granularity later, the established next step is **scoping the grant to a
path/root, not adding more booleans** — which is exactly what MCP `roots` and WASI
directory handles both do. Or verb × resource pairs, as in K8s RBAC.

---

## Anti-patterns matching our defects

| Our defect | Named as |
|---|---|
| Blanket ambient-authority fallback for undeclared agents | The core "ambient authority" anti-pattern in ocap literature — granting default access not tied to an explicit request |
| Over-toolled agent takes over downstream work | CrewAI's documented field note (above) |
| Permission computed but not enforced | Not a named security-taxonomy item (it's an implementation-bug category), but maps to OWASP **LLM06 excessive permissions** — the documented fix is that the runtime enforcement point must be the single place tool access is granted, with no bypass path |
| Opaque named tool-set aliases hardcoded in code | OWASP LLM06 **excessive functionality** — structurally likely when a shared alias is broader than any one agent needs |

### Correction on OWASP numbering

"LLM08 Excessive Permissions" **does not exist**. In the current OWASP Top 10 for LLM
Applications, LLM08 is *Vector and Embedding Weaknesses*. The relevant category is
**LLM06: Excessive Agency**, which decomposes into three root causes: excessive
functionality, excessive permissions, excessive autonomy. Use that taxonomy in any design
doc.

---

## Recommendation from this pass

1. **Source of truth** — collapse to the manifest, but keep it a two-layer *value*, not a
   two-*file* system. Agent-level declared ceiling + step-level grant, intersected, both
   in the same explicit-flag vocabulary. Make `AGENT.md` declare
   `{read_files, write_files, exec, extra_tools}`, not a named bundle. This kills the
   alias→hardcoded-tuple indirection causing today's bugs while keeping the layer that
   stops a manifest granting `write_file` to an agent whose prompt says "output only
   markdown".
2. **Default posture** — deny-by-default has the precedent. A bounded `read_files` default
   is acceptable (Claude Code-style: read-only, scoped); `write_files` and `exec` must
   default false with **no fallback path**.
3. **Keep intersection.** Same structure OAuth uses at scale; it correctly encodes our
   trust tiers. Fix the missing consumer, not the algebra.
4. **Capability vs. permission** — the resolved flags must determine which tool objects get
   *constructed*. Don't build a full toolset and gate calls. This makes "computed but not
   enforced" structurally impossible rather than fixed-for-now.

---

## Flagged as unverifiable

- No canonical industry name for "intersection of independently-authored grants"; OAuth
  scope-intersection used as the closest documented analogue rather than claiming a formal
  pattern name exists.
- MCP `roots`/`sampling` are being deprecated in the current spec cycle — historical
  reference only, not a target architecture.

---

## Sources

- https://code.claude.com/docs/en/permissions
- https://modelcontextprotocol.io/specification/draft/client/sampling
- https://blog.acolyer.org/2016/02/16/capability-myths-demolished/
- https://en.wikipedia.org/wiki/Confused_deputy_problem
- https://medium.com/webassembly/capabilities-based-security-with-wasi-c523a34c1944
- https://developer.chrome.com/docs/extensions/develop/concepts/declare-permissions
- https://kubernetes.io/docs/reference/access-authn-authz/rbac/
- https://source.android.com/docs/core/permissions/runtime_perms
- https://openai.github.io/openai-agents-python/guardrails/
- https://github.com/langchain-ai/langgraph/discussions/6059
- https://community.crewai.com/t/field-note-scope-each-agents-tools-to-its-role-dont-hand-everyone-the-full-toolset/7687
- https://genai.owasp.org/llmrisk/llm06-sensitive-information-disclosure/
