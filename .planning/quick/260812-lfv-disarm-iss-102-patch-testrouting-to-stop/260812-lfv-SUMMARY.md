---
phase: quick-260812-lfv
plan: 01
status: complete
requirements: [ISS-102]
branch: bugfix/spec-revision-context-loss
base_commit: d0c094f0
files_changed: 2
tasks_completed: 2
completed: 2026-08-12
---

# quick-260812-lfv — disarm ISS-102: stop offline Bedrock spend + add a live-client guard

**One-liner:** Two offline unit tests that reached the real AWS Bedrock `ConverseStream` API are
now cut off at the Concierge seam, and a root-conftest autouse guard makes *any* offline test
that constructs `ChatAnthropic` / `ChatBedrockConverse` / `ChatMistralAI` fail loudly by nodeid —
proven by a planted test, with zero movement in three test trees, the goldens, or the import
contracts.

## Why this was urgent

`TestRouting` never patched `run_commands._resolve_concierge`, so the endpoint resolved the REAL
`ConciergeCapability` (ctx `model=None`) → `build_model()` → `ChatBedrockConverse` → a live
`ConverseStream` call. Until today those calls died on an expired SSO token and cost nothing. AWS
SSO went live on this machine today, so the next suite run would have billed real money.

A second fact, verified during execution, is what makes the guard (not just the two-test fix) the
deliverable: **the suite has no offline-by-default state at all.** `AWS_REGION`
(`app/core/config.py:130`), `BEDROCK_INFERENCE_PROFILE_ID` (`:123`) and `BEDROCK_MODEL_ID`
(`:118`) are hardcoded **code** defaults and there is no `backend/.env`, so unsetting env vars
cannot make `build_model()` offline. The only thing that ever stood between this suite and a bill
was whether AWS credentials happened to resolve.

## The change — test infrastructure only (D7)

**Task 1 — `backend/tests/unit/test_chat_messages_endpoint.py`** (+23 lines, additions only).
One autouse fixture `_no_live_concierge`, placed as the first member of `class TestRouting`, doing
the byte-identical sibling call already used at `:439/:487/:539/:581/:615`:

```python
monkeypatch.setattr(rc_module, "_resolve_concierge", lambda: fake)
```

Class-placed rather than per-test because only 2 of the class's 8 methods reach the seam today but
any could tomorrow; patching the other 6 individually would be dead code (INV-12). Its pytest
scope stays the default `function` — a `scope="class"` fixture cannot request `monkeypatch`
(`ScopeMismatch`), so D1's "class-scoped" is placement, not pytest scope. The docstring records
the whole WHY so a future reader cannot delete it as noise.

**Task 2 — `backend/tests/conftest.py`** (+160 lines, additions only). Five members:

| Member | Role |
|---|---|
| `_CONSTRUCTS_BUT_NEVER_INVOKES` | nodeid → reason dict, seeded with exactly the 8 construct-only tests from CONTEXT F6 items 3–10 |
| `LiveModelClientConstructed(BaseException)` | the guard error |
| `_guarded_classes()` | `lru_cache(maxsize=1)`, resolves the 3 provider classes, each in its own `try/except (ImportError, AttributeError)` |
| `_blocked_init(nodeid, class_name)` | the replacement `__init__`, message naming test + class + three remedies |
| `_forbid_live_model_clients(request, monkeypatch)` | the autouse fixture |

Three design points that carry the weight:

- **`BaseException`, not `Exception`.** `app/agents/deep_agent_runner.py:586` is
  `except Exception as exc:  # noqa: BLE001 — mirror the legacy swallow`, which converts the
  exception into a yielded `{"type": "error"}` event at `:610-611`. That is *precisely* how the
  ISS-102 `ExpiredTokenException` surfaced as a log line instead of a test failure. An
  `Exception`-derived guard error would be swallowed identically and the test would pass silently.
  Verified on pytest 8.3.4: a custom `BaseException` subclass is reported as a normal `FAILED` and
  the session continues.
- **The three provider CLASSES, not `build_model`.** A `build_model` guard would be theatre:
  `agents/planner/smart_planner.py:173/:189/:196` bypasses `build_model()` entirely, and
  `deepagents.create_deep_agent(model="anthropic:...")` builds `ChatAnthropic` via langchain's own
  `init_chat_model` — six tests missed. It would also be defeated by the by-value
  `from app.agents.model_factory import build_model` imports at `deep_agent_runner.py:58` and
  `cached_invoke.py:44`.
- **Patch `__init__`, never the class object.** `isinstance()` keeps working
  (`deep_agent_runner._maybe_apply:234`, `cached_invoke:79`), `object.__new__(ChatBedrockConverse)`
  keeps working (`test_bedrock_cache_and_thinking.py::_bedrock_instance`), tests that swap the
  whole class attribute on the source module are unaffected, and monkeypatch restores it per test.

Allowances are exactly three (D5): `RUN_LIVE_BEDROCK=1`, the declared `requires_api_key` marker, or
**exact** nodeid membership in the dict. Exact matching only — no prefix or parametrize-suffix
stripping — so the dict **fails closed**: rename a test and it drops its exemption loudly.

