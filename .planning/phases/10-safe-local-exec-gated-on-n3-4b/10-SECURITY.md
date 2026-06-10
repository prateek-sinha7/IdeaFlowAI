---
phase: 10
slug: safe-local-exec-gated-on-n3-4b
status: verified
threats_open: 0
asvs_level: 1
created: 2026-06-10
---

# Phase 10 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.
> Safe Local Exec (gated on N3) [4B] — verifies EXEC-01 / EXEC-02 mitigations are
> present in the implemented code (not documentation/intent). FORCE stance:
> every threat started OPEN and was closed only on a grep/read/test match in the
> cited file. The 5 SPEC-accepted residuals are recorded in the Accepted Risks Log.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| capability/validator → `workspace.exec_command(argv)` | The ONLY legal path to spawn a process; allow/deny + caps + audit enforced at this single point | argv list (no shell string) |
| exec'd child process → host environment | Untrusted code runs; must not see host creds or escape the run root | scrubbed env (PATH/HOME/TMPDIR only), cwd=run root |
| exec'd child process → network | Egress must be denied (policy + allow-list + scrubbed env) | no net-capable tool on allow-list; residual interpreter-socket accepted |
| ScopedStore writes → `exec_runs` rows | Owner/workspace-scoped; cross-owner reads denied | owner_id + workspace_id, truncated output digest (never raw secrets) |
| manifest author trust (file/builtin vs user/db) → compiled grant | Compile-time is where trust is known; user/db must never compile an exec/network/secrets grant | `Step.tools.exec` bool |
| compiled exec step → security gate → first-exec approval (HITL) | Runtime second/third line: exec passes only with profile + approval declared + durable human sign-off | gate_events rows, D-04 policy snapshot (no creds/argv) |
| engine run entry → runtime workspace binding (§15 host seam) | The ONE place the exec-enabled workspace is provisioned, conditional on the plan granting exec | `KernelServices.workspace` |
| user palette → `slack_post` WRITE (MCP-04) | The one user-grantable write; sign-off documents the accepted post-only scope | post_message scope |
| repo diff parser → per-file output | An unparseable `diff --git` header must not silently drop a changed file | synthetic `__unparsed_N__` key |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-10-01-01 | Tampering/EoP | exec_command shell interpolation (IN-02) | mitigate | `shell=False` argv body (`local.py:326`); grep `shell=True` over runtime+agents = 0 | closed |
| T-10-01-02 | Tampering | argument injection (`-`-prefixed argv[0]) | mitigate | pre-spawn allow-list check, deny beats allow, recorded before any spawn (`local.py:294-299`); empty-argv guard (WR-02, `local.py:291-293`) | closed |
| T-10-01-03 | Information Disclosure | host credential exfiltration into child | mitigate | scrubbed minimal env dict PATH/HOME/TMPDIR only (`local.py:37,302`); test_local_runtime asserts no AWS/ANTHROPIC/DATABASE/TOKEN/PROXY survives | closed |
| T-10-01-04 | DoS | resource exhaustion (fork bomb / OOM / CPU spin) | mitigate | RLIMIT_CPU + RLIMIT_AS preexec_fn (`local.py:308-314`) + wall-clock timeout + `os.killpg` group kill on timeout (WR-01, `local.py:336-341`) + start_new_session | closed |
| T-10-01-05 | Information Disclosure | data egress over interpreter sockets | accept | policy.network=False + no net-capable tool on allow-list + scrubbed env; residual documented at `local.py:273-277`. See Accepted Risks (RISK-1) | closed |
| T-10-01-06 | DoS | unbounded output (log/memory blowup) | mitigate | 64KB/stream truncation `_OUTPUT_CAP` (`local.py:42,357`); only a 256-char digest in the audit row (`local.py:363`) | closed |
| T-10-01-07 | Repudiation | audit bypass | mitigate | recorder fires at the single enforcement point on every outcome (`local.py:281,292,296,348,358`); CR-01 sync→async adapter `_make_exec_recorder` (`engine.py:338`) bridges to `record_exec_run`; ScopedStore writer (`authz.py:843`) | closed |
| T-10-01-08 | Information Disclosure | cross-owner exec_runs read | mitigate | `ScopedStore.read_exec_runs` applies `_scope_owner_ws` default-deny (`authz.py:887-901`); migration 0018 owner_id+workspace_id NOT NULL; test_exec_runs cross-owner read returns zero | closed |
| T-10-01-SC | Tampering | npm/pip/cargo installs | mitigate | zero external packages (stdlib subprocess/resource/os + pre-installed ruff/pytest); SUMMARY Threat Flags: None | closed |
| T-10-02-01 | Elevation of Privilege | user/db manifest granting exec/network/secrets | mitigate | trust-conditional guard raises CompilerError naming the grant(s) + step for non-trusted trust (`compiler.py:323-336`); test_compiler_trust user/db exec/network/secrets → CompilerError | closed |
| T-10-02-02 | Elevation of Privilege | exec step authored without approval/security gate | mitigate | D-01 gates-required: `{security,approval} - set(gates)` → CompilerError (`compiler.py:342-349`) | closed |
| T-10-02-03 | Tampering | compiler silently widening a grant via auto-injection | mitigate | D-01 raises, NEVER mutates the gates list (`compiler.py:342-349`); compiled plan mirrors the manifest | closed |
| T-10-02-04 | Repudiation/Tampering | dual policy surfaces drifting (INV-12) | mitigate | `plan.py:ExecutionPolicy.check` DELETED; grep `ExecutionPolicy\.check` over backend = 0 (verified); migration-ledger D11 ratchet green | closed |
| T-10-02-SC | Tampering | npm/pip/cargo installs | mitigate | zero external packages (compiler edit + deletion only); SUMMARY Threat Flags: None | closed |
| T-10-03-01 | Elevation of Privilege | exec passing the gate without human sign-off | mitigate | ApprovalGate delegates first-exec to `run_human_gate`→`_run_review_gate`, reject→GATE_BLOCK (`approval.py:141-157`); SecurityGate blocks exec if `approval` not declared (`security.py:104-108`) | closed |
| T-10-03-02 | Elevation of Privilege | network/secrets slipping through the loosened exec branch | mitigate | network/secrets BLOCK path kept separate + byte-identical (`security.py:60-87`); only exec branch is conditional PASS | closed |
| T-10-03-03 | Spoofing/Tampering | replaying/forging first-exec memory | mitigate | D-03 reads durable owner/workspace-scoped `gate_events` via `read_gate_events` (`approval.py:111-123`), not a forgeable in-memory flag | closed |
| T-10-03-04 | Repudiation | exec authorized but not audited | mitigate | every gate evaluation writes a gate_events row (`write_gate_event` in security.py/approval.py); the workspace recorder audits the exec itself (T-10-01-07) | closed |
| T-10-03-05 | Tampering | non-exec run silently gaining an exec-enabled workspace (parity break) | mitigate | §15 host seam gated on `_plan_grants_exec = any(s.tools.exec ...)` (`engine.py:1200-1214`); 10 characterization snapshots byte/event-identical | closed |
| T-10-03-06 | Information Disclosure | approval payload leaking secrets to the approver | accept | D-04 `_exec_policy_snapshot` carries only allow-list + caps + scrubbed-env note, no creds, no argv (`approval.py:52-90`). See Accepted Risks (RISK-2) | closed |
| T-10-03-SC | Tampering | npm/pip/cargo installs | mitigate | zero external packages (gate + engine edits only); SUMMARY Threat Flags: None | closed |
| T-10-04-01 | Elevation of Privilege | validator spawning subprocess directly (bypassing policy+audit) | mitigate | validators reach exec ONLY via `ws.exec_command` (`code_compile.py:97`, `_exec_support.py`); grep `subprocess.run(`/`Popen(` in the 3 files = 0; lint-imports 4/0 keeps them off app.* | closed |
| T-10-04-02 | Tampering | validator silently passing when exec ungranted (false green) | mitigate | VALIDATOR-DENY: `if ws is None or not exec_granted(ws)` → refusal Issue, no spawn (`code_compile.py:81`); PermissionError caught, never escapes (`code_compile.py:99-100`) | closed |
| T-10-04-03 | DoS | pytest-inside-pytest hang / runaway fixture | mitigate | tiny `sample_python_repo` fixture; `pytest -p no:cacheprovider`; bounded by the 10-01 policy caps (cpu=60s, wall=120s) | closed |
| T-10-04-04 | Information Disclosure | sample manifest leaking into a shipped/user-grantable palette | accept | fixture lives under tests/agents/fixtures only; exec stays gate+trust-bound. See Accepted Risks (RISK-3) | closed |
| T-10-04-SC | Tampering | npm/pip/cargo installs | mitigate | zero external packages (ruff/pytest pre-installed, py_compile stdlib); SUMMARY Threat Flags: None | closed |
| T-10-05-01 | Repudiation/Tampering | shell=True reintroduced after the IN-02 fix | mitigate | migration-ledger ☑ grep ratchet for `shell=True` (test_migration_ledger asserts 0 in scope); grep over runtime+agents = 0 (verified) | closed |
| T-10-05-02 | Information Disclosure/Tampering | a changed file silently dropped from a repo diff (IN-03) | mitigate | synthetic-key fallback: `_flush` keys `__unparsed_N__` when current_path is None but current_lines exist, per-call idx (`repo_diff.py:131-148`); test_repo_diff covers quoted/rename/multiple | closed |
| T-10-05-03 | Elevation of Privilege | slack_post user-grantable write scope misunderstood/widened (IN-01) | mitigate | MCP-04 sign-off docstring near `user_allowed=True` (`catalog.py:86-103`); exposed_tools/user_allowed UNCHANGED (no behavior change) | closed |
| T-10-05-04 | Tampering | exec stack perturbing existing deterministic runs (parity break) | mitigate | phase parity gate: 10 characterization snapshots byte/event-identical (SNAPSHOT_UPDATE unset), lint-imports 4/0, banned-pattern + migration-ledger green (re-run this audit) | closed |
| T-10-05-SC | Tampering | npm/pip/cargo installs | mitigate | zero external packages (comment + parser fix + planning-doc edits); SUMMARY Threat Flags: None | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

