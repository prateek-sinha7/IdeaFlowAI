# Integration Contracts: Native `deepagents` Skills

**External services, webhooks, queues, cron jobs: None.** This feature adds no outbound
integration. The contracts below are with the `deepagents` library, the run filesystem, and the
model providers already in use.

---

## 1. `deepagents==0.6.7` — `SkillsMiddleware`

| Term | Value | Consequence if violated |
|---|---|---|
| Activation | `create_deep_agent(skills=[...])`, non-`None` ⇒ `SkillsMiddleware(backend, sources)` (`graph.py:715-716`) | `skills=None` ⇒ middleware absent ⇒ R-04 satisfied by construction |
| `sources` | POSIX directory paths relative to the backend root — we pass `["/skills"]` | A file path or a bare `SKILL.md` is never scanned |
| Layout | `<source>/<skill-name>/SKILL.md` (`middleware/skills.py:573-630`) | A flat file at the source root is **silently** not found |
| Frontmatter | Only `name`, `license`, `description`, `compatibility`, `metadata`, `allowed-tools` survive; everything else is dropped | Our synthesized frontmatter carries `name` + `description` only |
| `description` | > 1,024 chars silently truncated | We clamp and record an error rather than let it truncate unseen |
| Body | **Never injected.** Activation is the model calling `read_file` | R-03; unmeasured activation is D-01 |
| Caching | `before_agent` early-returns when `skills_metadata` is in state — loads once per thread | A resumed run keeps its original skill set (C-06, accepted) |
| `allowed-tools` | Parsed and printed, **never enforced** | Do not treat it as a permission mechanism |
| Preamble | Stock (C-08). Advertises script execution and supporting files we do not provide | D-04; mitigated by excluding `execute` at the tool filter |

**Version lock**: 0.6.7 (`requirements.txt:42`). Upgrading to 0.7.x is out of scope and
independently breaking (`write_file` overwrite semantics). Note the unrelated 0.7.5 install under
`/opt/homebrew` — verification must use the project venv.

---

## 2. Run filesystem

| Term | Value |
|---|---|
| Backend | `FilesystemBackend(root_dir=str(run_sandbox.root), virtual_mode=True)` (`deep_agent_runner.py:338-339`) |
| Mount | POSIX `/skills` ⇒ `<sandbox.root>/skills/` |
| Sandbox identity | `<RUNS_ROOT>/<user>/<run>/`, shared across all agents in a run; fan-out workers get an isolated `_ChildSandbox` root |
| Writer | `stage_skills`, called from `create_runner` for whichever sandbox is effective for that invocation |
| Idempotence | Content-compare then atomic write; N agents ⇒ 1 effective write (R-02) |
| Confinement | `RunSandbox.path_for` rejects traversal; `virtual_mode=True` confines the model's own fs tools (C-02) |
| Permissions | **No `FilesystemPermission` rules** (C-02). Agents can read and write `/skills/**` within the run sandbox (D-03, accepted) |
| Lifetime | Removed with the sandbox by `RunSandbox.cleanup()` |
| Never exposed | `backend/skills/global/` — the global catalog is read in-process and staged by value, never mounted |

---

## 3. Model providers

| Provider | Role here |
|---|---|
| Frontier (Bedrock/Anthropic via `build_model`) | Acceptance 6 — activation measurement |
| Ollama `qwen3.5:4b` (`OLLAMA=true`) | Acceptance 6 — the D-01 risk case |

No provider API changes. The only new provider-visible surface is the stock skills preamble plus
~66 tokens per advertised skill in each agent's system prompt, and the `read_file` calls the model
may choose to make. Token cost is estimated (`464 + 66 × n`), logged, emitted, and warned above
8,000 tok/agent — **never** a hard failure (R-16, C-05).

---

## 4. Events

One existing SSE event changes payload (`agent_skills` — see [`api-contract.md`](api-contract.md) §3).
No new event type, so `types/index.ts:107`, `lib/wsReplayState.ts:112` and the dashboard event
allow-list (`app/dashboard/page.tsx:693`) need no additions.

---

## 5. Jobs / cron / queues

None. Staging is synchronous inside runner construction. There is no background job, no scheduled
catalog sync, and no cache to invalidate beyond the existing in-process
`skills_catalog.clear_cache()` used by tests.
