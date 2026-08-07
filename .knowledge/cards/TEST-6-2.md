---
id: TEST-6-2
type: test
status: done
area: [sse, workflow, agents, auth, artifacts]
summary: >-
  6.2 What is NOT (yet) verified — close before production sign-off
source: .planning/TEST-REGISTER.md#6-2-what-is-not-yet-verified-close-before-produc
covers: [TS-V-08, TS-U-06]
---

### 6.2 What is NOT (yet) verified — close before production sign-off

| Gap | Why | Action |
|---|---|---|
| **No committed Playwright suite** | campaign used throwaway `/tmp` harnesses (not in repo) | **§7-G1 — build the suite from §3.** Highest priority. |
| ISS-004 `app-sdlc-governance` anti-tool-XML | agent sits deep in app_builder; never reached the live window | 🟠 OFFLINE-ONLY — drive a full app_builder run to completion and assert 0 tool-XML in its stream |
| Migration with source repos (TS-V-08/09) | needs repo inputs the bare-brief harness lacks | 🟠 — provide a fixture source repo, run mulesoft + dotnet to a deliverable |
| Multi-worker isolated-write (fan-out) | offline harness runs `shared_read` | drive a live fan-out where 2 workers write different files; assert no cross-contamination |
| Live `has_git=True` workspace provisioning | forward ECS seam | exercise the brownfield/repo workflow live |
| Prototype surgical-diff revise (TS-U-06) | not in the campaign | author the Playwright case |