## Acceptance — all eight rows OBSERVED

| # | Check | Required | Observed | Verdict |
|---|---|---|---|---|
| A1 | `tests/unit/test_chat_messages_endpoint.py` | 3 failed / 17 passed, same 3 ids | `3 failed, 17 passed, 1 warning in 1.37s`; ids = `test_clarify_waiting_routes_to_answers_seam`, `test_gate_paused_routes_to_gate_seam_approve`, `test_terminal_routes_to_revision` | PASS |
| A2 | same file, `log_cli_level=ERROR` | ZERO `ExpiredTokenException`/`ConverseStream` (was 2) | `0` | PASS |
| A3 | `tests/unit` whole tree | 62 failed / 1167 passed | `62 failed, 1167 passed, 3 warnings in 42.37s`; FAILED id set **identical** to `base_unit.txt`; 0 guard trips | PASS |
| A4 | `tests/agents tests/properties tests/integration` | 57/1723/42 and identical id set | `57 failed, 1723 passed, 42 skipped in 414.51s`; `diff` of the 57 FAILED/ERROR ids vs `base_agents.txt` **empty**; 0 guard trips | PASS |
| A5 | 5 characterization golden files | 10 passed | `10 passed, 1 warning in 38.06s` | PASS |
| A6 | goldens unmoved | empty status + 15 checksums | `git status --porcelain` empty; `shasum` diff vs `golden_before.txt` empty — re-checked again *after* all suites ran | PASS |
| A7 | `lint-imports` from `backend/` | 4 kept, 0 broken | `Contracts: 4 kept, 0 broken.` | PASS |
| A8 | planted-test demo | fails with the guard naming its nodeid | `LiveModelClientConstructed` raised at `model_factory.py:148` → `tests/conftest.py:125`, message carried `tests/unit/test_iss102_guard_plant.py::test_guard_fires_on_build_model` and `ChatBedrockConverse`; reported as `1 failed` (session continued); plant deleted, `git status` for it empty | PASS |

Two evidence points beyond what the plan required: the **`tests/unit` FAILED id set** was diffed
against the pre-change `base_unit.txt` and is identical (A3 asked only for counts), and both large
runs were grepped for `LiveModelClientConstructed` — **0 trips**, confirming the allow-list is
complete and the guard adds no reds anywhere.

Final `git status --porcelain`: exactly `backend/tests/conftest.py` and
`backend/tests/unit/test_chat_messages_endpoint.py`. `git diff --stat` = **183 insertions,
0 deletions**. No production file, no golden, no assertion, no deletion, no `xfail`, no `skip`.

## Expected reds left in place, deliberately

The two `TestRouting` tests **stay red, for a new reason**, exactly as CONTEXT F2 locked. They now
fail with `json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)` at
`resp.json()` — the endpoint returns a `text/event-stream` Concierge body, not the `answers`/`gate`
JSON they assert. That is `chat_router.route_chat_turn` behaving correctly: a bare-text turn at
`PHASE_CLARIFY_WAITING` must not be auto-submitted as a freeform clarify answer, and at
`PHASE_GATE_PAUSED` must not default to `approve`. These tests encode the **superseded pre-safety
contract**; reconciling a safety-critical routing contract is an owner decision, not this plan's.

`test_terminal_routes_to_revision` is untouched and still dies at `run_commands.py:2497` with
`AttributeError: '_FakeUser' object has no attribute 'tier'` (KAN-161/ISS-055; the `_FakeUser`
double at `:33` is stale). It never reached a model.

## Deviations from plan

**None.** Every decision D1–D7 was implemented literally. The locked BEFORE baselines were not
re-measured, and `$SCRATCH/base_agents.txt` was used directly as the A4 comparator as instructed
(no 7-minute re-capture). No package was installed. No production file was opened for edit.

## Carry to bookkeeping (filings, not work for this plan)

1. **The ISS-102 register row is wrong on two counts.** It names `test_terminal_routes_to_revision`
   (which never reaches a model — it dies at `run_commands.py:2497` on `_FakeUser.tier`), and it
   says "four attempts per run" when it is **two** calls (a grep miscount: 2 ERROR log lines + the
   same 2 exceptions echoed inside their tracebacks).
2. **New ISS row — the 8 construct-only tests.** A latent-hazard class: each constructs a real
   provider client and is one added `.ainvoke`/`.astream` away from live spend. Currently exempted
   by nodeid in `backend/tests/conftest.py::_CONSTRUCTS_BUT_NEVER_INVOKES`.
3. **New ISS row — the superseded routing contract.** The two `TestRouting` tests assert
   `answers`/`gate` where `chat_router.route_chat_turn` now deliberately returns `concierge`.
   Reconciling it is an owner decision.

## Self-Check: PASSED

- `backend/tests/conftest.py` — FOUND, contains `_CONSTRUCTS_BUT_NEVER_INVOKES`
- `backend/tests/unit/test_chat_messages_endpoint.py` — FOUND, contains `_resolve_concierge` in a
  class-placed autouse fixture
- `backend/tests/unit/test_iss102_guard_plant.py` — correctly ABSENT (temporary A8 plant, deleted)