**Verification summary:** 31/31 threats CLOSED (26 mitigate + 5 accept). Behavior
suite 131 passed / 5 skipped (test_local_runtime, test_exec_runs, test_compiler_trust,
test_gates, test_code_validators, test_repo_diff, test_migration_ledger, test_banned_patterns);
10 characterization snapshots byte/event-identical; lint-imports 4 kept / 0 broken; grep
ratchets (`shell=True`, `ExecutionPolicy.check`, direct validator spawn) all = 0.

**REVIEW.md cross-check (mitigation evidence verified in source, not just claimed):**
- CR-01 (audit recorder never invoked — signature + sync/async mismatch): FIXED — single
  keyword-only step-free recorder contract `_noop_recorder` (`local.py:68-87`); sync→async
  adapter `_make_exec_recorder` (`engine.py:338-405`) wired at the host seam (`engine.py:1213`).
  Closes T-10-01-07 + the deny contract for T-10-01-01/02 + the VALIDATOR-DENY net T-10-04-02.
- WR-01 (timeout did not kill process group): FIXED — Popen+communicate + `os.killpg`
  (`local.py:336-341`). Closes T-10-01-04 containment.
- WR-02 (empty argv unaudited IndexError): FIXED — empty-argv deny guard (`local.py:291-293`).
  Closes T-10-01-02 edge.
