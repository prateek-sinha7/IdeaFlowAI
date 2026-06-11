---
phase: 11
slug: engine-owned-fan-out-merge-5
status: verified
threats_open: 0
asvs_level: 1
created: 2026-06-11
---

# Phase 11 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

Register authored at plan time (all 5 PLAN files carry a `<threat_model>` block).
Audit mode: verify-mitigations (not retroactive STRIDE). Every `mitigate` threat was
verified by locating the actual guard/call in the cited implementation file AND its
asserting test; every `accept` threat was verified by confirming the acceptance
rationale holds in the phase commits. Implementation files were treated as read-only.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| agent (LLM) → spawn_subagents tool | Model emits a fan-out REQUEST; the kernel — not the tool — decides what spawns | untrusted task list / mode |
| manifest → compiler | Declared `fanout` / `allowed_workers` / `Limits` are untrusted data; trust-conditional compile, unknown keys rejected (INV-5) | manifest YAML/JSON |
| run → subagent_runs store | Child rows are owner/workspace-scoped; cross-owner reads return ∅ | run rows, fragment refs |
| run_fanout → isolation provider | Engine picks the isolation scope; the manifest cannot influence it (INV-7) | scope decision |
| LocalWorkspace → git subprocess | git runs only inside the single `_git` owner with `GIT_ALLOW_PROTOCOL` + option-injection guards | clone/worktree/branch/merge args |
| worker → parent workspace | Workers read shared-read parent refs; writes isolated to the child workspace | files |
| merge strategy → base workspace | Fragments integrate into the run's primary workspace; overlap is reported, never silently applied | merged files |
| merge_conflict artifact → approver | The conflict payload a human adjudicates; must not leak raw secrets | truncated hunks/snippets |
| merge_agent worker → run_fanout | Bounded retry worker; must not oscillate past 2 attempts | conflict resolution attempts |
| manifest Limits → compiler | Untrusted (user/db) Limits may only lower; file Limits may raise — static budget ceiling gate | caps |
| run_fanout → BudgetManager.reserve | The single budget enforcement point; spawning outside run_fanout would bypass it | reservations |
| workspace → per-workspace ceiling | Aggregate spend keyed owner+workspace; cross-owner runs must not interfere | spend aggregates |
| cancel_event → in-flight children | Cancellation propagates to all in-flight worker tasks and prevents pending spawns | cancel signal |
| run termination → isolated workspaces | Every allocated isolated workspace is torn down (incl. cancel path) — no leaks | dirs/branches/worktrees |
| file manifest → spawn_subagents grant | The sample_fanout file manifest is trusted, so the privileged grant is allowed (user/db rejected) | capability grant |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-11-01-01 | Elevation of Privilege | spawn_subagents tool grantable by user/db manifest | mitigate | `providers.py:116` `@register("tool","spawn_subagents", user_allowed=False)`; compiler CAP-03 `_check_trust` (`compiler.py:299-324`) + step-grant rejection (`compiler.py:444-452`); deepagents `task` tool excluded (`deep_agent_runner.py:84,96`) — `test_fanout_tool.py:23`, `test_compiler_trust.py:242` | closed |
| T-11-01-02 | Denial of Service | unbounded worker spawn via run_fanout | mitigate | concurrency capped `min(declared, DEFAULT_MAX_CONCURRENCY=4)` via `asyncio.Semaphore` in the single spawn path (`fanout.py:159-169,517-518`; `budget.py:44`) — `test_fanout.py` parallel cap, `test_budget.py:133` | closed |
| T-11-01-03 | Information Disclosure | cross-owner subagent_runs read | mitigate | `ScopedStore.read_subagent_runs` applies `_scope_owner_ws` (`authz.py:1015-1032`); `owner_id`/`workspace_id` `nullable=False` (`subagent_run.py:35-36`, migration 0019) — `test_subagent_runs.py:190` cross-owner `== []` | closed |
| T-11-01-04 | Tampering | spawn_subagents tool body performs the spawn (bypassing reserve/audit) | mitigate | tool body is a store-free/spawn-free JSON request emitter (`runner_tools.py:43-58`, imports only `json` + `langchain_core.tools`) — `test_fanout_tool.py:44,54` module-is-spawn-free | closed |
| T-11-01-SC | Tampering (supply chain) | npm/pip/cargo installs | accept | zero new packages this phase; brownfield on installed stack (deepagents 0.6.7, stdlib, repo-pinned Alembic/SQLAlchemy) — see Accepted Risks Log | closed |
| T-11-02-01 | Tampering / EoP | git transport code-exec at worktree add | mitigate | worktree ops route through the single `_git` owner (`local.py:472-506`); `GIT_ALLOW_PROTOCOL=file:https:ssh` + `source.startswith("-")` guard + `--` (`local.py:266-292`) — `test_isolation.py:121` | closed |
| T-11-02-02 | Tampering | worker write cross-contamination before merge | mitigate | per-worker write isolation: sub_sandbox child dir (`local.py:445-470`) / worktree branch (`local.py:472-506`) — `test_isolation.py:92` two-worker same-filename distinct roots | closed |
| T-11-02-03 | Information Disclosure | manifest-controlled isolation downgrade to shared_read | mitigate | scope engine-decided in `fanout._select_isolation_scope` (`fanout.py:226-238`, has_git→worktree else sub_sandbox); `_ALLOWED_FANOUT_KEYS` (`compiler.py:101-103`) carries no `isolation` key (INV-7) | closed |
| T-11-02-04 | Resource leak (DoS) | orphaned worktree/branch on happy path | mitigate | `remove_worktree` runs `git worktree remove --force` + `git branch -D` via `_git` (`local.py:558-582`) after collect — teardown asserts in `test_isolation.py` / `test_fanout_cancel.py` | closed |
| T-11-02-05 | Access Control | isolated workspace missing owner/workspace scoping | mitigate | `allocate_sub_sandbox`/`allocate_worktree` stamp parent `owner_id`/`workspace_id` (`local.py:464-466,495-498`) — `test_isolation.py:82` | closed |
| T-11-02-SC | Tampering (supply chain) | npm/pip/cargo installs | accept | zero new packages; stdlib subprocess + system git only — see Accepted Risks Log | closed |
| T-11-03-01 | Tampering | merge silently overwrites instead of reporting a conflict | mitigate | overlap → reported conflict, never silent overwrite: `copy_disjoint.py:80-101`, `json_merge.py:72-90`, `git_3way.py:54-62`, `merge_worktree` parses unmerged + `git merge --abort` (`local.py:598-617`) — `test_merge_conflict.py:210`, `test_merge.py` | closed |
| T-11-03-02 | Information Disclosure | secret leakage in merge_conflict payload | mitigate | payload truncated to `_SNIPPET_CAP=256` hunks (`copy_disjoint.py:25,117`; `json_merge.py:21,106`; `git_3way.py:23,60`); merge_conflict ArtifactRef owner-scoped via ScopedStore — `test_merge_conflict.py:15` | closed |
| T-11-03-03 | Denial of Service | merge_agent unbounded retry oscillation | mitigate | `MERGE_AGENT_MAX_ATTEMPTS=2` (`budget.py:47`); `_run_merge_agent` bounded loop then `human_gate` fallback (`fanout.py:970-1006`) — `test_merge_conflict.py:270` | closed |
| T-11-03-04 | EoP | a second HITL surface for merge conflicts | mitigate | merge `human_gate` delegates to the ONE durable `run_human_gate`→`_run_review_gate` (`fanout.py:1009-1030`); grep `run_merge_gate` non-test = 0 | closed |
| T-11-03-05 | Tampering | git_3way shells git from the capability layer | mitigate | `git_3way` reaches git only via `ctx.runner.git_3way_merge` handle (`git_3way.py:40-65`); zero real `subprocess`/`Popen`/`os.system` in `agents/capabilities/merge/`; import-linter contract kept | closed |
| T-11-03-SC | Tampering (supply chain) | npm/pip/cargo installs | accept | zero new packages; pure-stdlib merges + system git via handle — see Accepted Risks Log | closed |
| T-11-04-01 | Denial of Service | resource exhaustion via unbounded fan-out (fork bomb) | mitigate | `BudgetManager.reserve` enforces subagents=8/concurrency=4/depth=2/wall=900s + per-workspace ceiling BEFORE spawn (`budget.py:150-217`); reserve is first call in the single spawn path (`fanout.py:294-316`) — `test_budget.py:125,142` | closed |
| T-11-04-02 | EoP | user/db manifest raising a Limits cap above the ceiling | mitigate | trust-conditional `_compile_limits`: untrusted raise → CompilerError naming the dimension; file/builtin may raise (`compiler.py:248-295`) — `test_compiler_trust.py:347` | closed |
| T-11-04-03 | EoP / DoS | bypassing the budget by spawning outside run_fanout | mitigate | `run_fanout` is the ONLY spawn path (FANOUT-02); `budget.reserve` first enforcement call before any allocate/run_worker/row (`fanout.py:270-316`) — refused reserve leaves zero `subagent_runs` rows (`test_budget.py`) | closed |
| T-11-04-04 | Information Disclosure | cross-owner workspace budget aggregate read | mitigate | `ScopedStore.workspace_budget_spent` owner+workspace keyed default-deny (`authz.py:1034-1066`) — ceiling scoping tests | closed |
| T-11-04-05 | Availability | snapshot/audit write aborts the run | mitigate | `persist_budget_snapshot` None-degrading: `store is None → return`, try/except → `logger.warning`, never aborts (`kernel_services.py:491-513`; `authz.py:351-374`) | closed |
| T-11-04-SC | Tampering (supply chain) | npm/pip/cargo installs | accept | zero new packages; stdlib budget enforcement — see Accepted Risks Log | closed |
| T-11-05-01 | Resource leak (DoS) | orphaned worktrees/branches/sub_sandbox dirs after cancel | mitigate | `finally`-block `_teardown_allocated` reclaims EVERY allocated workspace on happy/cancel/abort paths (`fanout.py:621-634,1033-1057`) — zero-residue asserts in `test_fanout_cancel.py` | closed |
| T-11-05-02 | Denial of Service | a cancelled run keeps spawning pending workers | mitigate | `_check_cancel` before wave, between sequential workers, before merge (`fanout.py:207-223,258,502,605`); in-flight tasks cancelled via `_gather_or_cancel` (`fanout.py:637-674`) — `test_fanout_cancel.py:140` | closed |
| T-11-05-03 | EoP | user/db manifest granting spawn_subagents via the sample workflow precedent | mitigate | `sample_fanout/workflow.yaml` is FILE-trusted; CAP-03 rejects user/db manifests referencing `user_allowed=False` `spawn_subagents` (`compiler.py:299-324`) — `test_sc001_fanout.py:358` (engine grep = 0) | closed |
| T-11-05-04 | Integrity | a cancelled run loses completed work | mitigate | completed fragments persisted before merge (`write_fragment_artifact`, `fanout.py:439-457`) survive cancel; only conflicted/incomplete rows marked `cancelled` (`fanout.py:402-410,687-702`) — retained-artifact asserts in `test_fanout_cancel.py` | closed |
| T-11-05-SC | Tampering (supply chain) | npm/pip/cargo installs | accept | zero new packages; sample workflow uses only registered capabilities — see Accepted Risks Log | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-11-01 | T-11-01-SC | Zero new packages this phase; brownfield on the installed stack (deepagents 0.6.7, stdlib asyncio/subprocess, repo-pinned Alembic/SQLAlchemy). Verified: phase-11 commits (`cdec230^..HEAD`) changed zero backend dependency manifests. | plan-time disposition, verified by gsd-security-auditor | 2026-06-11 |
| AR-11-02 | T-11-02-SC | Zero new packages; stdlib subprocess + system git only. Same dep-manifest verification. | plan-time disposition, verified by gsd-security-auditor | 2026-06-11 |
| AR-11-03 | T-11-03-SC | Zero new packages; pure-stdlib merges + system git via the runner handle. Same dep-manifest verification. | plan-time disposition, verified by gsd-security-auditor | 2026-06-11 |
| AR-11-04 | T-11-04-SC | Zero new packages; stdlib budget enforcement. Same dep-manifest verification. | plan-time disposition, verified by gsd-security-auditor | 2026-06-11 |
| AR-11-05 | T-11-05-SC | Zero new packages; the sample workflow uses only registered capabilities. Same dep-manifest verification. | plan-time disposition, verified by gsd-security-auditor | 2026-06-11 |

