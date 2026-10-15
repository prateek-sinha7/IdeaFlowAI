"""Scratch pytest plugin for QA-KB-039 analysis. NOT part of the repo.

Patches ONLY in memory (monkeypatch, undone after the test) so the REAL test file runs under the
REAL conftest chain:

  QAKB039_VARIANT contains "fixed"   -> append the agreed second text-only turn to the
                                        prototype-build script (what the fixer would add)
  QAKB039_VARIANT contains "nogate"  -> neutralise FIX-612's placeholder gate, exactly as
                                        FIX-641 did, to prove the test still discriminates
  QAKB039_PROBE=<path>               -> read-only: dump what pipeline_complete / the event stream
                                        carry (agents_failed, status, agent_error count) to <path>
"""
import json
import os

import pytest

_TARGET = "test_qa_ps_027_placeholder_completion"


@pytest.fixture(autouse=True)
def _qakb039_variant(request, monkeypatch):
    mod = request.module
    if not mod.__name__.endswith(_TARGET):
        yield
        return
    variant = os.environ.get("QAKB039_VARIANT", "")
    if "fixed" in variant:
        orig = mod._prototype_placeholder_scripts

        def patched(agent_id):
            turns = list(orig(agent_id))
            if agent_id == "prototype-build":
                turns.append(mod._ScriptedTurn(texts=["Task complete."], usage=(5, 3)))
            return turns

        monkeypatch.setattr(mod, "_prototype_placeholder_scripts", patched)
    if "nogate" in variant:
        import agents.capabilities.deliverables._placeholder as _p

        monkeypatch.setattr(_p, "placeholder_narration_reason", lambda *a, **k: None)

    if "limit60" in variant:
        from app.core.config import settings as _s

        monkeypatch.setattr(_s, "AGENT_RECURSION_LIMIT", 60)

    probe = os.environ.get("QAKB039_PROBE")
    if probe:
        orig_pc = mod._pipeline_complete

        def probing(events):
            data = orig_pc(events)
            errs = [e for e in events if e.get("type") == "agent_error"]
            summary = {
                "variant": variant or "unfixed",
                "status": data.get("status"),
                "published_status": data.get("published_status"),
                "agents_failed": data.get("agents_failed"),
                "agents_completed": data.get("agents_completed"),
                "degraded_reason": data.get("degraded_reason"),
                "agent_error_events": [
                    {"agent_id": (e.get("data") or {}).get("agent_id"),
                     "recoverable": (e.get("data") or {}).get("recoverable")}
                    for e in errs
                ],
                "event_type_counts": {},
                "task_progress_payloads": [
                    e.get("data") for e in events if e.get("type") == "task_progress"
                ][:3] + [
                    e.get("data") for e in events if e.get("type") == "task_progress"
                ][-2:],
                "task_loop_progress_payloads": [
                    e.get("data") for e in events if e.get("type") == "task_loop_progress"
                ],
            }
            for e in events:
                t = e.get("type")
                summary["event_type_counts"][t] = summary["event_type_counts"].get(t, 0) + 1
            with open(probe, "w") as fh:
                json.dump(summary, fh, indent=2, default=str)
            return data

        monkeypatch.setattr(mod, "_pipeline_complete", probing)
    yield