- WR-04 (block with empty events silently not halting): FIXED — terminal `(None, outcome)`
  sentinel (`engine.py:2533-2545`). Hardens T-10-03-01/02 gate-halt observability.
- WR-03 (exec grant run-global, not per-step): documented as SPEC-locked D-03 run-scoped
  authorization at the host seam (`engine.py:1189-1199`); bounded by engineer-trust + run-level
  approval — not a default-deny break (consistent with T-10-03-05).

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| RISK-1 | T-10-01-05 | Interpreter-socket egress residual: an allow-listed interpreter can still open sockets at runtime. Policy.network=False + no net-capable tool on the allow-list + scrubbed env mitigate but do not hard-block; OS-level netns enforcement is the v2 ECS seam. Exec is engineer-only + security-gated. Documented at `local.py:273-277`. | 10-SPEC.md (N3 decision record, Req 3 EGRESS-DENY) | 2026-06-10 |
| RISK-2 | T-10-03-06 | Approval-payload disclosure residual: the D-04 payload is the exec POLICY snapshot (allow-list, caps, scrubbed-env note, egress-denied) — no creds, no dynamic argv preview. The allow-list IS the honest bound the approver evaluates. `_exec_policy_snapshot` (`approval.py:52-90`). | 10-SPEC.md (N3 decision record, Req 5 GATES / D-04) | 2026-06-10 |
| RISK-3 | T-10-04-04 | Sample-manifest palette residual: the exec-granting `sample_exec_workflow` manifest lives under `tests/agents/fixtures/` only and is NOT added to any production registry/catalog. Exec stays gate+trust-bound; nothing exec-related becomes user_allowed=True. | 10-SPEC.md (Req 7 VALIDATORS / SC-001) | 2026-06-10 |
| RISK-4 | IN-01 (→ T-10-05-03 mitigated) | REVIEW.md IN-01: `ExecRun` is imported for Base.metadata registration but omitted from `app/models/__init__.py.__all__`. Accepted — consistent with the existing import-only pattern for all Phase-8/9 audit models (GateEvent, HookRun, ValidationResult). No security impact; the registration (the security-relevant fact) is present. | 10-REVIEW.md (Info, accepted) | 2026-06-10 |
| RISK-5 | IN-02 (→ T-10-03-01/02 mitigated) | REVIEW.md IN-02: the SecurityGate runtime trust check (`getattr(step, "trust", "file")`) always resolves to "file" because the compiled Step carries no trust attribute, so condition (a) cannot fire at runtime. Accepted — the PRIMARY enforcement is the compiler's `_TRUSTED_SOURCES` check (T-10-02-01, verified at `compiler.py:323-336`); the runtime check is intentional defense-in-depth, documented at `security.py:91-93`. | 10-REVIEW.md (Info, accepted) | 2026-06-10 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-06-10 | 31 | 31 | 0 | gsd-security-auditor (Claude) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-06-10
