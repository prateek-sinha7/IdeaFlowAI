$ git commit --file=/var/folders/fv/36z8hwhx79zbmd06_pbk4bvm0000gp/T/8B88AC27-B9B0-41A6-89FB-AF5BD57588BF

ruff (backend)...........................................................Failed
- hook id: ruff
- exit code: 1

backend/agents/execution_engine/clarify_engine.py:730:13: F601 Dictionary key literal `"target_audience"` repeated
    |
728 |                 ["React / Next.js (web)", "React Native / Flutter (mobile)", "Node.js / Python (backend)", "Cloud-native (AWS / Azure / GCP)", "No preference"],
729 |             ),
730 |             "target_audience": (
    |             ^^^^^^^^^^^^^^^^^ F601
731 |                 "Who is the primary audience for this?",
732 |                 ["Executive / C-Suite", "Technical team / Engineers", "Business stakeholders / Managers", "General public / Consumers", "Sales & Marketing team"],
    |
    = help: Remove repeated key literal `"target_audience"`

backend/agents/planner/smart_planner.py:321:49: W291 Trailing whitespace
    |
320 | ### 1. Topic Detection
321 | Does the brief contain a SPECIFIC topic/subject? 
    |                                                 ^ W291
322 | 
323 | A brief HAS a topic when it names something specific:
    |
    = help: Remove trailing whitespace

backend/agents/planner/smart_planner.py:325:49: W291 Trailing whitespace
    |
323 | A brief HAS a topic when it names something specific:
324 | - ✅ "Apple vs Samsung comparison" → has topic
325 | - ✅ "Q3 sales results for the board" → has topic  
    |                                                  ^^ W291
326 | - ✅ "hospital booking system" → has topic
327 | - ✅ "climate change impact" → has topic
    |
    = help: Remove trailing whitespace

backend/app/api/run_commands.py:598:48: F401 [*] `agents.execution_engine.engine.get_execution_engine` imported but unused
    |
596 |       8. Return 200 ``{"run_id": run_id}``.
597 |     """
598 |     from agents.execution_engine.engine import get_execution_engine
    |                                                ^^^^^^^^^^^^^^^^^^^^ F401
599 | 
600 |     db = _get_db()
    |
    = help: Remove unused import: `agents.execution_engine.engine.get_execution_engine`

backend/app/api/run_commands.py:2117:1: E402 Module level import not at top of file
     |
2115 | # SC-001 / INV-1: generic marker matching, never a hardcoded pipeline name.
2116 | # ---------------------------------------------------------------------------
2117 | import re as _re_title
     | ^^^^^^^^^^^^^^^^^^^^^^ E402
2118 | 
2119 | _REVISION_REQUEST_RE = _re_title.compile(
     |

backend/app/api/run_commands.py:2894:17: F841 Local variable `any_agent_errored` is assigned to but never used
     |
2892 |             raw_events.append((utype, update.get("data", {})))
2893 |             if utype == "agent_error":
2894 |                 any_agent_errored = True
     |                 ^^^^^^^^^^^^^^^^^ F841
2895 |                 if first_agent_error_msg is None:
2896 |                     first_agent_error_msg = update["data"].get("error") or "Agent execution error"
     |
     = help: Remove assignment to unused variable `any_agent_errored`

backend/app/api/runs.py:349:1: W293 [*] Blank line contains whitespace
    |
347 |         .filter(WorkflowRun.user_id == current_user.id)
348 |     )
349 |     
    | ^^^^ W293
350 |     if type:
351 |         query = query.filter(WorkflowRun.type == type)
    |
    = help: Remove whitespace from blank line

backend/app/api/runs.py:354:1: W293 [*] Blank line contains whitespace
    |
352 |     if status_filter:
353 |         query = query.filter(WorkflowRun.status == status_filter)
354 |     
    | ^^^^ W293
355 |     # Count before applying limit/offset so the total reflects filters.
356 |     # Uses the same WHERE clause as the page query — no extra round trip on a
    |
    = help: Remove whitespace from blank line

backend/tests/agents/test_capability_resolution.py:63:12: B009 [*] Do not call `getattr` with a constant attribute value. It is not any safer than normal property access.
   |
61 | ) → None:
62 |     impl = reg.resolve(kind, name)
63 |     assert getattr(impl, "name") == name
   |            ^^^^^^^^^^^^^^^^^^^^^ B009
   |
   = help: Replace `getattr` with attribute access

backend/tests/agents/test_restart_resume.py:303:13: E731 Do not assign a `lambda` expression, use a `def`
    |
302 |             _KS.run_fanout = _wrapped_fanout
303 |             _restore_fanout = lambda: setattr(_KS, "run_fanout", _orig_fanout)
    |             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ E731
304 |         else:
305 |             _restore_fanout = lambda: None
    |
    = help: Rewrite `_restore_fanout` as a `def`

backend/tests/agents/test_restart_resume.py:305:13: E731 Do not assign a `lambda` expression, use a `def`
    |
303 |             _restore_fanout = lambda: setattr(_KS, "run_fanout", _orig_fanout)
304 |         else:
305 |             _restore_fanout = lambda: None
    |             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ E731
306 | 
307 |         # Point the module-level SessionLocal (used by restore_non_terminal_runs +
    |
    = help: Rewrite `_restore_fanout` as a `def`

backend/tests/agents/test_restart_resume.py:723:5: F841 Local variable `events` is assigned to but never used
    |
721 |     step.task_source = type("TS", (), {"source_step": "plan", "parser": "json_tasks"})()
722 | 
723 |     events = [ev async for ev in strat.run(step, ctx)]
    |     ^^^^^^ F841
724 | 
725 |     # The strategy must have recorded a wave_run for step2's waves (NOT skipped them).
    |
    = help: Remove assignment to unused variable `events`

backend/tests/agents/test_restart_resume.py:1826:5: F841 Local variable `row_id` is assigned to but never used
     |
1824 |                     producer_agent="wave-worker", task_id="1")
1825 |     # The wave_runs row is still `running` — the merge never ran (the discriminator).
1826 |     row_id = await store.record_wave_run(
     |     ^^^^^^ F841
1827 |         run_id, step="build", wave_index=0, task_ids=["t1", "t2"], status="running"
1828 |     )
     |
     = help: Remove assignment to unused variable `row_id`

Found 13 errors.
[*] 4 fixable with the `--fix` option (8 hidden fixes can be enabled with the `--unsafe-fixes` option).

pyright (backend imports)................................................Failed
- hook id: pyright
- exit code: 1

/Users/bilala/Developer/Projects/VELOCITY-AI/backend/app/api/user_workflows.py
  /Users/bilala/Developer/Projects/VELOCITY-AI/backend/app/api/user_workflows.py:44:6 - error: Import "fastapi" could not be resolved (reportMissingImports)
  /Users/bilala/Developer/Projects/VELOCITY-AI/backend/app/api/user_workflows.py:45:6 - error: Import "pydantic" could not be resolved (reportMissingImports)
  /Users/bilala/Developer/Projects/VELOCITY-AI/backend/app/api/user_workflows.py:46:6 - error: Import "sqlalchemy.orm" could not be resolved (reportMissingImports)
3 errors, 0 warnings, 0 informations 
WARNING: there is a new pyright version available (v1.1.391 → v1.1.411).
Please install the new version or set PYRIGHT_PYTHON_FORCE_VERSION to `latest`

/Users/bilala/Developer/Projects/VELOCITY-AI/backend/app/api/runs.py
  /Users/bilala/Developer/Projects/VELOCITY-AI/backend/app/api/runs.py:27:6 - error: Import "fastapi" could not be resolved (reportMissingImports)
  /Users/bilala/Developer/Projects/VELOCITY-AI/backend/app/api/runs.py:28:6 - error: Import "pydantic" could not be resolved (reportMissingImports)
  /Users/bilala/Developer/Projects/VELOCITY-AI/backend/app/api/runs.py:29:6 - error: Import "sqlalchemy.orm" could not be resolved (reportMissingImports)
  /Users/bilala/Developer/Projects/VELOCITY-AI/backend/app/api/runs.py:391:10 - error: Import "fastapi.responses" could not be resolved (reportMissingImports)
/Users/bilala/Developer/Projects/VELOCITY-AI/backend/agents/execution_engine/clarify_engine.py
  /Users/bilala/Developer/Projects/VELOCITY-AI/backend/agents/execution_engine/clarify_engine.py:544:18 - error: Import "langchain_core.messages" could not be resolved (reportMissingImports)
  /Users/bilala/Developer/Projects/VELOCITY-AI/backend/agents/execution_engine/clarify_engine.py:867:14 - error: Import "sqlalchemy.exc" could not be resolved (reportMissingImports)
/Users/bilala/Developer/Projects/VELOCITY-AI/backend/agents/planner/smart_planner.py
  /Users/bilala/Developer/Projects/VELOCITY-AI/backend/agents/planner/smart_planner.py:160:18 - error: Import "langchain_anthropic" could not be resolved (reportMissingImports)
  /Users/bilala/Developer/Projects/VELOCITY-AI/backend/agents/planner/smart_planner.py:169:14 - error: Import "langchain_aws" could not be resolved (reportMissingImports)
  /Users/bilala/Developer/Projects/VELOCITY-AI/backend/agents/planner/smart_planner.py:393:14 - error: Import "langchain_core.messages" could not be resolved (reportMissingImports)
9 errors, 0 warnings, 0 informations 
WARNING: there is a new pyright version available (v1.1.391 → v1.1.411).
Please install the new version or set PYRIGHT_PYTHON_FORCE_VERSION to `latest`

0 errors, 0 warnings, 0 informations 
WARNING: there is a new pyright version available (v1.1.391 → v1.1.411).
Please install the new version or set PYRIGHT_PYTHON_FORCE_VERSION to `latest`

0 errors, 0 warnings, 0 informations 
WARNING: there is a new pyright version available (v1.1.391 → v1.1.411).
Please install the new version or set PYRIGHT_PYTHON_FORCE_VERSION to `latest`

/Users/bilala/Developer/Projects/VELOCITY-AI/backend/app/api/run_commands.py
  /Users/bilala/Developer/Projects/VELOCITY-AI/backend/app/api/run_commands.py:46:6 - error: Import "fastapi" could not be resolved (reportMissingImports)
  /Users/bilala/Developer/Projects/VELOCITY-AI/backend/app/api/run_commands.py:47:6 - error: Import "pydantic" could not be resolved (reportMissingImports)
  /Users/bilala/Developer/Projects/VELOCITY-AI/backend/app/api/run_commands.py:1761:14 - error: Import "sse_starlette" could not be resolved (reportMissingImports)
  /Users/bilala/Developer/Projects/VELOCITY-AI/backend/app/api/run_commands.py:3379:10 - error: Import "sse_starlette" could not be resolved (reportMissingImports)
4 errors, 0 warnings, 0 informations 
WARNING: there is a new pyright version available (v1.1.391 → v1.1.411).
Please install the new version or set PYRIGHT_PYTHON_FORCE_VERSION to `latest`

/Users/bilala/Developer/Projects/VELOCITY-AI/backend/agents/loader.py
  /Users/bilala/Developer/Projects/VELOCITY-AI/backend/agents/loader.py:22:8 - error: Import "frontmatter" could not be resolved (reportMissingImports)
1 error, 0 warnings, 0 informations 
WARNING: there is a new pyright version available (v1.1.391 → v1.1.411).
Please install the new version or set PYRIGHT_PYTHON_FORCE_VERSION to `latest`

/Users/bilala/Developer/Projects/VELOCITY-AI/backend/app/api/prototype_templates.py
  /Users/bilala/Developer/Projects/VELOCITY-AI/backend/app/api/prototype_templates.py:18:6 - error: Import "fastapi" could not be resolved (reportMissingImports)
  /Users/bilala/Developer/Projects/VELOCITY-AI/backend/app/api/prototype_templates.py:19:6 - error: Import "fastapi.responses" could not be resolved (reportMissingImports)
  /Users/bilala/Developer/Projects/VELOCITY-AI/backend/app/api/prototype_templates.py:20:6 - error: Import "pydantic" could not be resolved (reportMissingImports)
  /Users/bilala/Developer/Projects/VELOCITY-AI/backend/app/api/prototype_templates.py:336:12 - error: Import "httpx" could not be resolved (reportMissingImports)
4 errors, 0 warnings, 0 informations 
WARNING: there is a new pyright version available (v1.1.391 → v1.1.411).
Please install the new version or set PYRIGHT_PYTHON_FORCE_VERSION to `latest`

0 errors, 0 warnings, 0 informations 
WARNING: there is a new pyright version available (v1.1.391 → v1.1.411).
Please install the new version or set PYRIGHT_PYTHON_FORCE_VERSION to `latest`

0 errors, 0 warnings, 0 informations 
WARNING: there is a new pyright version available (v1.1.391 → v1.1.411).
Please install the new version or set PYRIGHT_PYTHON_FORCE_VERSION to `latest`

eslint (frontend)........................................................Failed
- hook id: eslint
- exit code: 1

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/app/admin/page.tsx
   54:21  warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/app/admin/page.tsx:54:21
  52 |
  53 |   // Sync if parent updates
> 54 |   useEffect(() => { setLocalTier(currentTier); }, [currentTier]);
     |                     ^^^^^^^^^^^^ Avoid calling setState() directly within an effect
  55 |
  56 |   const handleSelect = async (tier: string) => {
  57 |     if (tier === localTier) { setOpen(false); return; }                                                                                             react-hooks/set-state-in-effect
  143:7   error    Error: Cannot access variable before it is declared

`loadUsers` is accessed before it is declared, which prevents the earlier access from updating when this value changes over time.

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/app/admin/page.tsx:143:7
  141 |     getMe(token).then(user => {
  142 |       if (!user.is_admin) { router.replace("/dashboard"); return; }
> 143 |       loadUsers(token);
      |       ^^^^^^^^^ `loadUsers` accessed before it is declared
  144 |     }).catch(() => router.replace("/login"));
  145 |   }, [router]);
  146 |

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/app/admin/page.tsx:147:3
  145 |   }, [router]);
  146 |
> 147 |   const loadUsers = async (token?: string) => {
      |   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
> 148 |     const t = token ?? getToken();
      | ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
> 149 |     if (!t) return;
      …
      | ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
> 158 |     }
      | ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
> 159 |   };
      | ^^^^^ `loadUsers` is declared here
  160 |
  161 |   const handleUpdateTier = async (userId: string, tier: string) => {
  162 |     const token = getToken();  react-hooks/immutability
  145:6   warning  React Hook useEffect has a missing dependency: 'loadUsers'. Either include it or remove the dependency array                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  react-hooks/exhaustive-deps

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/app/dashboard/page.tsx
     5:29  warning  'addMessage' is defined but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     @typescript-eslint/no-unused-vars
     5:61  warning  'createChat' is defined but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     @typescript-eslint/no-unused-vars
    35:15  warning  'PerRunState' is defined but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
    80:10  warning  'token' is assigned a value but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 @typescript-eslint/no-unused-vars
    87:5   warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/app/dashboard/page.tsx:87:5
  85 |   // this is the earliest safe point to read localStorage on the client.
  86 |   useEffect(() => {
> 87 |     setMounted(true);
     |     ^^^^^^^^^^ Avoid calling setState() directly within an effect
  88 |   }, []);
  89 |
  90 |   // Chat state (secondary — used for refinement)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 react-hooks/set-state-in-effect
   125:23  warning  'setCurrentMode' is assigned a value but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        @typescript-eslint/no-unused-vars
   157:10  warning  'waveGroups' is assigned a value but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   253:9   warning  'updateRunQuestionnaire' is assigned a value but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                @typescript-eslint/no-unused-vars
   266:9   warning  'updateRunReviewGate' is assigned a value but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   @typescript-eslint/no-unused-vars
   278:9   warning  'projectRunStateToUI' is assigned a value but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   @typescript-eslint/no-unused-vars
   343:10  warning  'questionnaireData' is assigned a value but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     @typescript-eslint/no-unused-vars
   358:10  warning  'reviewGateData' is assigned a value but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        @typescript-eslint/no-unused-vars
   402:5   warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/app/dashboard/page.tsx:402:5
  400 |       return;
  401 |     }
> 402 |     setToken(storedToken);
      |     ^^^^^^^^ Avoid calling setState() directly within an effect
  403 |     setIsAuthenticated(true);
  404 |     // Signals the Redux store that the user is signed in — the agents
  405 |     // slice's listener middleware reacts to this by fetching the agent                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              react-hooks/set-state-in-effect
   790:16  error    Error: Cannot access variable before it is declared

`runStore` is accessed before it is declared, which prevents the earlier access from updating when this value changes over time.

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/app/dashboard/page.tsx:790:16
  788 |             const prevViewedHasClarify =
  789 |               !!prevTrackedId &&
> 790 |               (runStore.get(prevTrackedId)?.questionnaireData != null);
      |                ^^^^^^^^ `runStore` accessed before it is declared
  791 |             // Point all tracking refs at the new run immediately — same as .then()
  792 |             trackedRunIdRef.current = incomingRunId;
  793 |             activelyBuildingRunIdRef.current = incomingRunId;

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/app/dashboard/page.tsx:1620:3
  1618 |   // run also triggers React re-renders. store.switchViewTo(runId) atomically
  1619 |   // projects the new run's state to the UI — no async gap, no race.
> 1620 |   const runStore = useRunStateStore();
       |   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ `runStore` is declared here
  1621 |   // Convenience: the viewed run's state (what the UI actually renders).
  1622 |   // Non-contamination-prone fields (pipelineState, waveGroups) still go through
  1623 |   // the existing useWorkflow / waveGroups path which is already gated by                                                                                                                                                                                                                                                                 react-hooks/immutability
  1547:11  error    Error: Cannot access variable before it is declared

`retainAgentEdit` is accessed before it is declared, which prevents the earlier access from updating when this value changes over time.

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/app/dashboard/page.tsx:1547:11
  1545 |           const { agentId, editedContent } = pendingGateEditRef.current;
  1546 |           pendingGateEditRef.current = null;
> 1547 |           retainAgentEdit(agentId, editedContent);
       |           ^^^^^^^^^^^^^^^ `retainAgentEdit` accessed before it is declared
  1548 |         }
  1549 |         // Clear in the store too
  1550 |         const approvedSrcRunId = (msg as unknown as Record<string, unknown>)._sourceRunId as string | undefined ?? sourceRunId;

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/app/dashboard/page.tsx:1607:161
  1605 |
  1606 |   // Workflow pipeline state
> 1607 |   const { pipelineState, startPipeline, resetPipeline, isRunning: isPipelineRunning, handleMessage: handlePipelineMsg, submitQuestionnaire, retainClarifyRound, retainAgentEdit, reconcileTerminalStatus } = useWorkflow();
       |                                                                                                                                                                 ^^^^^^^^^^^^^^^ `retainAgentEdit` is declared here
  1608 |   // KAN-98: store pending gate edits so review_gate_approved can apply them to
  1609 |   // the live agent state (planAgent.output etc.) for the Thinking tab display.
  1610 |   const pendingGateEditRef = useRef<{ agentId: string; editedContent: string } | null>(null);  react-hooks/immutability
  1584:6   warning  React Hook useCallback has missing dependencies: 'getRunViewState', 'retainAgentEdit', and 'runStore'. Either include them or remove the dependency array                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  react-hooks/exhaustive-deps
  1607:67  warning  'isPipelineRunning' is assigned a value but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     @typescript-eslint/no-unused-vars
  1626:9   warning  'viewedRun' is assigned a value but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             @typescript-eslint/no-unused-vars
  1632:5   error    Error: This value cannot be modified

Modifying a value previously passed as an argument to a hook is not allowed. Consider moving the modification before calling the hook.

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/app/dashboard/page.tsx:1632:5
  1630 |   const runStoreHandleFrameRef = useRef(runStore.handleFrame);
  1631 |   useEffect(() => {
> 1632 |     runStoreHandleFrameRef.current = runStore.handleFrame;
       |     ^^^^^^^^^^^^^^^^^^^^^^ `runStoreHandleFrameRef` cannot be modified
  1633 |   }, [runStore.handleFrame]);
  1634 |
  1635 |   const runStoreSwitchViewToRef = useRef(runStore.switchViewTo);                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   react-hooks/immutability
  1637:5   error    Error: This value cannot be modified

Modifying a value previously passed as an argument to a hook is not allowed. Consider moving the modification before calling the hook.

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/app/dashboard/page.tsx:1637:5
  1635 |   const runStoreSwitchViewToRef = useRef(runStore.switchViewTo);
  1636 |   useEffect(() => {
> 1637 |     runStoreSwitchViewToRef.current = runStore.switchViewTo;
       |     ^^^^^^^^^^^^^^^^^^^^^^^ `runStoreSwitchViewToRef` cannot be modified
  1638 |   }, [runStore.switchViewTo]);
  1639 |
  1640 |   // Keep pipeline handler ref in sync                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      react-hooks/immutability
  1804:5   error    Error: This value cannot be modified

Modifying a value previously passed as an argument to a hook is not allowed. Consider moving the modification before calling the hook.

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/app/dashboard/page.tsx:1804:5
  1802 |   const getRunChatLastSeqRef = useRef<(() => number) | null>(null);
  1803 |   useEffect(() => {
> 1804 |     getRunChatLastSeqRef.current = getRunChatLastSeq;
       |     ^^^^^^^^^^^^^^^^^^^^ `getRunChatLastSeqRef` cannot be modified
  1805 |   }, [getRunChatLastSeq]);
  1806 |
  1807 |   // The nonce'd deep-link seam (borrow #6): the lane's result cards call                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 react-hooks/immutability
  1887:3   warning  Unused eslint-disable directive (no problems were reported from 'react-hooks/exhaustive-deps')
  1961:3   warning  Unused eslint-disable directive (no problems were reported from 'react-hooks/exhaustive-deps')
  2141:5   warning  React Hook useCallback has a missing dependency: 'runStore'. Either include it or remove the dependency array                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              react-hooks/exhaustive-deps
  2165:5   warning  Unused eslint-disable directive (no problems were reported from 'react-hooks/exhaustive-deps')
  2535:5   warning  React Hook useCallback has missing dependencies: 'pipelineState.pipelineRunId', 'reconcileTerminalStatus', and 'runStore'. Either include them or remove the dependency array                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              react-hooks/exhaustive-deps
  2812:11  error    Error: This value cannot be modified

Modifying a value previously passed as an argument to a hook is not allowed. Consider moving the modification before calling the hook.

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/app/dashboard/page.tsx:2812:11
  2810 |         const activeGate = runStore.viewed.reviewGateData;
  2811 |         if (editedContent && activeGate) {
> 2812 |           pendingGateEditRef.current = { agentId: activeGate.agentId, editedContent };
       |           ^^^^^^^^^^^^^^^^^^ `pendingGateEditRef` cannot be modified
  2813 |         }
  2814 |         void postGate(getToken() ?? "", activeGate?.pipelineRunId ?? "", {
  2815 |           gate_key: gateKey,                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  react-hooks/immutability

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/app/handoff/settings/page.tsx
  29:5  warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/app/handoff/settings/page.tsx:29:5
  27 |       return;
  28 |     }
> 29 |     setAuthed(true);
     |     ^^^^^^^^^ Avoid calling setState() directly within an effect
  30 |   }, [router]);
  31 |
  32 |   if (!authed) return null;  react-hooks/set-state-in-effect

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/app/login/page.tsx
  47:11  warning  Using `<img>` could result in slower LCP and higher bandwidth. Consider using `<Image />` from `next/image` or a custom image loader to automatically optimize images. This may incur additional usage or cost from your provider. See: https://nextjs.org/docs/messages/no-img-element  @next/next/no-img-element

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/app/preview-fullscreen/page.tsx
  32:7  warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/app/preview-fullscreen/page.tsx:32:7
  30 |     const params = new URLSearchParams(window.location.search);
  31 |     if (params.get("error") === "quota") {
> 32 |       setState("quota");
     |       ^^^^^^^^ Avoid calling setState() directly within an effect
  33 |       return;
  34 |     }
  35 |  react-hooks/set-state-in-effect

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/app/workflow/page.tsx
  16:10  warning  'token' is assigned a value but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             @typescript-eslint/no-unused-vars
  26:5   warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/app/workflow/page.tsx:26:5
  24 |       return;
  25 |     }
> 26 |     setToken(storedToken);
     |     ^^^^^^^^ Avoid calling setState() directly within an effect
  27 |     setIsAuthenticated(true);
  28 |   }, [router]);
  29 |  react-hooks/set-state-in-effect

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/analytics/AnalyticsPage.tsx
   71:21  warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/analytics/AnalyticsPage.tsx:71:21
  69 |   const [mounted, setMounted] = useState(false);
  70 |
> 71 |   useEffect(() => { setMounted(true); }, []);
     |                     ^^^^^^^^^^ Avoid calling setState() directly within an effect
  72 |
  73 |   useEffect(() => {
  74 |     if (!mounted) return;                                        react-hooks/set-state-in-effect
   75:24  warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/analytics/AnalyticsPage.tsx:75:24
  73 |   useEffect(() => {
  74 |     if (!mounted) return;
> 75 |     if (value === 0) { setDisplay(0); return; }
     |                        ^^^^^^^^^^ Avoid calling setState() directly within an effect
  76 |     const duration = 700;
  77 |     const startTs = performance.now();
  78 |     let raf = 0;  react-hooks/set-state-in-effect
  131:7   warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/analytics/AnalyticsPage.tsx:131:7
  129 |     const token = getToken();
  130 |     if (!token) {
> 131 |       setError("Not authenticated.");
      |       ^^^^^^^^ Avoid calling setState() directly within an effect
  132 |       setLoading(false);
  133 |       return;
  134 |     }                                                           react-hooks/set-state-in-effect

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/catalog/HomeLaunchGrid.test.tsx
  29:10  warning  '_token' is defined but never used  @typescript-eslint/no-unused-vars
  29:27  warning  '_range' is defined but never used  @typescript-eslint/no-unused-vars
  36:10  warning  '_token' is defined but never used  @typescript-eslint/no-unused-vars
  36:27  warning  '_opts' is defined but never used   @typescript-eslint/no-unused-vars

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/catalog/HomeLaunchGrid.tsx
   21:41  warning  'Plus' is defined but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             @typescript-eslint/no-unused-vars
   21:53  warning  'Paperclip' is defined but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        @typescript-eslint/no-unused-vars
   21:64  warning  'Sparkles' is defined but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         @typescript-eslint/no-unused-vars
   21:74  warning  'X' is defined but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                @typescript-eslint/no-unused-vars
   99:3   warning  'brief' is defined but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
  100:3   warning  'onBriefChange' is defined but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
  101:3   warning  'onBuild' is defined but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          @typescript-eslint/no-unused-vars
  150:7   warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/catalog/HomeLaunchGrid.tsx:150:7
  148 |     if (recentRunsProp && recentRunsProp.length > 0) {
  149 |       const sliced = recentRunsProp.slice(0, RECENTS_LIMIT);
> 150 |       setRecents(sliced);
      |       ^^^^^^^^^^ Avoid calling setState() directly within an effect
  151 |       writeCache(CACHE_KEY_RECENTS, sliced);
  152 |     }
  153 |   }, [recentRunsProp]);                                                                                                react-hooks/set-state-in-effect
  160:7   warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/catalog/HomeLaunchGrid.tsx:160:7
  158 |     if ((!recentRunsProp || recentRunsProp.length === 0) && reduxRecentRuns.length > 0 && recents.length === 0) {
  159 |       const sliced = reduxRecentRuns.slice(0, RECENTS_LIMIT);
> 160 |       setRecents(sliced);
      |       ^^^^^^^^^^ Avoid calling setState() directly within an effect
  161 |       writeCache(CACHE_KEY_RECENTS, sliced);
  162 |     }
  163 |   // eslint-disable-next-line react-hooks/exhaustive-deps  react-hooks/set-state-in-effect

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/chat/ChatAttachments.tsx
  175:15  warning  Using `<img>` could result in slower LCP and higher bandwidth. Consider using `<Image />` from `next/image` or a custom image loader to automatically optimize images. This may incur additional usage or cost from your provider. See: https://nextjs.org/docs/messages/no-img-element  @next/next/no-img-element

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/chat/ChatInput.tsx
  52:37  warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/chat/ChatInput.tsx:52:37
  50 |   const { isListening, transcript, startListening, stopListening, isSupported: speechSupported } = useSpeechRecognition();
  51 |
> 52 |   useEffect(() => { if (transcript) setValue(transcript); }, [transcript]);
     |                                     ^^^^^^^^ Avoid calling setState() directly within an effect
  53 |
  54 |   useEffect(() => {
  55 |     const handleClickOutside = (e: MouseEvent) => {  react-hooks/set-state-in-effect

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/chat/InlineClarifyActions.tsx
   24:34  warning  'useMemo' is defined but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        @typescript-eslint/no-unused-vars
   86:5   warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/chat/InlineClarifyActions.tsx:86:5
  84 |   // Reset on a fresh clarify round (new question set).
  85 |   useEffect(() => {
> 86 |     setAnswers({});
     |     ^^^^^^^^^^ Avoid calling setState() directly within an effect
  87 |     setSubmitted(false);
  88 |   }, [questions]);
  89 |  react-hooks/set-state-in-effect
  212:34  error    React Hook "useRecommended" cannot be called inside a callback. React Hooks must be called in a React function component or a custom React Hook function                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   react-hooks/rules-of-hooks

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/chat/InlineGateActions.tsx
  139:5  warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/chat/InlineGateActions.tsx:139:5
  137 |   // latched, and the user faces a live gate with every action disabled.
  138 |   useEffect(() => {
> 139 |     setEditedContent(output);
      |     ^^^^^^^^^^^^^^^^ Avoid calling setState() directly within an effect
  140 |     setHasEdits(false);
  141 |     setShowEdit(false);
  142 |     setShowRequestChanges(false);  react-hooks/set-state-in-effect

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/chat/RunChatLane.fix192.test.tsx
  12:37  warning  'act' is defined but never used  @typescript-eslint/no-unused-vars

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/chat/RunChatLane.tsx
   353:10  warning  'classifyFreeText' is defined but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        @typescript-eslint/no-unused-vars
   353:27  warning  '_text' is defined but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   @typescript-eslint/no-unused-vars
  1087:3   warning  'gate' is defined but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
  1088:3   warning  'onApprove' is defined but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               @typescript-eslint/no-unused-vars
  1089:3   warning  'onReject' is defined but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                @typescript-eslint/no-unused-vars
  1090:3   warning  'onRedo' is defined but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  @typescript-eslint/no-unused-vars
  1091:3   warning  'onUpdateSpecs' is defined but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           @typescript-eslint/no-unused-vars
  1093:3   warning  'onSubmitAnswers' is defined but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         @typescript-eslint/no-unused-vars
  1094:3   warning  'onSkipClarify' is defined but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           @typescript-eslint/no-unused-vars
  1095:3   warning  'onCancelWorkflow' is defined but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        @typescript-eslint/no-unused-vars
  1167:44  warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/chat/RunChatLane.tsx:1167:44
  1165 |     if (!replyPending) return;
  1166 |     const last = messages[messages.length - 1];
> 1167 |     if (last && last.role === "assistant") setReplyPending(false);
       |                                            ^^^^^^^^^^^^^^^ Avoid calling setState() directly within an effect
  1168 |   }, [messages, replyPending]);
  1169 |
  1170 |   // Auto-collapse the Pipeline mini when the user sends a chat message so the  react-hooks/set-state-in-effect
  1173:23  warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/chat/RunChatLane.tsx:1173:23
  1171 |   // Concierge reply is front-and-center. The user can re-expand it by clicking.
  1172 |   useEffect(() => {
> 1173 |     if (replyPending) setPipelineMiniCollapsed(true);
       |                       ^^^^^^^^^^^^^^^^^^^^^^^^ Avoid calling setState() directly within an effect
  1174 |   }, [replyPending]);
  1175 |
  1176 |   // Bind the flag to the VIEWED run: RunChatLane does NOT remount per run (no               react-hooks/set-state-in-effect
  1183:5   warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/chat/RunChatLane.tsx:1183:5
  1181 |   const viewedRunId = pipelineState?.pipelineRunId;
  1182 |   useEffect(() => {
> 1183 |     setReplyPending(false);
       |     ^^^^^^^^^^^^^^^ Avoid calling setState() directly within an effect
  1184 |   }, [viewedRunId]);
  1185 |
  1186 |   // Safety net for the ERROR path: sendMessage is fire-and-forget/void, so if the                                                                                               react-hooks/set-state-in-effect
  1277:15  warning  'runId' is assigned a value but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          @typescript-eslint/no-unused-vars
  1318:5   warning  React Hook useCallback has a missing dependency: 'suggestions'. Either include it or remove the dependency array                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    react-hooks/exhaustive-deps
  1338:34  warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/chat/RunChatLane.tsx:1338:34
  1336 |   // (e.g. the user started a new chain pipeline).
  1337 |   useEffect(() => {
> 1338 |     if (runState !== "complete") setChainPickerOpen(false);
       |                                  ^^^^^^^^^^^^^^^^^^ Avoid calling setState() directly within an effect
  1339 |   }, [runState]);
  1340 |
  1341 |   // Failed-lane composer send — a change instruction that feeds the reopen /                                       react-hooks/set-state-in-effect
  1520:19  warning  'workflowDisplayName' is assigned a value but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/chat/runtime/useMeasuredVirtualWindow.ts
   98:7   error  'startIndex' is never reassigned. Use 'const' instead                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         prefer-const
  171:14  error  Error: Cannot access refs during render

React refs are values that are not needed for rendering. Refs should only be accessed outside of render, such as in event handlers or effects. Accessing a ref value (the `current` property) during render can cause your component not to update as expected (https://react.dev/reference/react/useRef).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/chat/runtime/useMeasuredVirtualWindow.ts:171:14
  169 |   }
  170 |
> 171 |   const el = scrollRef.current;
      |              ^^^^^^^^^^^^^^^^^ Cannot access ref value during render
  172 |   const scrollTop = el?.scrollTop ?? 0;
  173 |   const viewport = el?.clientHeight ?? 0;
  174 |                                                  react-hooks/refs
  172:21  error  Error: Cannot access refs during render

React refs are values that are not needed for rendering. Refs should only be accessed outside of render, such as in event handlers or effects. Accessing a ref value (the `current` property) during render can cause your component not to update as expected (https://react.dev/reference/react/useRef).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/chat/runtime/useMeasuredVirtualWindow.ts:172:21
  170 |
  171 |   const el = scrollRef.current;
> 172 |   const scrollTop = el?.scrollTop ?? 0;
      |                     ^^^^^^^^^^^^^ Cannot access ref value during render
  173 |   const viewport = el?.clientHeight ?? 0;
  174 |
  175 |   const window = computeWindow(                   react-hooks/refs
  173:20  error  Error: Cannot access refs during render

React refs are values that are not needed for rendering. Refs should only be accessed outside of render, such as in event handlers or effects. Accessing a ref value (the `current` property) during render can cause your component not to update as expected (https://react.dev/reference/react/useRef).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/chat/runtime/useMeasuredVirtualWindow.ts:173:20
  171 |   const el = scrollRef.current;
  172 |   const scrollTop = el?.scrollTop ?? 0;
> 173 |   const viewport = el?.clientHeight ?? 0;
      |                    ^^ Cannot access ref value during render
  174 |
  175 |   const window = computeWindow(
  176 |     itemCount,                react-hooks/refs
  173:20  error  Error: Cannot access refs during render

React refs are values that are not needed for rendering. Refs should only be accessed outside of render, such as in event handlers or effects. Accessing a ref value (the `current` property) during render can cause your component not to update as expected (https://react.dev/reference/react/useRef).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/chat/runtime/useMeasuredVirtualWindow.ts:173:20
  171 |   const el = scrollRef.current;
  172 |   const scrollTop = el?.scrollTop ?? 0;
> 173 |   const viewport = el?.clientHeight ?? 0;
      |                    ^^^^^^^^^^^^^^^^ Cannot access ref value during render
  174 |
  175 |   const window = computeWindow(
  176 |     itemCount,  react-hooks/refs
  177:5   error  Error: Cannot access refs during render

React refs are values that are not needed for rendering. Refs should only be accessed outside of render, such as in event handlers or effects. Accessing a ref value (the `current` property) during render can cause your component not to update as expected (https://react.dev/reference/react/useRef).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/chat/runtime/useMeasuredVirtualWindow.ts:177:5
  175 |   const window = computeWindow(
  176 |     itemCount,
> 177 |     scrollTop,
      |     ^^^^^^^^^ Passing a ref to a function may read its value during render
  178 |     viewport,
  179 |     heights.current,
  180 |     estimate,                                                    react-hooks/refs
  178:5   error  Error: Cannot access refs during render

React refs are values that are not needed for rendering. Refs should only be accessed outside of render, such as in event handlers or effects. Accessing a ref value (the `current` property) during render can cause your component not to update as expected (https://react.dev/reference/react/useRef).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/chat/runtime/useMeasuredVirtualWindow.ts:178:5
  176 |     itemCount,
  177 |     scrollTop,
> 178 |     viewport,
      |     ^^^^^^^^ Passing a ref to a function may read its value during render
  179 |     heights.current,
  180 |     estimate,
  181 |     overscan,                                                                       react-hooks/refs
  179:5   error  Error: Cannot access refs during render

React refs are values that are not needed for rendering. Refs should only be accessed outside of render, such as in event handlers or effects. Accessing a ref value (the `current` property) during render can cause your component not to update as expected (https://react.dev/reference/react/useRef).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/chat/runtime/useMeasuredVirtualWindow.ts:179:5
  177 |     scrollTop,
  178 |     viewport,
> 179 |     heights.current,
      |     ^^^^^^^^^^^^^^^ Passing a ref to a function may read its value during render
  180 |     estimate,
  181 |     overscan,
  182 |   );                                                                          react-hooks/refs

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/handoff/HandoffWorkflow.tsx
   69:5   warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/handoff/HandoffWorkflow.tsx:69:5
  67 |       return;
  68 |     }
> 69 |     setAuthToken(t);
     |     ^^^^^^^^^^^^ Avoid calling setState() directly within an effect
  70 |   }, [router]);
  71 |
  72 |   // Initial fetch — and re-fetch when pipeline finishes for refresh safety                                                                                     react-hooks/set-state-in-effect
  151:41  warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/handoff/HandoffWorkflow.tsx:151:41
  149 |
  150 |   useEffect(() => {
> 151 |     if (authToken && handoffToken) void fetchSession();
      |                                         ^^^^^^^^^^^^ Avoid calling setState() directly within an effect
  152 |   }, [authToken, handoffToken, fetchSession]);
  153 |
  154 |   // Live WS — only when we're actively running  react-hooks/set-state-in-effect

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/handoff/IntegrationsCard.tsx
  94:24  warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/handoff/IntegrationsCard.tsx:94:24
  92 |     }
  93 |   }, []);
> 94 |   useEffect(() => void refresh(), [refresh]);
     |                        ^^^^^^^ Avoid calling setState() directly within an effect
  95 |
  96 |   const handleSavePat = useCallback(async () => {
  97 |     const token = getToken();  react-hooks/set-state-in-effect

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/history/RunDetailPage.tsx
  97:7  warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/history/RunDetailPage.tsx:97:7
   95 |     const jwt = getToken();
   96 |     if (!jwt) {
>  97 |       setError("Not authenticated.");
      |       ^^^^^^^^ Avoid calling setState() directly within an effect
   98 |       setLoading(false);
   99 |       return;
  100 |     }  react-hooks/set-state-in-effect

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/history/WorkflowHistory.tsx
  185:5   warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/history/WorkflowHistory.tsx:185:5
  183 |     const token = getToken();
  184 |     if (!token) return;
> 185 |     setLoading(true);
      |     ^^^^^^^^^^ Avoid calling setState() directly within an effect
  186 |     getWorkflows(token, { limit: 50 })
  187 |       .then(({ runs: data, total }) => {
  188 |         setRuns(data);                                                                                                                 react-hooks/set-state-in-effect
  195:9   warning  'handleLoadMore' is assigned a value but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
  238:6   warning  React Hook useCallback has a missing dependency: 'onOpenRun'. Either include it or remove the dependency array. If 'onOpenRun' changes too often, find the parent component that defines it and wrap that definition in useCallback                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    react-hooks/exhaustive-deps
  273:25  warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/history/WorkflowHistory.tsx:273:25
  271 |   // cancellable so a fast back-and-forth cannot land a stale family.
  272 |   useEffect(() => {
> 273 |     if (!selectedRun) { setFamily(null); return; }
      |                         ^^^^^^^^^ Avoid calling setState() directly within an effect
  274 |     const token = getToken();
  275 |     if (!token) return;
  276 |     let cancelled = false;                                                  react-hooks/set-state-in-effect
  296:25  warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/history/WorkflowHistory.tsx:296:25
  294 |   // run resolves to empty artifacts → [] → ClarificationsCard renders nothing.
  295 |   useEffect(() => {
> 296 |     if (!selectedRun) { setClarifyRounds([]); return; }
      |                         ^^^^^^^^^^^^^^^^ Avoid calling setState() directly within an effect
  297 |     const token = getToken();
  298 |     if (!token) { setClarifyRounds([]); return; }
  299 |     let cancelled = false;  react-hooks/set-state-in-effect
  306:6   warning  React Hook useEffect has a missing dependency: 'selectedRun'. Either include it or remove the dependency array                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         react-hooks/exhaustive-deps

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/layout/AppHeader.tsx
  243:9  warning  Using `<img>` could result in slower LCP and higher bandwidth. Consider using `<Image />` from `next/image` or a custom image loader to automatically optimize images. This may incur additional usage or cost from your provider. See: https://nextjs.org/docs/messages/no-img-element  @next/next/no-img-element

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/layout/DashboardLayout.tsx
     6:30  warning  'Loader2' is defined but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
   283:3   warning  'activeChatId' is defined but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               @typescript-eslint/no-unused-vars
   293:3   warning  'onSendMessageWithMode' is defined but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      @typescript-eslint/no-unused-vars
   294:3   warning  'onSelectChat' is defined but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               @typescript-eslint/no-unused-vars
   295:3   warning  'onNewChat' is defined but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  @typescript-eslint/no-unused-vars
   296:3   warning  'onDeleteChat' is defined but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               @typescript-eslint/no-unused-vars
   299:3   warning  'messageMode' is defined but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                @typescript-eslint/no-unused-vars
   300:3   warning  'chatTitleUpdate' is defined but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   301:3   warning  'processSteps' is defined but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               @typescript-eslint/no-unused-vars
   309:3   warning  'homeWorkflows' is defined but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              @typescript-eslint/no-unused-vars
   375:10  warning  'completedPipelineTypes' is assigned a value but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   386:10  warning  'questionnaireLoading' is assigned a value but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              @typescript-eslint/no-unused-vars
   457:32  warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/layout/DashboardLayout.tsx:457:32
  455 |   const [runFamily, setRunFamily] = useState<RunFamily | null>(null);
  456 |   useEffect(() => {
> 457 |     if (!contentSourceRunId) { setRunFamily(null); return; }
      |                                ^^^^^^^^^^^^ Avoid calling setState() directly within an effect
  458 |     getRunFamily(getToken() || "", contentSourceRunId)
  459 |       .then(setRunFamily)
  460 |       .catch(() => setRunFamily(null));                                                                                                                                                                                                                                                                                                       react-hooks/set-state-in-effect
   490:5   warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/layout/DashboardLayout.tsx:490:5
  488 |     // FIX-215: pass backgroundCompletedRunId so markCompleted stamps workflowRunId.
  489 |     markCompleted(notif.id, backgroundCompletedRunId);
> 490 |     setToasts(prev => {
      |     ^^^^^^^^^ Avoid calling setState() directly within an effect
  491 |       const toastId = notif!.id + "-toast";
  492 |       if (prev.some(t => t.id === toastId)) return prev;
  493 |       return [...prev, {                                                                                                                                                                                                                                                                                                                    react-hooks/set-state-in-effect
   539:9   warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/layout/DashboardLayout.tsx:539:9
  537 |       }
  538 |       if (mainView !== "execution") {
> 539 |         setMainView("execution");
      |         ^^^^^^^^^^^ Avoid calling setState() directly within an effect
  540 |       }
  541 |       const normalised = pipelineState.pipeline_type as WorkflowType;
  542 |       if (normalised && normalised !== workflowType) {                                                                                                                                                                                                                                                                                                                                                                                           react-hooks/set-state-in-effect
   628:21  warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/layout/DashboardLayout.tsx:628:21
  626 |         });
  627 |         const output = pptContent || userStoryContent || prototypeContent;
> 628 |         if (output) setLastPipelineOutput(output);
      |                     ^^^^^^^^^^^^^^^^^^^^^ Avoid calling setState() directly within an effect
  629 |
  630 |         // Fire completion notification + toast
  631 |         if (currentPipelineNotifId.current) {                                                                                                                                                                                                                                                                                                                                                 react-hooks/set-state-in-effect
   678:6   warning  React Hook useEffect has missing dependencies: 'markCancelled', 'markCompleted', 'markFailed', and 'notifications'. Either include them or remove the dependency array                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 react-hooks/exhaustive-deps
   700:6   warning  React Hook useEffect has a missing dependency: 'updateProgress'. Either include it or remove the dependency array                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      react-hooks/exhaustive-deps
   733:7   error    Error: This value cannot be modified

Modifying a value used previously in an effect function or as an effect dependency is not allowed. Consider moving the modification before calling useEffect().

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/layout/DashboardLayout.tsx:733:7
  731 |     ) {
  732 |       if (odProtoNotifCreated.current) return;
> 733 |       odProtoNotifCreated.current = true;
      |       ^^^^^^^^^^^^^^^^^^^ `odProtoNotifCreated` cannot be modified
  734 |       // Use the stable pipelineRunId as the notification id so a second firing
  735 |       // of this effect for the SAME run is a no-op (addRunningNotification
  736 |       // deduplicates by id). Falls back to Date.now() only when pipelineRunId                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    react-hooks/immutability
   786:6   warning  React Hook useEffect has missing dependencies: 'addRunningNotification', 'setNotifWorkflowRunId', and 'submittedBrief'. Either include them or remove the dependency array                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             react-hooks/exhaustive-deps
   794:6   warning  React Hook useEffect has a missing dependency: 'updateAgentsTotal'. Either include it or remove the dependency array                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   react-hooks/exhaustive-deps
   819:6   warning  React Hook useEffect has missing dependencies: 'pipelineState?.agents?.length', 'recentRuns', and 'updateAgentsTotal'. Either include them or remove the dependency array                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              react-hooks/exhaustive-deps
   819:7   warning  React Hook useEffect has a complex expression in the dependency array. Extract it to a separate variable so it can be statically checked                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               react-hooks/exhaustive-deps
   831:28  warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/layout/DashboardLayout.tsx:831:28
  829 |   // is safe because this effect runs on each isPipelineRunning change.
  830 |   useEffect(() => {
> 831 |     if (isPipelineRunning) setResumeError(null);
      |                            ^^^^^^^^^^^^^^ Avoid calling setState() directly within an effect
  832 |   }, [isPipelineRunning]);
  833 |
  834 |   // Extract Agent 3's (ppt-code-generator) output for early PPTX download                                                                                                                                                                                                                                                                                                                                      react-hooks/set-state-in-effect
   957:7   warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/layout/DashboardLayout.tsx:957:7
  955 |   useEffect(() => {
  956 |     if (questionnaireData && questionnaireData.questions) {
> 957 |       setQuestionnaireQuestions(questionnaireData.questions);
      |       ^^^^^^^^^^^^^^^^^^^^^^^^^ Avoid calling setState() directly within an effect
  958 |       setQuestionnaireLoading(false);
  959 |     } else if (!questionnaireData) {
  960 |       // questionnaireData was cleared — clear the questions so the Steps panel                                                                                                                                                                                                                                                                                           react-hooks/set-state-in-effect
  1390:33  error    Error: Cannot access variable before it is declared

`chainFromType` is accessed before it is declared, which prevents the earlier access from updating when this value changes over time.

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/layout/DashboardLayout.tsx:1390:33
  1388 |     // run of a different type (e.g. viewing od_prototype while workflowType is
  1389 |     // still "user_stories" from a previous run).
> 1390 |     const effectiveSourceType = chainFromType || workflowType;
       |                                 ^^^^^^^^^^^^^ `chainFromType` accessed before it is declared
  1391 |     const sourceRunId: string | undefined =
  1392 |       contentSourceRunId ??
  1393 |       recentRuns?.find(

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/layout/DashboardLayout.tsx:2061:3
  2059 |   // Use effectiveReviseType (the type of the run currently on screen) so the filter
  2060 |   // correctly excludes the VIEWED pipeline type, not the last-launched type.
> 2061 |   const chainFromType = (effectiveReviseType ?? workflowType) as WorkflowType;
       |   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ `chainFromType` is declared here
  2062 |   const laneSuggestions: LaneSuggestion[] = chainInto(baseWorkflowType(chainFromType))
  2063 |     //.filter((o) => !o.beta)
  2064 |     .map((o) => ({ id: o.id, text: o.text, label: o.label, isBeta: o.beta, display_name: o.display_name, short_name: o.short_name }));  react-hooks/immutability
  1489:6   warning  React Hook useCallback has missing dependencies: 'chainFromType' and 'router'. Either include them or remove the dependency array                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      react-hooks/exhaustive-deps
  1576:6   warning  React Hook useCallback has a missing dependency: 'router'. Either include it or remove the dependency array                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            react-hooks/exhaustive-deps

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/library/LibraryPage.reskin.test.tsx
  169:13  warning  'container' is assigned a value but never used  @typescript-eslint/no-unused-vars

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/library/LibraryPage.tsx
   29:7   warning  'ICON_TINTS' is assigned a value but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             @typescript-eslint/no-unused-vars
   38:10  warning  'getInitials' is defined but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     @typescript-eslint/no-unused-vars
  750:20  error    Error: Cannot access refs during render

React refs are values that are not needed for rendering. Refs should only be accessed outside of render, such as in event handlers or effects. Accessing a ref value (the `current` property) during render can cause your component not to update as expected (https://react.dev/reference/react/useRef).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/library/LibraryPage.tsx:750:20
  748 |           <AgentCapabilitiesModal
  749 |             // Seed the Skills tab from the persisted set so a reopen restores it.
> 750 |             agent={{
      |                    ^
> 751 |               ...selectedAgent.agent,
      | ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
> 752 |               skills:
      | ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
> 753 |                 savedSkillsRef.current[selectedAgent.agent.id] ??
      | ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
> 754 |                 selectedAgent.agent.skills,
      | ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
> 755 |             }}
      | ^^^^^^^^^^^^^^ Cannot access ref value during render
  756 |             agentIndex={selectedAgent.index}
  757 |             onClose={() => setSelectedAgent(null)}
  758 |             asDrawer  react-hooks/refs
  753:17  error    Error: Cannot access refs during render

React refs are values that are not needed for rendering. Refs should only be accessed outside of render, such as in event handlers or effects. Accessing a ref value (the `current` property) during render can cause your component not to update as expected (https://react.dev/reference/react/useRef).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/library/LibraryPage.tsx:753:17
  751 |               ...selectedAgent.agent,
  752 |               skills:
> 753 |                 savedSkillsRef.current[selectedAgent.agent.id] ??
      |                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ Cannot access ref value during render
  754 |                 selectedAgent.agent.skills,
  755 |             }}
  756 |             agentIndex={selectedAgent.index}                                                                                                                                                                                                                                                                                                                                                                                                                                 react-hooks/refs
  753:17  error    Error: Cannot access refs during render

React refs are values that are not needed for rendering. Refs should only be accessed outside of render, such as in event handlers or effects. Accessing a ref value (the `current` property) during render can cause your component not to update as expected (https://react.dev/reference/react/useRef).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/library/LibraryPage.tsx:753:17
  751 |               ...selectedAgent.agent,
  752 |               skills:
> 753 |                 savedSkillsRef.current[selectedAgent.agent.id] ??
      |                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
> 754 |                 selectedAgent.agent.skills,
      | ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ Cannot access ref value during render
  755 |             }}
  756 |             agentIndex={selectedAgent.index}
  757 |             onClose={() => setSelectedAgent(null)}                                                                                                                                                                                                                                                                                                               react-hooks/refs
  759:32  error    Error: Cannot access refs during render

React refs are values that are not needed for rendering. Refs should only be accessed outside of render, such as in event handlers or effects. Accessing a ref value (the `current` property) during render can cause your component not to update as expected (https://react.dev/reference/react/useRef).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/library/LibraryPage.tsx:759:32
  757 |             onClose={() => setSelectedAgent(null)}
  758 |             asDrawer
> 759 |             initialSelections={savedSelectionsRef.current[selectedAgent.agent.id] ?? {}}
      |                                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ Cannot access ref value during render
  760 |             onSelectionsChange={(next) => {
  761 |               // Persist the selections for this agent so reopening restores them.
  762 |               savedSelectionsRef.current[selectedAgent.agent.id] = next;                                                                                                                                                                                                                                                                           react-hooks/refs
  759:32  error    Error: Cannot access refs during render

React refs are values that are not needed for rendering. Refs should only be accessed outside of render, such as in event handlers or effects. Accessing a ref value (the `current` property) during render can cause your component not to update as expected (https://react.dev/reference/react/useRef).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/library/LibraryPage.tsx:759:32
  757 |             onClose={() => setSelectedAgent(null)}
  758 |             asDrawer
> 759 |             initialSelections={savedSelectionsRef.current[selectedAgent.agent.id] ?? {}}
      |                                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ Cannot access ref value during render
  760 |             onSelectionsChange={(next) => {
  761 |               // Persist the selections for this agent so reopening restores them.
  762 |               savedSelectionsRef.current[selectedAgent.agent.id] = next;                                                                                                                                                                                                                                                                     react-hooks/refs

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/preview/AppBuilderPreview.tsx
  215:8   warning  Error: Cannot create components during render

Components created during render will reset their state each time they are created. Declare components outside of render.

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/preview/AppBuilderPreview.tsx:215:8
  213 |       style={{ paddingLeft: `${10 + indent}px`, paddingRight: "8px" }}
  214 |     >
> 215 |       <Icon className={`h-3.5 w-3.5 flex-shrink-0 ${isActive ? "text-brand" : "text-ink-400"}`} />
      |        ^^^^ This component is created during render
  216 |       <span className={`text-[11px] truncate ${isActive ? "text-brand font-medium" : "text-ink-600"}`}>
  217 |         {node.name}
  218 |       </span>

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/preview/AppBuilderPreview.tsx:201:16
  199 |   }
  200 |
> 201 |   const Icon = getFileIcon(node.file?.ext || "");
      |                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ The component is created during render here
  202 |   const matchesSearch = !searchQuery || node.name.toLowerCase().includes(searchQuery.toLowerCase());
  203 |   if (!matchesSearch) return null;
  204 |                    react-hooks/static-components
  235:18  warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/preview/AppBuilderPreview.tsx:235:18
  233 |
  234 |   useEffect(() => {
> 235 |     if (!file) { setHighlighted(""); return; }
      |                  ^^^^^^^^^^^^^^ Avoid calling setState() directly within an effect
  236 |     if (hlReady) setHighlighted(highlightCode(file.content, file.language));
  237 |     else setHighlighted(escapeHtml(file.content));
  238 |   }, [file, hlReady]);         react-hooks/set-state-in-effect
  353:5   warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/preview/AppBuilderPreview.tsx:353:5
  351 |       if (parts.length > 1) topFolders.add(parts[0]);
  352 |     });
> 353 |     setExpandedPaths(topFolders);
      |     ^^^^^^^^^^^^^^^^ Avoid calling setState() directly within an effect
  354 |     if (files.length > 0 && !activeFile) {
  355 |       setActiveFile(files[0]);
  356 |       setOpenTabs([{ path: files[0].path, name: files[0].name }]);  react-hooks/set-state-in-effect
  358:6   warning  React Hook useEffect has a missing dependency: 'activeFile'. Either include it or remove the dependency array                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             react-hooks/exhaustive-deps

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/preview/PPTPreview.tsx
   20:39  warning  'isStreaming' is defined but never used                    @typescript-eslint/no-unused-vars
   22:10  warning  'isDownloading' is assigned a value but never used         @typescript-eslint/no-unused-vars
   30:9   warning  'handleDownloadHtml' is assigned a value but never used    @typescript-eslint/no-unused-vars
   47:9   warning  'handleDownloadPptx' is assigned a value but never used    @typescript-eslint/no-unused-vars
  194:9   warning  'handleOpenFullScreen' is assigned a value but never used  @typescript-eslint/no-unused-vars

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/preview/PreviewPanel.tsx
  506:77  warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/preview/PreviewPanel.tsx:506:77
  504 |   const autoTabbedForState = useRef<string | null>(null);
  505 |
> 506 |   useEffect(() => { if (initialTab === "preview" || initialTab === "files") setActiveTab(initialTab); }, [initialTab]);
      |                                                                             ^^^^^^^^^^^^ Avoid calling setState() directly within an effect
  507 |
  508 |   // Phase 31 (CHATUI-02) — nonce'd deep-link consumer (borrow #6). A chat
  509 |   // result-card click mints a fresh {tab, nonce}; switch to the target tab for  react-hooks/set-state-in-effect
  517:7   warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/preview/PreviewPanel.tsx:517:7
  515 |     const tab = deepLinkTarget?.tab;
  516 |     if (tab && (PANEL_TAB_IDS as readonly string[]).includes(tab)) {
> 517 |       setActiveTab(tab as PanelTab);
      |       ^^^^^^^^^^^^ Avoid calling setState() directly within an effect
  518 |     }
  519 |     // eslint-disable-next-line react-hooks/exhaustive-deps
  520 |   }, [deepLinkTarget?.nonce]);                                                                                                                                                                      react-hooks/set-state-in-effect
  570:21  warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/preview/PreviewPanel.tsx:570:21
  568 |
  569 |   // A new live run supersedes any active read-only view.
> 570 |   useEffect(() => { setViewingVersion(null); }, [liveRunId]);
      |                     ^^^^^^^^^^^^^^^^^ Avoid calling setState() directly within an effect
  571 |
  572 |   const detectedType: WorkflowType = workflowType || (userStoryContent ? "user_stories" : pptContent ? "ppt" : prototypeContent ? "prototype" : "user_stories");
  573 |   // Normalize revision types to their base type for rendering                                          react-hooks/set-state-in-effect
  732:17  warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/preview/PreviewPanel.tsx:732:17
  730 |       (headerRunState === "gate" || headerRunState === "clarify" || headerRunState === "building") ? "thinking" :
  731 |       null;
> 732 |     if (target) setActiveTab(target);
      |                 ^^^^^^^^^^^^ Avoid calling setState() directly within an effect
  733 |     // eslint-disable-next-line react-hooks/exhaustive-deps
  734 |   }, [defaultTabDiscriminator]);
  735 |   // Live version label — derived from the live family (active member index) or the                                                      react-hooks/set-state-in-effect
  870:21  warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/preview/PreviewPanel.tsx:870:21
  868 |   // A new deliverable (renderType change) drops any stale override so the generic
  869 |   // auto-dispatch resumes as the PRIMARY route.
> 870 |   useEffect(() => { setRendererOverride(null); }, [renderType]);
      |                     ^^^^^^^^^^^^^^^^^^^ Avoid calling setState() directly within an effect
  871 |
  872 |   // Mimetype tokens the generic renderer can be forced into. These are DECLARED
  873 |   // mimetype/render shapes (SC-001 — never a workflow name)                                             react-hooks/set-state-in-effect

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/preview/PrototypePreview.tsx
  341:7   warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/preview/PrototypePreview.tsx:341:7
  339 |   useEffect(() => {
  340 |     if (!content) {
> 341 |       setBaseHtml("");
      |       ^^^^^^^^^^^ Avoid calling setState() directly within an effect
  342 |       baseHtmlRef.current = "";
  343 |       setRenderedHtml("");
  344 |       return;                                                                                                                                                                                                                           react-hooks/set-state-in-effect
  357:26  warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/preview/PrototypePreview.tsx:357:26
  355 |   // ── Build Blob URL whenever renderedHtml changes ────────────────────────
  356 |   useEffect(() => {
> 357 |     if (!renderedHtml) { setBlobUrl(null); return; }
      |                          ^^^^^^^^^^ Avoid calling setState() directly within an effect
  358 |     const isHtml = /<!DOCTYPE\s+html|<html[\s>]/i.test(renderedHtml);
  359 |     if (!isHtml) { setBlobUrl(null); return; }
  360 |     const blob = new Blob([renderedHtml], { type: "text/html" });  react-hooks/set-state-in-effect

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/preview/RunHeader.test.tsx
  2:37  warning  'waitFor' is defined but never used  @typescript-eslint/no-unused-vars

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/preview/TweaksPanel.tsx
  190:5   warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/preview/TweaksPanel.tsx:190:5
  188 |   // Sync localHtml when parent content changes (new pipeline run)
  189 |   useEffect(() => {
> 190 |     setLocalHtml(editHtml);
      |     ^^^^^^^^^^^^ Avoid calling setState() directly within an effect
  191 |     setHtmlDirty(false);
  192 |   }, [editHtml]);
  193 |  react-hooks/set-state-in-effect
  330:45  error    `"` can be escaped with `&quot;`, `&ldquo;`, `&#34;`, `&rdquo;`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  react/no-unescaped-entities
  330:51  error    `"` can be escaped with `&quot;`, `&ldquo;`, `&#34;`, `&rdquo;`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  react/no-unescaped-entities

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/results/AgentDetailPanel.artifactVersions.test.tsx
   66:71  warning  '_c' is defined but never used  @typescript-eslint/no-unused-vars
  152:71  warning  '_c' is defined but never used  @typescript-eslint/no-unused-vars

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/results/AgentDetailPanel.tsx
   20:3   warning  'Clock' is defined but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             @typescript-eslint/no-unused-vars
  910:21  warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/results/AgentDetailPanel.tsx:910:21
  908 |   // ISS-065 — the older artifact version currently on screen, if any.
  909 |   const [viewed, setViewed] = useState<{ index: number; content: string } | null>(null);
> 910 |   useEffect(() => { setViewed(null); }, [agent.id]);
      |                     ^^^^^^^^^ Avoid calling setState() directly within an effect
  911 |   // ISS-085 — this agent AS OF the version on screen. Every consumer of the
  912 |   // artifact reads from here, so one selection moves the whole panel; deriving the
  913 |   // cards from `agent.output` while the output section read the selected version  react-hooks/set-state-in-effect

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/results/AgentThinkingTab.tsx
  94:19  warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/results/AgentThinkingTab.tsx:94:19
  92 |   const [gateEvents, setGateEvents] = useState<GateEventRow[]>([]);
  93 |   useEffect(() => {
> 94 |     if (!runId) { setGateEvents([]); return; }
     |                   ^^^^^^^^^^^^^ Avoid calling setState() directly within an effect
  95 |     let cancelled = false;
  96 |     (async () => {
  97 |       try {  react-hooks/set-state-in-effect

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/results/ArtifactVersionPicker.tsx
  111:7  warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/results/ArtifactVersionPicker.tsx:111:7
  109 |     contentCache.current.clear();
  110 |     if (!runId) {
> 111 |       setVersions([]);
      |       ^^^^^^^^^^^ Avoid calling setState() directly within an effect
  112 |       return;
  113 |     }
  114 |     let cancelled = false;  react-hooks/set-state-in-effect

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/results/AuditTab.tsx
  456:5  warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/results/AuditTab.tsx:456:5
  454 |     if (!token) return;
  455 |     let cancelled = false;
> 456 |     setLoading(true);
      |     ^^^^^^^^^^ Avoid calling setState() directly within an effect
  457 |     Promise.all([
  458 |       getRunGateEvents(token, workflowRunId),
  459 |       getRunValidationResults(token, workflowRunId),  react-hooks/set-state-in-effect

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/results/StepsOverviewSpine.tsx
  137:40  error    Error: Cannot call impure function during render

`Date.now` is an impure function. Calling an impure function can produce unstable results that update unpredictably when the component happens to re-render. (https://react.dev/reference/rules/components-and-hooks-must-be-pure#components-and-hooks-must-be-idempotent).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/results/StepsOverviewSpine.tsx:137:40
  135 | }) {
  136 |   useTick(1000);
> 137 |   const line = liveActivityLine(agent, Date.now(), pipelineState);
      |                                        ^^^^^^^^^^ Cannot call impure function
  138 |   if (!line) return null;
  139 |
  140 |   return (  react-hooks/purity
  296:38  warning  'onSkipClarify' is defined but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      @typescript-eslint/no-unused-vars

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/savedworkflows/SavedWorkflowsPage.tsx
   91:3   warning  'row' is defined but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     @typescript-eslint/no-unused-vars
  164:17  warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/savedworkflows/SavedWorkflowsPage.tsx:164:17
  162 |     let cancelled = false;
  163 |     const jwt = getToken();
> 164 |     if (!jwt) { setSavedError("Not authenticated."); setLoading(false); return; }
      |                 ^^^^^^^^^^^^^ Avoid calling setState() directly within an effect
  165 |     setLoading(true);
  166 |     getUserWorkflows(jwt)
  167 |       .then((rows) => { if (!cancelled) { setUserWorkflows(rows); setSavedError(null); } })  react-hooks/set-state-in-effect
  293:66  error    `"` can be escaped with `&quot;`, `&ldquo;`, `&#34;`, `&rdquo;`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     react/no-unescaped-entities
  293:82  error    `"` can be escaped with `&quot;`, `&ldquo;`, `&#34;`, `&rdquo;`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     react/no-unescaped-entities
  303:84  error    `"` can be escaped with `&quot;`, `&ldquo;`, `&#34;`, `&rdquo;`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     react/no-unescaped-entities
  303:93  error    `"` can be escaped with `&quot;`, `&ldquo;`, `&#34;`, `&rdquo;`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     react/no-unescaped-entities

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/settings/AccountSettings.tsx
    6:54  warning  'Check' is defined but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           @typescript-eslint/no-unused-vars
   75:5   warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/settings/AccountSettings.tsx:75:5
  73 |     const token = getToken();
  74 |     if (!token) return;
> 75 |     setLoading(true);
     |     ^^^^^^^^^^ Avoid calling setState() directly within an effect
  76 |
  77 |     Promise.all([
  78 |       getMe(token),                                                                                                              react-hooks/set-state-in-effect
  451:19  warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/settings/AccountSettings.tsx:451:19
  449 |   useEffect(() => {
  450 |     const token = getToken();
> 451 |     if (!token) { setLoading(false); return; }
      |                   ^^^^^^^^^^ Avoid calling setState() directly within an effect
  452 |     fetch("/api/settings/constitution", {
  453 |       headers: { Authorization: `Bearer ${token}` },
  454 |     })  react-hooks/set-state-in-effect

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/sidebar/Sidebar.tsx
   3:10  warning  'useCallback' is defined but never used      @typescript-eslint/no-unused-vars
   3:23  warning  'useEffect' is defined but never used        @typescript-eslint/no-unused-vars
  22:10  warning  'getToken' is defined but never used         @typescript-eslint/no-unused-vars
  22:20  warning  'getChats' is defined but never used         @typescript-eslint/no-unused-vars
  91:3   warning  'activeChatId' is defined but never used     @typescript-eslint/no-unused-vars
  92:3   warning  'onSelectChat' is defined but never used     @typescript-eslint/no-unused-vars
  93:3   warning  'onNewChat' is defined but never used        @typescript-eslint/no-unused-vars
  94:3   warning  'onDeleteChat' is defined but never used     @typescript-eslint/no-unused-vars
  97:3   warning  'chatTitleUpdate' is defined but never used  @typescript-eslint/no-unused-vars

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/ui/CompletionToast.tsx
  3:21  warning  'useState' is defined but never used  @typescript-eslint/no-unused-vars

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/ui/NotificationPanel.fix195.test.tsx
  22:36  warning  'beforeEach' is defined but never used  @typescript-eslint/no-unused-vars

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/ui/NotificationPanel.tsx
  202:3  warning  'onGoToPipeline' is defined but never used             @typescript-eslint/no-unused-vars
  208:9  warning  'getWorkflowLabel' is assigned a value but never used  @typescript-eslint/no-unused-vars

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/AdvancedExpander.test.tsx
  29:26  warning  'waitFor' is defined but never used  @typescript-eslint/no-unused-vars

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/AgentLibrary.tsx
  160:25  warning  'count' is assigned a value but never used                             @typescript-eslint/no-unused-vars
  212:29  warning  'initials' is assigned a value but never used                          @typescript-eslint/no-unused-vars
  232:68  warning  Expected an assignment or function call and instead saw an expression  @typescript-eslint/no-unused-expressions

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/AgentModelPicker.tsx
  69:7  warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/AgentModelPicker.tsx:69:7
  67 |     const jwt = token ?? getToken();
  68 |     if (!jwt) {
> 69 |       setError("Not authenticated.");
     |       ^^^^^^^^ Avoid calling setState() directly within an effect
  70 |       setLoading(false);
  71 |       return;
  72 |     }  react-hooks/set-state-in-effect

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/AgentsPopup.tsx
     8:68  warning  'Cpu' is defined but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               @typescript-eslint/no-unused-vars
   242:5   warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/AgentsPopup.tsx:242:5
  240 |     const token = getToken();
  241 |     if (!token) return;
> 242 |     setLoading(true);
      |     ^^^^^^^^^^ Avoid calling setState() directly within an effect
  243 |     setError(null);
  244 |     getAgentPrompt(token, agent.id)
  245 |       .then(d => { setPromptData(d); })  react-hooks/set-state-in-effect
   423:18  warning  'propHooks' is defined but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         @typescript-eslint/no-unused-vars
   424:17  warning  'propAttachHook' is defined but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
   427:3   warning  'priorAgents' is defined but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       @typescript-eslint/no-unused-vars
   462:33  warning  'HOOK_EVENTS' is assigned a value but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              @typescript-eslint/no-unused-vars
   829:28  warning  'pipelineType' is defined but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      @typescript-eslint/no-unused-vars
  1034:7   warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/AgentsPopup.tsx:1034:7
  1032 |     const jwt = token ?? getToken();
  1033 |     if (!jwt) {
> 1034 |       setError("Not authenticated.");
       |       ^^^^^^^^ Avoid calling setState() directly within an effect
  1035 |       setLoading(false);
  1036 |       return;
  1037 |     }                              react-hooks/set-state-in-effect
  1392:7   warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/AgentsPopup.tsx:1392:7
  1390 |     const jwt = token ?? getToken();
  1391 |     if (!jwt) {
> 1392 |       setError("Not authenticated.");
       |       ^^^^^^^^ Avoid calling setState() directly within an effect
  1393 |       setLoading(false);
  1394 |       return;
  1395 |     }                              react-hooks/set-state-in-effect
  1567:56  warning  'loading' is assigned a value but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  @typescript-eslint/no-unused-vars

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/IdeaInputPage.tsx
    21:39  warning  'AttachedSkill' is defined but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   @typescript-eslint/no-unused-vars
    21:54  warning  'AttachedHook' is defined but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    @typescript-eslint/no-unused-vars
   811:56  warning  'CUSTOM_AGENTS' is assigned a value but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          @typescript-eslint/no-unused-vars
   909:7   warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/IdeaInputPage.tsx:909:7
  907 |   useEffect(() => {
  908 |     if (!workflowId) {
> 909 |       setDeclaredCapabilities(undefined);
      |       ^^^^^^^^^^^^^^^^^^^^^^^ Avoid calling setState() directly within an effect
  910 |       return;
  911 |     }
  912 |     let cancelled = false;                                                                                                                                                       react-hooks/set-state-in-effect
   958:7   warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/IdeaInputPage.tsx:958:7
  956 |     // KAN-112: custom workflow starts blank — user picks agents themselves.
  957 |     if (effectiveType === "custom") {
> 958 |       setPipelineAgents([]);
      |       ^^^^^^^^^^^^^^^^^ Avoid calling setState() directly within an effect
  959 |     } else {
  960 |       setPipelineAgents(LIBRARY_AGENTS.filter((a) => a.pipeline_type === effectiveType).sort((a, b) => a.order - b.order));
  961 |     }  react-hooks/set-state-in-effect
   966:27  warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/IdeaInputPage.tsx:966:27
  964 |   // Reset the sub-choice when the parent switches us off the migration meta-type.
  965 |   useEffect(() => {
> 966 |     if (!isMigrationMeta) setMigrationChoice(null);
      |                           ^^^^^^^^^^^^^^^^^^ Avoid calling setState() directly within an effect
  967 |   }, [isMigrationMeta]);
  968 |
  969 |   const config = TYPE_CONFIG[effectiveType];                                          react-hooks/set-state-in-effect
   999:11  warning  'hasSelections' is assigned a value but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          @typescript-eslint/no-unused-vars
  1325:27  warning  'missingAgents' is assigned a value but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          @typescript-eslint/no-unused-vars

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/LaunchWizard.tsx
  183:5  warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/LaunchWizard.tsx:183:5
  181 |     const token = getToken();
  182 |     if (!token) { router.replace("/login"); return; }
> 183 |     setAuthChecked(true);
      |     ^^^^^^^^^^^^^^ Avoid calling setState() directly within an effect
  184 |     const from = sessionStorage.getItem("chain.from");
  185 |     if (from) {
  186 |       setChainFrom(from);                          react-hooks/set-state-in-effect
  200:9  warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/LaunchWizard.tsx:200:9
  198 |       const chainBrief = sessionStorage.getItem("chain.brief");
  199 |       if (chainBrief) {
> 200 |         setBrief(chainBrief);
      |         ^^^^^^^^ Avoid calling setState() directly within an effect
  201 |         sessionStorage.removeItem("chain.brief");
  202 |         sessionStorage.removeItem("chain.from");
  203 |         return;  react-hooks/set-state-in-effect
  229:6  warning  React Hook useEffect has a missing dependency: 'libraryAgents'. Either include it or remove the dependency array                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              react-hooks/exhaustive-deps
  269:6  warning  React Hook useEffect has a missing dependency: 'mode'. Either include it or remove the dependency array. You can also replace multiple useState variables with useReducer if 'setSelectedDsId' needs the current value of 'mode'                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              react-hooks/exhaustive-deps

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/SkillManager.tsx
  135:7  warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/SkillManager.tsx:135:7
  133 |   useEffect(() => {
  134 |     if (isOpen && agentId) {
> 135 |       loadSkill();
      |       ^^^^^^^^^ Avoid calling setState() directly within an effect
  136 |     }
  137 |   }, [isOpen, agentId, loadSkill]);
  138 |  react-hooks/set-state-in-effect

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/TokenUsageSummary.tsx
  18:10  warning  'formatCost' is defined but never used                  @typescript-eslint/no-unused-vars
  25:7   warning  'MODEL_SHORT_NAMES' is assigned a value but never used  @typescript-eslint/no-unused-vars
  33:52  warning  'modelId' is defined but never used                     @typescript-eslint/no-unused-vars
  42:9   warning  'cost' is assigned a value but never used               @typescript-eslint/no-unused-vars

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/WizardStepper.tsx
  83:7  warning  'ALL_STEP_IDS' is assigned a value but only used as a type  @typescript-eslint/no-unused-vars

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/WorkflowDialog.tsx
  68:7  warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/WorkflowDialog.tsx:68:7
  66 |     const jwt = token ?? getToken();
  67 |     if (!jwt) {
> 68 |       setError("Not authenticated.");
     |       ^^^^^^^^ Avoid calling setState() directly within an effect
  69 |       setLoading(false);
  70 |       return;
  71 |     }  react-hooks/set-state-in-effect

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/WorkflowView.tsx
   13:3  warning  'ChevronDown' is defined but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                @typescript-eslint/no-unused-vars
   14:3  warning  'ChevronRight' is defined but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               @typescript-eslint/no-unused-vars
   15:3  warning  'ChevronLeft' is defined but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                @typescript-eslint/no-unused-vars
   16:3  warning  'Clock' is defined but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      @typescript-eslint/no-unused-vars
   24:3  warning  'Send' is defined but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       @typescript-eslint/no-unused-vars
  124:5  warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/WorkflowView.tsx:124:5
  122 |   // Update agents when type changes
  123 |   useEffect(() => {
> 124 |     setPipelineAgents(
      |     ^^^^^^^^^^^^^^^^^ Avoid calling setState() directly within an effect
  125 |       libraryAgents.filter((a) => a.pipeline_type === selectedType).sort((a, b) => a.order - b.order)
  126 |     );
  127 |   }, [libraryAgents, selectedType]);                                                             react-hooks/set-state-in-effect
  142:7  warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/WorkflowView.tsx:142:7
  140 |   useEffect(() => {
  141 |     if (pipelineState.isRunning && step !== "running") {
> 142 |       setStep("running");
      |       ^^^^^^^ Avoid calling setState() directly within an effect
  143 |     }
  144 |     if (!pipelineState.isRunning && pipelineState.agents.length > 0 && pipelineState.completedCount === pipelineState.agents.length && step === "running") {
  145 |       setStep("complete");  react-hooks/set-state-in-effect

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/composer/CanvasConfigRail.tsx
  421:10   warning  Error: Cannot create components during render

Components created during render will reset their state each time they are created. Declare components outside of render.

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/composer/CanvasConfigRail.tsx:421:10
  419 |       {/* MODEL (whole catalog — SC-001) */}
  420 |       <p className="mb-2 mt-5 flex items-center gap-1.5 font-sans text-[10px] font-semibold uppercase tracking-[0.1em] text-ink-300">
> 421 |         <InfoHint>Overrides the default model for this agent's step. &quot;Default&quot; uses the workflow's own model choice.</InfoHint>
      |          ^^^^^^^^ This component is created during render
  422 |         Model
  423 |       </p>
  424 |       <div className="relative">

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/composer/CanvasConfigRail.tsx:103:20
  101 |   // (CanvasView's workflowSettingsSection) — reproduced here rather than
  102 |   // imported since that one is a local, unexported component.
> 103 |   const InfoHint = ({ children }: { children: ReactNode }) => (
      |                    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
> 104 |     <span className="group relative inline-flex flex-none">
      | ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
> 105 |       <Info className="h-3.5 w-3.5 cursor-help text-ink-300 hover:text-ink-500" />
      …
      | ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
> 112 |     </span>
      | ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
> 113 |   );
      | ^^^^ The component is created during render here
  114 |
  115 |   const Toggle = ({
  116 |     on,                                                       react-hooks/static-components
  421:61   error    `'` can be escaped with `&apos;`, `&lsquo;`, `&#39;`, `&rsquo;`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           react/no-unescaped-entities
  421:107  error    `'` can be escaped with `&apos;`, `&lsquo;`, `&#39;`, `&rsquo;`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           react/no-unescaped-entities
  451:14   warning  Error: Cannot create components during render

Components created during render will reset their state each time they are created. Declare components outside of render.

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/composer/CanvasConfigRail.tsx:451:14
  449 |         <div className="min-w-0">
  450 |           <div className="flex items-center gap-1.5 font-sans text-[12.5px] font-semibold text-ink-900">
> 451 |             <InfoHint>Runs a registered validator against this step's output before the pipeline continues.</InfoHint>
      |              ^^^^^^^^ This component is created during render
  452 |             Validator
  453 |           </div>
  454 |           <div className="font-serif text-[11px] text-ink-300">

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/composer/CanvasConfigRail.tsx:103:20
  101 |   // (CanvasView's workflowSettingsSection) — reproduced here rather than
  102 |   // imported since that one is a local, unexported component.
> 103 |   const InfoHint = ({ children }: { children: ReactNode }) => (
      |                    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
> 104 |     <span className="group relative inline-flex flex-none">
      | ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
> 105 |       <Info className="h-3.5 w-3.5 cursor-help text-ink-300 hover:text-ink-500" />
      …
      | ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
> 112 |     </span>
      | ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
> 113 |   );
      | ^^^^ The component is created during render here
  114 |
  115 |   const Toggle = ({
  116 |     on,                                                                 react-hooks/static-components
  451:68   error    `'` can be escaped with `&apos;`, `&lsquo;`, `&#39;`, `&rsquo;`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           react/no-unescaped-entities
  458:10   warning  Error: Cannot create components during render

Components created during render will reset their state each time they are created. Declare components outside of render.

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/composer/CanvasConfigRail.tsx:458:10
  456 |           </div>
  457 |         </div>
> 458 |         <Toggle
      |          ^^^^^^ This component is created during render
  459 |           on={validatorOn}
  460 |           label="Validator"
  461 |           disabled={loading || validatorOptions.length === 0}

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/composer/CanvasConfigRail.tsx:115:18
  113 |   );
  114 |
> 115 |   const Toggle = ({
      |                  ^^
> 116 |     on,
      | ^^^^^^^
> 117 |     amber = false,
      …
      | ^^^^^^^
> 144 |     </button>
      | ^^^^^^^
> 145 |   );
      | ^^^^ The component is created during render here
  146 |
  147 |   if (!agent) {
  148 |     return (                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    react-hooks/static-components
  471:14   warning  Error: Cannot create components during render

Components created during render will reset their state each time they are created. Declare components outside of render.

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/composer/CanvasConfigRail.tsx:471:14
  469 |         <div className="min-w-0">
  470 |           <div className="flex items-center gap-1.5 font-sans text-[12.5px] font-semibold text-ink-900">
> 471 |             <InfoHint>Pauses the run after this step so a human can approve its output before the pipeline continues.</InfoHint>
      |              ^^^^^^^^ This component is created during render
  472 |             Review gate
  473 |           </div>
  474 |           <div className="font-serif text-[11px] text-ink-300">

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/composer/CanvasConfigRail.tsx:103:20
  101 |   // (CanvasView's workflowSettingsSection) — reproduced here rather than
  102 |   // imported since that one is a local, unexported component.
> 103 |   const InfoHint = ({ children }: { children: ReactNode }) => (
      |                    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
> 104 |     <span className="group relative inline-flex flex-none">
      | ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
> 105 |       <Info className="h-3.5 w-3.5 cursor-help text-ink-300 hover:text-ink-500" />
      …
      | ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
> 112 |     </span>
      | ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
> 113 |   );
      | ^^^^ The component is created during render here
  114 |
  115 |   const Toggle = ({
  116 |     on,                                                     react-hooks/static-components
  478:10   warning  Error: Cannot create components during render

Components created during render will reset their state each time they are created. Declare components outside of render.

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/composer/CanvasConfigRail.tsx:478:10
  476 |           </div>
  477 |         </div>
> 478 |         <Toggle
      |          ^^^^^^ This component is created during render
  479 |           on={reviewGateOn}
  480 |           amber
  481 |           label="Review gate"

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/composer/CanvasConfigRail.tsx:115:18
  113 |   );
  114 |
> 115 |   const Toggle = ({
      |                  ^^
> 116 |     on,
      | ^^^^^^^
> 117 |     amber = false,
      …
      | ^^^^^^^
> 144 |     </button>
      | ^^^^^^^
> 145 |   );
      | ^^^^ The component is created during render here
  146 |
  147 |   if (!agent) {
  148 |     return (                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               react-hooks/static-components
  496:14   warning  Error: Cannot create components during render

Components created during render will reset their state each time they are created. Declare components outside of render.

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/composer/CanvasConfigRail.tsx:496:14
  494 |         <div className="min-w-0">
  495 |           <div className="flex items-center gap-1.5 font-sans text-[12.5px] font-semibold text-ink-900">
> 496 |             <InfoHint>Automatically re-runs this step on a transient failure, up to the selected number of extra attempts.</InfoHint>
      |              ^^^^^^^^ This component is created during render
  497 |             Retry on failure
  498 |           </div>
  499 |           <div className="font-serif text-[11px] text-ink-300">

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/composer/CanvasConfigRail.tsx:103:20
  101 |   // (CanvasView's workflowSettingsSection) — reproduced here rather than
  102 |   // imported since that one is a local, unexported component.
> 103 |   const InfoHint = ({ children }: { children: ReactNode }) => (
      |                    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
> 104 |     <span className="group relative inline-flex flex-none">
      | ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
> 105 |       <Info className="h-3.5 w-3.5 cursor-help text-ink-300 hover:text-ink-500" />
      …
      | ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
> 112 |     </span>
      | ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
> 113 |   );
      | ^^^^ The component is created during render here
  114 |
  115 |   const Toggle = ({
  116 |     on,                                           react-hooks/static-components
  538:16   warning  Error: Cannot create components during render

Components created during render will reset their state each time they are created. Declare components outside of render.

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/composer/CanvasConfigRail.tsx:538:16
  536 |           <div className="min-w-0">
  537 |             <div className="flex items-center gap-1.5 font-sans text-[12.5px] font-semibold text-ink-900">
> 538 |               <InfoHint>Spawns one worker per `## Task N:` heading emitted by an earlier step, instead of running this step once.</InfoHint>
      |                ^^^^^^^^ This component is created during render
  539 |               Fan out over a list
  540 |             </div>
  541 |             <div className="font-serif text-[11px] text-ink-300">

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/composer/CanvasConfigRail.tsx:103:20
  101 |   // (CanvasView's workflowSettingsSection) — reproduced here rather than
  102 |   // imported since that one is a local, unexported component.
> 103 |   const InfoHint = ({ children }: { children: ReactNode }) => (
      |                    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
> 104 |     <span className="group relative inline-flex flex-none">
      | ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
> 105 |       <Info className="h-3.5 w-3.5 cursor-help text-ink-300 hover:text-ink-500" />
      …
      | ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
> 112 |     </span>
      | ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
> 113 |   );
      | ^^^^ The component is created during render here
  114 |
  115 |   const Toggle = ({
  116 |     on,                     react-hooks/static-components
  549:12   warning  Error: Cannot create components during render

Components created during render will reset their state each time they are created. Declare components outside of render.

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/composer/CanvasConfigRail.tsx:549:12
  547 |               already-saved `fanout_batch` still renders as ON) so an existing workflow
  548 |               is not silently rewritten — it just cannot be turned on from here. */}
> 549 |           <Toggle
      |            ^^^^^^ This component is created during render
  550 |             on={fanoutOn}
  551 |             label="Fan out over a list"
  552 |             disabled

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/composer/CanvasConfigRail.tsx:115:18
  113 |   );
  114 |
> 115 |   const Toggle = ({
      |                  ^^
> 116 |     on,
      | ^^^^^^^
> 117 |     amber = false,
      …
      | ^^^^^^^
> 144 |     </button>
      | ^^^^^^^
> 145 |   );
      | ^^^^ The component is created during render here
  146 |
  147 |   if (!agent) {
  148 |     return (                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 react-hooks/static-components
  628:14   warning  Error: Cannot create components during render

Components created during render will reset their state each time they are created. Declare components outside of render.

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/composer/CanvasConfigRail.tsx:628:14
  626 |         <div className="mt-4 border-t border-line-faint-row pt-3">
  627 |           <p className="mb-2 flex items-center gap-1.5 font-sans text-[10px] font-semibold uppercase tracking-[0.1em] text-ink-300">
> 628 |             <InfoHint>Sequential runs each sub-agent one after another; Parallel runs them at the same time (up to Max parallel).</InfoHint>
      |              ^^^^^^^^ This component is created during render
  629 |             Sub-agent strategy
  630 |           </p>
  631 |           <div className="relative">

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/composer/CanvasConfigRail.tsx:103:20
  101 |   // (CanvasView's workflowSettingsSection) — reproduced here rather than
  102 |   // imported since that one is a local, unexported component.
> 103 |   const InfoHint = ({ children }: { children: ReactNode }) => (
      |                    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
> 104 |     <span className="group relative inline-flex flex-none">
      | ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
> 105 |       <Info className="h-3.5 w-3.5 cursor-help text-ink-300 hover:text-ink-500" />
      …
      | ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
> 112 |     </span>
      | ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
> 113 |   );
      | ^^^^ The component is created during render here
  114 |
  115 |   const Toggle = ({
  116 |     on,  react-hooks/static-components

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/composer/CanvasView.tsx
   228:5   warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/composer/CanvasView.tsx:228:5
  226 |   useEffect(() => {
  227 |     if (briefFocusSignal === undefined || briefFocusSignal === 0) return;
> 228 |     setSelectedId(BRIEF_ID);
      |     ^^^^^^^^^^^^^ Avoid calling setState() directly within an effect
  229 |     briefInputRef.current?.focus();
  230 |   }, [briefFocusSignal]);
  231 |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     react-hooks/set-state-in-effect
   236:5   warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/composer/CanvasView.tsx:236:5
  234 |   useEffect(() => {
  235 |     if (resetLayoutSignal === undefined || resetLayoutSignal === 0) return;
> 236 |     setDragOverrides({});
      |     ^^^^^^^^^^^^^^^^ Avoid calling setState() directly within an effect
  237 |     // eslint-disable-next-line react-hooks/exhaustive-deps
  238 |   }, [resetLayoutSignal]);
  239 |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          react-hooks/set-state-in-effect
   237:5   warning  Unused eslint-disable directive (no problems were reported from 'react-hooks/exhaustive-deps')
   252:3   warning  React Hook useLayoutEffect contains a call to 'setNodeCenterY'. Without a list of dependencies, this can lead to an infinite chain of updates. To fix this, pass [nodeCenterY, briefHeight, pipelineAgents] as a second argument to the useLayoutEffect Hook                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             react-hooks/exhaustive-deps
   264:18  warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/composer/CanvasView.tsx:264:18
  262 |       keys.length !== Object.keys(nodeCenterY).length ||
  263 |       keys.some((k) => nodeCenterY[k] !== next[k]);
> 264 |     if (changed) setNodeCenterY(next);
      |                  ^^^^^^^^^^^^^^ Avoid calling setState() directly within an effect
  265 |
  266 |     const briefEl = stageRef.current?.querySelector<HTMLElement>('[data-testid="canvas-brief"]');
  267 |     if (briefEl && briefEl.offsetHeight !== briefHeight) setBriefHeight(briefEl.offsetHeight);                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          react-hooks/set-state-in-effect
   432:9   warning  'selIndex' is assigned a value but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   437:34  warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/composer/CanvasView.tsx:437:34
  435 |   const [railTab, setRailTab] = useState<"workflow" | "agent">("workflow");
  436 |   useEffect(() => {
> 437 |     if (selectedId === BRIEF_ID) setRailTab("workflow");
      |                                  ^^^^^^^^^^ Avoid calling setState() directly within an effect
  438 |     else if (selectedId) setRailTab("agent");
  439 |   }, [selectedId]);
  440 |   const agentTabAgent = foundAgent ?? pipelineAgents[0] ?? null;                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       react-hooks/set-state-in-effect
   690:68  warning  'i' is defined but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
   842:12  warning  Error: Cannot create components during render

Components created during render will reset their state each time they are created. Declare components outside of render.

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/composer/CanvasView.tsx:842:12
  840 |       <div className="flex items-center justify-between">
  841 |         <span className="flex items-center gap-1.5 font-sans text-[12.5px] font-semibold text-ink-900">
> 842 |           <OnOffHint
      |            ^^^^^^^^^ This component is created during render
  843 |             on="Runs a planning agent that breaks the brief into a task plan before the workflow's agents start."
  844 |             off="Agents start directly from the brief, with no planning pass."
  845 |           />

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/composer/CanvasView.tsx:795:21
  793 |     </span>
  794 |   );
> 795 |   const OnOffHint = ({ on, off }: { on: string; off: string }) => (
      |                     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
> 796 |     <InfoHint>
      | ^^^^^^^^^^^^^^
> 797 |       <div>
      | ^^^^^^^^^^^^^^
> 798 |         <span className="font-semibold text-ink-900">ON</span> — {on}
      | ^^^^^^^^^^^^^^
> 799 |       </div>
      | ^^^^^^^^^^^^^^
> 800 |       <div className="mt-1">
      | ^^^^^^^^^^^^^^
> 801 |         <span className="font-semibold text-ink-900">OFF</span> — {off}
      | ^^^^^^^^^^^^^^
> 802 |       </div>
      | ^^^^^^^^^^^^^^
> 803 |     </InfoHint>
      | ^^^^^^^^^^^^^^
> 804 |   );
      | ^^^^ The component is created during render here
  805 |
  806 |   const deliverableStrategy = runConfig?.deliverable?.strategy ?? "streamed_text";
  807 |   const deliverableName = runConfig?.deliverable?.name ?? "output.md";  react-hooks/static-components
   848:10  warning  Error: Cannot create components during render

Components created during render will reset their state each time they are created. Declare components outside of render.

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/composer/CanvasView.tsx:848:10
  846 |           Smart planning
  847 |         </span>
> 848 |         <Toggle
      |          ^^^^^^ This component is created during render
  849 |           on={plannerOn}
  850 |           label="Smart planning"
  851 |           disabled={!onRunConfigChange}

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/composer/CanvasView.tsx:739:18
  737 |   //    they live under the Brief instruction (the workflow-level selection),
  738 |   //    not the per-node rail. ─────────────────────────────────────────────
> 739 |   const Toggle = ({
      |                  ^^
> 740 |     on,
      | ^^^^^^^
> 741 |     label,
      …
      | ^^^^^^^
> 766 |     </button>
      | ^^^^^^^
> 767 |   );
      | ^^^^ The component is created during render here
  768 |
  769 |   const InfoHint = ({ children }: { children: ReactNode }) => (
  770 |     <span className="group relative inline-flex flex-none">                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            react-hooks/static-components
   857:12  warning  Error: Cannot create components during render

Components created during render will reset their state each time they are created. Declare components outside of render.

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/composer/CanvasView.tsx:857:12
  855 |       <div className="flex items-center justify-between">
  856 |         <span className="flex items-center gap-1.5 font-sans text-[12.5px] font-semibold text-ink-900">
> 857 |           <OnOffHint
      |            ^^^^^^^^^ This component is created during render
  858 |             on="Pauses the run to ask clarifying questions about the brief, then uses your answers to fill in missing details."
  859 |             off="Runs immediately with the brief as written."
  860 |           />

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/composer/CanvasView.tsx:795:21
  793 |     </span>
  794 |   );
> 795 |   const OnOffHint = ({ on, off }: { on: string; off: string }) => (
      |                     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
> 796 |     <InfoHint>
      | ^^^^^^^^^^^^^^
> 797 |       <div>
      | ^^^^^^^^^^^^^^
> 798 |         <span className="font-semibold text-ink-900">ON</span> — {on}
      | ^^^^^^^^^^^^^^
> 799 |       </div>
      | ^^^^^^^^^^^^^^
> 800 |       <div className="mt-1">
      | ^^^^^^^^^^^^^^
> 801 |         <span className="font-semibold text-ink-900">OFF</span> — {off}
      | ^^^^^^^^^^^^^^
> 802 |       </div>
      | ^^^^^^^^^^^^^^
> 803 |     </InfoHint>
      | ^^^^^^^^^^^^^^
> 804 |   );
      | ^^^^ The component is created during render here
  805 |
  806 |   const deliverableStrategy = runConfig?.deliverable?.strategy ?? "streamed_text";
  807 |   const deliverableName = runConfig?.deliverable?.name ?? "output.md";     react-hooks/static-components
   863:10  warning  Error: Cannot create components during render

Components created during render will reset their state each time they are created. Declare components outside of render.

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/composer/CanvasView.tsx:863:10
  861 |           Confirm requirements first
  862 |         </span>
> 863 |         <Toggle
      |          ^^^^^^ This component is created during render
  864 |           on={clarifyOn}
  865 |           label="Confirm requirements first"
  866 |           disabled={!onRunConfigChange}

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/composer/CanvasView.tsx:739:18
  737 |   //    they live under the Brief instruction (the workflow-level selection),
  738 |   //    not the per-node rail. ─────────────────────────────────────────────
> 739 |   const Toggle = ({
      |                  ^^
> 740 |     on,
      | ^^^^^^^
> 741 |     label,
      …
      | ^^^^^^^
> 766 |     </button>
      | ^^^^^^^
> 767 |   );
      | ^^^^ The component is created during render here
  768 |
  769 |   const InfoHint = ({ children }: { children: ReactNode }) => (
  770 |     <span className="group relative inline-flex flex-none">                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    react-hooks/static-components
   877:12  warning  Error: Cannot create components during render

Components created during render will reset their state each time they are created. Declare components outside of render.

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/composer/CanvasView.tsx:877:12
  875 |       <div>
  876 |         <div className="mb-1.5 flex items-center gap-1.5 font-sans text-[12.5px] font-semibold text-ink-900">
> 877 |           <InfoHint>
      |            ^^^^^^^^ This component is created during render
  878 |             <div>
  879 |               <span className="font-semibold text-ink-900">Streamed text</span> — uses the agent&apos;s raw output.
  880 |             </div>

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/composer/CanvasView.tsx:769:20
  767 |   );
  768 |
> 769 |   const InfoHint = ({ children }: { children: ReactNode }) => (
      |                    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
> 770 |     <span className="group relative inline-flex flex-none">
      | ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
> 771 |       <Info className="h-3.5 w-3.5 cursor-help text-ink-300 hover:text-ink-500" />
      …
      | ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
> 778 |     </span>
      | ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
> 779 |   );
      | ^^^^ The component is created during render here
  780 |   // Same styled hover-tooltip box as InfoHint above, reused for a disabled
  781 |   // add/insert button's cap reason instead of a plain native `title=`.
  782 |   const CapTip = ({ reason, children }: { reason?: string; children: ReactNode }) => (                                                                                                                                    react-hooks/static-components
   954:10  warning  Error: Cannot create components during render

Components created during render will reset their state each time they are created. Declare components outside of render.

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/composer/CanvasView.tsx:954:10
  952 |           <span className="font-sans text-[12.5px] font-semibold text-ink-900">Internet access</span>
  953 |         </div>
> 954 |         <Toggle
      |          ^^^^^^ This component is created during render
  955 |           on={!!capabilities?.internet}
  956 |           label="Internet access"
  957 |           disabled={!onCapabilitiesChange}

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/composer/CanvasView.tsx:739:18
  737 |   //    they live under the Brief instruction (the workflow-level selection),
  738 |   //    not the per-node rail. ─────────────────────────────────────────────
> 739 |   const Toggle = ({
      |                  ^^
> 740 |     on,
      | ^^^^^^^
> 741 |     label,
      …
      | ^^^^^^^
> 766 |     </button>
      | ^^^^^^^
> 767 |   );
      | ^^^^ The component is created during render here
  768 |
  769 |   const InfoHint = ({ children }: { children: ReactNode }) => (
  770 |     <span className="group relative inline-flex flex-none">                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             react-hooks/static-components
  1091:39  warning  'i' is defined but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            @typescript-eslint/no-unused-vars
  1175:12  warning  Error: Cannot create components during render

Components created during render will reset their state each time they are created. Declare components outside of render.

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/composer/CanvasView.tsx:1175:12
  1173 |             style={{ left: chainEndX, top: chainEndY }}
  1174 |           >
> 1175 |           <CapTip reason={canAddMore ? undefined : "Maximum 8 root agents are allowed"}>
       |            ^^^^^^ This component is created during render
  1176 |           <button
  1177 |             type="button"
  1178 |             aria-label="Add agent"

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/composer/CanvasView.tsx:782:18
  780 |   // Same styled hover-tooltip box as InfoHint above, reused for a disabled
  781 |   // add/insert button's cap reason instead of a plain native `title=`.
> 782 |   const CapTip = ({ reason, children }: { reason?: string; children: ReactNode }) => (
      |                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
> 783 |     <span className="group relative inline-flex">
      | ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
> 784 |       {children}
      …
      | ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
> 793 |     </span>
      | ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
> 794 |   );
      | ^^^^ The component is created during render here
  795 |   const OnOffHint = ({ on, off }: { on: string; off: string }) => (
  796 |     <InfoHint>
  797 |       <div>                                                                                                                                                                                                                                                   react-hooks/static-components
  1279:20  warning  Error: Cannot create components during render

Components created during render will reset their state each time they are created. Declare components outside of render.

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/composer/CanvasView.tsx:1279:20
  1277 |               <div>
  1278 |                 <p className="flex items-center gap-1.5 font-sans text-[13px] font-semibold text-ink-900">
> 1279 |                   <InfoHint>
       |                    ^^^^^^^^ This component is created during render
  1280 |                     The instruction sent to the workflow's first agent when this run starts — describe what
  1281 |                     you want built.
  1282 |                   </InfoHint>

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/composer/CanvasView.tsx:769:20
  767 |   );
  768 |
> 769 |   const InfoHint = ({ children }: { children: ReactNode }) => (
      |                    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
> 770 |     <span className="group relative inline-flex flex-none">
      | ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
> 771 |       <Info className="h-3.5 w-3.5 cursor-help text-ink-300 hover:text-ink-500" />
      …
      | ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
> 778 |     </span>
      | ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
> 779 |   );
      | ^^^^ The component is created during render here
  780 |   // Same styled hover-tooltip box as InfoHint above, reused for a disabled
  781 |   // add/insert button's cap reason instead of a plain native `title=`.
  782 |   const CapTip = ({ reason, children }: { reason?: string; children: ReactNode }) => (                                                                                  react-hooks/static-components
  1280:57  error    `'` can be escaped with `&apos;`, `&lsquo;`, `&#39;`, `&rsquo;`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          react/no-unescaped-entities

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/composer/ComposerPage.tsx
  223:10  warning  'draggedIdx' is assigned a value but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                @typescript-eslint/no-unused-vars
  233:7   warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/composer/ComposerPage.tsx:233:7
  231 |   useEffect(() => {
  232 |     if (!workflowId) {
> 233 |       setDeclaredCapabilities(undefined);
      |       ^^^^^^^^^^^^^^^^^^^^^^^ Avoid calling setState() directly within an effect
  234 |       return;
  235 |     }
  236 |     let cancelled = false;  react-hooks/set-state-in-effect
  267:9   warning  The 'defaultAgentIds' object construction makes the dependencies of useCallback Hook (at line 354) change on every render. To fix this, wrap the initialization of 'defaultAgentIds' in its own useMemo() Hook                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 react-hooks/exhaustive-deps

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/ppt/PPTTemplateGallery.tsx
  51:5  warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/ppt/PPTTemplateGallery.tsx:51:5
  49 |
  50 |   useEffect(() => {
> 51 |     setSavedCustomTemplates(loadCustomTemplates());
     |     ^^^^^^^^^^^^^^^^^^^^^^^ Avoid calling setState() directly within an effect
  52 |   }, []);
  53 |
  54 |   const filtered = useMemo(() => {  react-hooks/set-state-in-effect

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/prototype/CustomDesignSystemModal.tsx
  206:185  error  `'` can be escaped with `&apos;`, `&lsquo;`, `&#39;`, `&rsquo;`  react/no-unescaped-entities
  206:191  error  `'` can be escaped with `&apos;`, `&lsquo;`, `&#39;`, `&rsquo;`  react/no-unescaped-entities

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/prototype/CustomTemplateModal.tsx
  124:14  warning  'err' is defined but never used  @typescript-eslint/no-unused-vars

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/prototype/DesignSystemDetailModal.tsx
   46:5   warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/prototype/DesignSystemDetailModal.tsx:46:5
  44 |     if (!token) return;
  45 |     let cancelled = false;
> 46 |     setDetail(undefined);
     |     ^^^^^^^^^ Avoid calling setState() directly within an effect
  47 |     setIframeLoaded(false);
  48 |     getDesignSystem(token, system.id)
  49 |       .then((d) => { if (!cancelled) setDetail(d); })                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        react-hooks/set-state-in-effect
   55:39  warning  Compilation Skipped: Existing memoization could not be preserved

React Compiler has skipped optimizing this component because the existing manual memoization could not be preserved. The inferred dependencies did not match the manually specified dependencies, which could cause the value to change more or less frequently than expected. The inferred dependency was `detail.body`, but the source dependencies were [system.has_preview, detail?.body]. Inferred different dependency than source.

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/prototype/DesignSystemDetailModal.tsx:55:39
  53 |
  54 |   // For systems without components.html, generate a Blob URL from DESIGN.md
> 55 |   const generatedPreviewUrl = useMemo(() => {
     |                                       ^^^^^^^
> 56 |     if (system.has_preview) return null; // use the real endpoint instead
     | ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
> 57 |     if (!detail?.body) return null;
     | ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
> 58 |     const html = generateDesignSystemPreviewHtml(detail.body);
     | ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
> 59 |     const blob = new Blob([html], { type: "text/html" });
     | ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
> 60 |     return URL.createObjectURL(blob);
     | ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
> 61 |   }, [system.has_preview, detail?.body]);
     | ^^^^ Could not preserve existing manual memoization
  62 |
  63 |   // Revoke blob URL on unmount or when it changes
  64 |   useEffect(() => {  react-hooks/preserve-manual-memoization
  240:66  error    `'` can be escaped with `&apos;`, `&lsquo;`, `&#39;`, `&rsquo;`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           react/no-unescaped-entities

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/prototype/DesignSystemPicker.tsx
    3:30  warning  'useRef' is defined but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          @typescript-eslint/no-unused-vars
   39:5   warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/prototype/DesignSystemPicker.tsx:39:5
  37 |
  38 |   useEffect(() => {
> 39 |     setCustomSystems(loadCustomDesignSystems());
     |     ^^^^^^^^^^^^^^^^ Avoid calling setState() directly within an effect
  40 |   }, []);
  41 |
  42 |   const selected = useMemo(  react-hooks/set-state-in-effect
  337:71  error    `"` can be escaped with `&quot;`, `&ldquo;`, `&#34;`, `&rdquo;`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             react/no-unescaped-entities
  337:79  error    `"` can be escaped with `&quot;`, `&ldquo;`, `&#34;`, `&rdquo;`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             react/no-unescaped-entities
  361:69  error    `"` can be escaped with `&quot;`, `&ldquo;`, `&#34;`, `&rdquo;`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             react/no-unescaped-entities
  361:77  error    `"` can be escaped with `&quot;`, `&ldquo;`, `&#34;`, `&rdquo;`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             react/no-unescaped-entities

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/prototype/TemplateCard.tsx
  30:52  warning  'onSelect' is defined but never used  @typescript-eslint/no-unused-vars

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/prototype/TemplateGallery.tsx
  46:5  warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/components/workflow/prototype/TemplateGallery.tsx:46:5
  44 |   // Load saved custom templates from localStorage on mount
  45 |   useEffect(() => {
> 46 |     setSavedCustomTemplates(loadCustomTemplates());
     |     ^^^^^^^^^^^^^^^^^^^^^^^ Avoid calling setState() directly within an effect
  47 |   }, []);
  48 |
  49 |   const detailTemplate = useMemo(  react-hooks/set-state-in-effect

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/hooks/__tests__/useWorkflow.pipelineCancelled.test.ts
  23:10  warning  'beforeEach' is defined but never used  @typescript-eslint/no-unused-vars

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/hooks/useHandoffSocket.ts
  177:9  error    Error: Cannot access variable before it is declared

`connect` is accessed before it is declared, which prevents the earlier access from updating when this value changes over time.

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/hooks/useHandoffSocket.ts:177:9
  175 |       setLastError(`Connection lost. Reconnecting in ${Math.round(delay / 1000)}s… (attempt ${retryCountRef.current})`);
  176 |       retryTimeoutRef.current = setTimeout(() => {
> 177 |         connect();
      |         ^^^^^^^ `connect` accessed before it is declared
  178 |       }, delay);
  179 |     };
  180 |   }, [url, cleanup]);

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/hooks/useHandoffSocket.ts:91:3
   89 |   }, []);
   90 |
>  91 |   const connect = useCallback(() => {
      |   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
>  92 |     const currentToken = getToken();
      | ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
>  93 |     if (!currentToken || !url) {
      …
      | ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
> 179 |     };
      | ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
> 180 |   }, [url, cleanup]);
      | ^^^^^^^^^^^^^^^^^^^^^^ `connect` is declared here
  181 |
  182 |   const send = useCallback((message: string): boolean => {
  183 |     if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {  react-hooks/immutability
  202:7  warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/hooks/useHandoffSocket.ts:202:7
  200 |     } else {
  201 |       cleanup();
> 202 |       setConnectionStatus("disconnected");
      |       ^^^^^^^^^^^^^^^^^^^ Avoid calling setState() directly within an effect
  203 |     }
  204 |
  205 |     return () => {                                                                                                                                                                                                                                                                                                                   react-hooks/set-state-in-effect

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/hooks/useRunChat.test.ts
  450:8   warning  '_r' is defined but never used  @typescript-eslint/no-unused-vars
  450:27  warning  '_p' is defined but never used  @typescript-eslint/no-unused-vars

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/hooks/useRunChat.ts
  596:6  warning  React Hook useCallback has a missing dependency: 'runId'. Either include it or remove the dependency array  react-hooks/exhaustive-deps

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/hooks/useRunStateStore.ts
  519:10  error  Error: Cannot access refs during render

React refs are values that are not needed for rendering. Refs should only be accessed outside of render, such as in event handlers or effects. Accessing a ref value (the `current` property) during render can cause your component not to update as expected (https://react.dev/reference/react/useRef).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/hooks/useRunStateStore.ts:519:10
  517 |   }, []);
  518 |
> 519 |   return {
      |          ^
> 520 |     viewed: viewedState,
      | ^^^^^^^^^^^^^^^^^^^^^^^^
> 521 |     viewedRunId: viewedRunIdRef.current,
      …
> 529 |     has,
      | ^^^^^^^^^^^^^^^^^^^^^^^^
> 530 |     remove,
      | ^^^^^^^^^^^^^^^^^^^^^^^^
> 531 |   };
      | ^^^^ Cannot access ref value during render
  532 | }
  533 |  react-hooks/refs
  521:18  error  Error: Cannot access refs during render

React refs are values that are not needed for rendering. Refs should only be accessed outside of render, such as in event handlers or effects. Accessing a ref value (the `current` property) during render can cause your component not to update as expected (https://react.dev/reference/react/useRef).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/hooks/useRunStateStore.ts:521:18
  519 |   return {
  520 |     viewed: viewedState,
> 521 |     viewedRunId: viewedRunIdRef.current,
      |                  ^^^^^^^^^^^^^^^^^^^^^^ Cannot access ref value during render
  522 |     handleFrame,
  523 |     update,
  524 |     updatePipelineState,                                                                                                             react-hooks/refs

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/hooks/useRunStream.ts
  193:7  warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/hooks/useRunStream.ts:193:7
  191 |     if (typeof window === "undefined") return;
  192 |     if (!enabled || !runId) {
> 193 |       setPhase("idle");
      |       ^^^^^^^^ Avoid calling setState() directly within an effect
  194 |       return;
  195 |     }
  196 |  react-hooks/set-state-in-effect

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/hooks/useSpeechRecognition.ts
  75:5  warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/hooks/useSpeechRecognition.ts:75:5
  73 |         : null;
  74 |
> 75 |     setIsSupported(!!SpeechRecognitionAPI);
     |     ^^^^^^^^^^^^^^ Avoid calling setState() directly within an effect
  76 |
  77 |     if (SpeechRecognitionAPI) {
  78 |       const recognition = new SpeechRecognitionAPI();  react-hooks/set-state-in-effect

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/hooks/useTextToSpeech.ts
  22:5  warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/hooks/useTextToSpeech.ts:22:5
  20 |
  21 |   useEffect(() => {
> 22 |     setIsSupported(
     |     ^^^^^^^^^^^^^^ Avoid calling setState() directly within an effect
  23 |       typeof window !== "undefined" && "speechSynthesis" in window
  24 |     );
  25 |   }, []);  react-hooks/set-state-in-effect

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/hooks/useTheme.ts
  22:5  warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/hooks/useTheme.ts:22:5
  20 |   useEffect(() => {
  21 |     const current = document.documentElement.getAttribute("data-theme");
> 22 |     setThemeState(current === "dark" ? "dark" : "light");
     |     ^^^^^^^^^^^^^ Avoid calling setState() directly within an effect
  23 |   }, []);
  24 |
  25 |   const setTheme = useCallback((next: Theme) => {  react-hooks/set-state-in-effect

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/hooks/useWorkflow.imagePayload.test.ts
  25:7  warning  '_runId' is defined but never used    @typescript-eslint/no-unused-vars
  26:7  warning  '_payload' is defined but never used  @typescript-eslint/no-unused-vars

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/hooks/useWorkflow.regenerateReset.test.ts
  20:10  warning  'beforeEach' is defined but never used  @typescript-eslint/no-unused-vars

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/lib/parsers/pptParser.ts
  84:14  warning  'e2' is defined but never used  @typescript-eslint/no-unused-vars

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/providers/RunConnectionProvider.tsx
  304:5  warning  Error: Calling setState synchronously within an effect can trigger cascading renders

Effects are intended to synchronize state between React and external systems such as manually updating the DOM, state management libraries, or other platform APIs. In general, the body of an effect should do one or both of the following:
* Update external systems with the latest state from React.
* Subscribe for updates from some external system, calling setState in a callback function when external state changes.

Calling setState synchronously within an effect body causes cascading renders that can hurt performance, and is not recommended. (https://react.dev/learn/you-might-not-need-an-effect).

/Users/bilala/Developer/Projects/VELOCITY-AI/frontend/src/providers/RunConnectionProvider.tsx:304:5
  302 |   // Boot: resolve the token client-side and do the first server-derived attach.
  303 |   useEffect(() => {
> 304 |     setTokenState(getToken());
      |     ^^^^^^^^^^^^^ Avoid calling setState() directly within an effect
  305 |     void refreshLiveRuns();
  306 |   }, [refreshLiveRuns]);
  307 |  react-hooks/set-state-in-effect

✖ 287 problems (44 errors, 243 warnings)
  1 error and 4 warnings potentially fixable with the `--fix` option.

tflint (infra).......................................(no files to check)Skipped
