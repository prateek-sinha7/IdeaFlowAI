---
name: incident-runbooks
display_name: Incident Runbook Templates
description: Create structured incident response runbooks with step-by-step procedures, escalation paths, and recovery actions.
category: research
isBeta: false
tags:
- incident-response
- runbooks
- on-call
- escalation
- recovery
- sre
- operations
- procedures
---

# Incident Runbook Templates

Production-ready templates for incident response runbooks covering detection, triage, mitigation, resolution, and communication.

## When to Use This Skill

- Creating incident response procedures
- Building service-specific runbooks
- Establishing escalation paths
- Documenting recovery procedures
- Responding to active incidents
- Onboarding on-call engineers

## Severity Levels

| Severity | Impact                     | Response Time     | Example                 |
| -------- | -------------------------- | ----------------- | ----------------------- |
| **SEV1** | Complete outage, data loss | 15 min            | Production down         |
| **SEV2** | Major degradation          | 30 min            | Critical feature broken |
| **SEV3** | Minor impact               | 2 hours           | Non-critical bug        |
| **SEV4** | Minimal impact             | Next business day | Cosmetic issue          |

## Runbook Structure

```
1. Overview & Impact
2. Detection & Alerts
3. Initial Triage
4. Mitigation Steps
5. Root Cause Investigation
6. Resolution Procedures
7. Verification & Rollback
8. Communication Templates
9. Escalation Matrix
```

## Best Practices

### Do's
- **Keep runbooks updated** — Review after every incident
- **Test runbooks regularly** — Game days, chaos engineering
- **Include rollback steps** — Always have an escape hatch
- **Document assumptions** — What must be true for steps to work
- **Link to dashboards** — Quick access during stress
- **Version control** — Track changes to procedures
- **Include contact info** — On-call rosters, vendor support numbers

### Don'ts
- **Don't assume knowledge** — Write for 3 AM brain
- **Don't skip verification** — Confirm each step worked
- **Don't forget communication** — Keep stakeholders informed
- **Don't hardcode values** — Use variables for environment-specific data
- **Don't write novels** — Keep steps concise and actionable

## Communication Template

```
Subject: [SEV{N}] {Service} - {Brief Description}

Impact: {Who is affected and how}
Status: {Investigating | Identified | Monitoring | Resolved}
Start Time: {UTC timestamp}
ETA: {Expected resolution time or "Investigating"}
Updates: {Frequency of updates}

Next update in {N} minutes.
```

## Escalation Matrix

| Condition                          | Escalate To         |
|------------------------------------|---------------------|
| No progress after 15 min (SEV1)   | Engineering Manager |
| Customer data at risk              | Security + Legal    |
| Revenue impact > $X               | VP Engineering      |
| Third-party dependency             | Vendor support      |
| Cannot reproduce                   | Original developer  |