*Accepted risks do not resurface in future audit runs.*

**Inherited accepted residual (Phase 10, informational — not a Phase-11 risk):**
T-10-01-05 / EGRESS-DENY — an allow-listed interpreter under an exec-granted workspace
can still open sockets at runtime (`policy.network=False` + no-net allow-list + scrubbed
env mitigate but do not hard-block egress; OS-level network-namespace enforcement is the
v2 ECS seam). Moot for Phase 11: every fan-out isolated workspace is constructed with
`LocalExecutionPolicy(exec=False)` (`allocate_sub_sandbox` / `allocate_worktree`).

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-06-11 | 28 | 28 | 0 | gsd-security-auditor (opus) |

### Audit Notes (2026-06-11)

- **Counts:** 23 `mitigate` threats verified closed in code + test; 5 `accept` (`*-SC`)
  threats recorded in the Accepted Risks Log with verified rationale. The auditor's raw
  report header said "20 mitigate / 25 total" — a miscount; its own evidence table covers
  all 23 mitigate rows, reconciled here against the plan registers (4+5+5+5+4).
- **Single spawn path (FANOUT-02):** `run_fanout` (`fanout.py:241`) is the sole spawn
  site; both the `fanout_batch` strategy and the `spawn_subagents` tool funnel through
  it, and `budget.reserve` is the first enforcement call inside it — so T-11-04-01/03
  mitigations apply to ALL entry points.
- **Registry lockstep:** `_KNOWN` carries 59 `(kind,name)` pairs (`registry.py:78-138`),
  matching the SUMMARY self-check (53→59); the four new merge strategies +
  `fanout_batch` + `spawn_subagents (user_allowed=False)` are present.
- **Import direction:** the merge capability layer reaches git only via the `ctx.runner`
  handle (no `subprocess` in `merge/`); the compiler never imports the kernel (budget
  ceiling duplicated as a static constant, `compiler.py:157-164`, keeping the
  import-linter contract green — 4 kept / 0 broken).
- **Unregistered flags:** none. All five SUMMARY `## Threat Flags` sections declare
  "None"; every new surface (merge_conflict artifact, git_3way, `workspace_budget_spent`,
  `budget_snapshot_json`, `spawn_subagents` ceiling entry, cancel teardown) maps to an
  in-register threat.
- **No implementation files modified** by this audit.

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-06-11
