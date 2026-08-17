---
name: postmortem-writing
display_name: Postmortem Writing
description: Write effective blameless postmortems with root cause analysis, timelines, and action items.
category: research
isBeta: false
tags:
- incident-response
- postmortem
- root-cause-analysis
- blameless
- action-items
- organizational-learning
- sre
---

# Postmortem Writing

Comprehensive guide to writing effective, blameless postmortems that drive organizational learning and prevent incident recurrence.

## When to Use This Skill

- Conducting post-incident reviews
- Writing postmortem documents
- Facilitating blameless postmortem meetings
- Identifying root causes and contributing factors
- Creating actionable follow-up items
- Building organizational learning culture

## Core Concepts

### Blameless Culture

| Blame-Focused            | Blameless                         |
| ------------------------ | --------------------------------- |
| "Who caused this?"       | "What conditions allowed this?"   |
| "Someone made a mistake" | "The system allowed this mistake" |
| Punish individuals       | Improve systems                   |
| Hide information         | Share learnings                   |
| Fear of speaking up      | Psychological safety              |

### Postmortem Triggers

- SEV1 or SEV2 incidents
- Customer-facing outages > 15 minutes
- Data loss or security incidents
- Near-misses that could have been severe
- Novel failure modes
- Incidents requiring unusual intervention

## Postmortem Timeline

```
Day 0:     Incident occurs
Day 1-2:   Draft postmortem document
Day 3-5:   Postmortem meeting
Day 5-7:   Finalize document, create tickets
Week 2+:   Action item completion
Quarterly: Review patterns across incidents
```

## Document Structure

1. **Title & Metadata**: Date, duration, severity, participants
2. **Summary**: 2-3 sentence overview
3. **Impact**: Quantified user/business impact
4. **Timeline**: Minute-by-minute incident progression
5. **Root Cause**: Why the incident happened (5 Whys)
6. **Contributing Factors**: Conditions that enabled the failure
7. **What Went Well**: Effective response elements
8. **What Went Poorly**: Response gaps
9. **Action Items**: Owner + deadline for each remediation
10. **Lessons Learned**: Generalizable takeaways

## Best Practices

1. **Start quickly**: Draft within 24-48 hours while memory is fresh
2. **Include timeline**: Precise timestamps for detection, response, resolution
3. **Quantify impact**: Users affected, revenue lost, SLA burned
4. **Use 5 Whys**: Dig deeper than the proximate cause
5. **Assign owners**: Every action item needs a named owner and deadline
6. **Follow up**: Track action item completion in subsequent reviews
7. **Share widely**: Publish postmortems to normalize learning from failure
