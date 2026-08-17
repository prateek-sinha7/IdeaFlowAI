---
name: feature-design-assistant
display_name: Feature Design Assistant
description: Turn ideas into fully formed designs and specs through structured information gathering and collaborative dialogue.
category: planning
isBeta: false
tags:
- feature-design
- requirements
- specifications
- architecture
- planning
- collaborative
- user-stories
- technical-design
---

# Feature Design Assistant

Help turn ideas into fully formed designs and specs through structured information gathering and collaborative validation.

## Phase 1: Context Discovery

First, explore the codebase to understand:
- Project structure and tech stack
- Existing patterns and conventions
- Related features or modules
- Recent changes in relevant areas

## Phase 2: Structured Information Gathering

### Round 1: Core Requirements

1. **Goal**: What is the primary goal? (New Functionality / Enhancement / Bug Fix / Refactoring)
2. **Users**: Who are the primary users? (End Users / Admins / Developers / System)
3. **Scope**: What is the expected scope? (Small 1-2 days / Medium 3-5 days / Large 1-2 weeks / Unsure)
4. **Description**: Brief description of the desired behavior

### Round 2: Technical Constraints

1. **Dependencies**: External services or APIs needed?
2. **Data Model**: New entities or schema changes required?
3. **Performance**: Any latency or throughput requirements?
4. **Security**: Authentication, authorization, or data sensitivity concerns?

### Round 3: Acceptance Criteria

1. **Happy Path**: Primary success scenarios
2. **Edge Cases**: Error handling and boundary conditions
3. **Non-Functional**: Performance, accessibility, compatibility requirements

## Phase 3: Design Output

### Feature Specification

```markdown
## Feature: [Name]

### Overview
[1-2 sentence summary]

### User Stories
- As a [role], I want to [action] so that [benefit]

### Technical Design
- Architecture approach
- Data model changes
- API endpoints
- Component structure

### Acceptance Criteria
- [ ] Criterion 1
- [ ] Criterion 2

### Open Questions
- Question 1?
- Question 2?
```

## When to Use

- Planning new features before implementation
- Designing architecture for significant changes
- Collaborating on technical specifications
- Clarifying ambiguous requirements
- Breaking down large features into actionable tasks
