---
name: code-reviewer-expert
display_name: Code Reviewer Expert
description: Comprehensive code review skill for TypeScript, JavaScript, Python, Swift, Kotlin, Go. Includes automated code analysis, best practice checking, security scanning, and review checklist generation.
category: specialist
isBeta: false
tags:
- code-review
- quality
- best-practices
- security
- testing
---

# Code Reviewer Expert

Complete toolkit for thorough code reviews with modern tools and best practices.

## Core Capabilities

### 1. PR Analyzer
- Automated diff analysis
- Change impact assessment
- Risk identification
- Review priority assignment

### 2. Code Quality Checker
- Deep static analysis
- Performance metrics
- Pattern detection
- Automated fix suggestions

### 3. Review Report Generator
- Structured review reports
- Issue categorization
- Actionable feedback
- Progress tracking

## Review Checklist

### Code Quality
- [ ] Follow established patterns and conventions
- [ ] No code duplication (DRY principle)
- [ ] Single responsibility per function/class
- [ ] Appropriate abstraction levels
- [ ] Clear, descriptive naming
- [ ] Reasonable function/method length
- [ ] No dead code or unused imports

### Performance
- [ ] No unnecessary re-renders (React)
- [ ] Efficient data structures and algorithms
- [ ] Proper caching where appropriate
- [ ] No N+1 query patterns
- [ ] Lazy loading for expensive operations
- [ ] Appropriate use of memoization

### Security
- [ ] Input validation on all user inputs
- [ ] No hardcoded secrets or credentials
- [ ] Parameterized queries (no SQL injection)
- [ ] Proper authentication checks
- [ ] Authorization verified at correct layers
- [ ] No sensitive data in logs
- [ ] Dependencies up to date (no known CVEs)

### Testing
- [ ] Unit tests for new logic
- [ ] Edge cases covered
- [ ] Mocks used appropriately (not excessively)
- [ ] Integration tests for API changes
- [ ] Test descriptions are clear
- [ ] No flaky tests introduced

### Error Handling
- [ ] Errors caught and handled gracefully
- [ ] Appropriate error messages for users
- [ ] Logging for debugging purposes
- [ ] Fallback behavior defined
- [ ] No swallowed exceptions

### Maintainability
- [ ] Code is self-documenting
- [ ] Complex logic has comments explaining "why"
- [ ] Types/interfaces defined for data structures
- [ ] Consistent code style throughout
- [ ] No magic numbers/strings

### API Design
- [ ] RESTful conventions followed
- [ ] Proper HTTP status codes
- [ ] Request/response schemas documented
- [ ] Backward compatibility maintained
- [ ] Rate limiting considered
- [ ] Pagination for list endpoints

## Common Anti-Patterns to Flag

### General
- God objects/classes (too many responsibilities)
- Deep nesting (>3 levels)
- Long parameter lists (>4 params)
- Feature envy (using another class's data extensively)
- Shotgun surgery (one change requires many file edits)

### TypeScript/JavaScript
- `any` type usage without justification
- Missing error boundaries in React
- Prop drilling through many levels
- useEffect with missing dependencies
- Synchronous operations that should be async

### Python
- Bare `except` clauses
- Mutable default arguments
- Global state modification
- Missing type hints on public interfaces
- Overly broad try/except blocks

### Go
- Ignoring errors (discarding error return)
- Goroutine leaks
- Race conditions with shared state
- Missing defer for cleanup

## Review Communication Best Practices

### Tone
- Be constructive, not critical
- Ask questions instead of making demands
- Acknowledge good patterns when you see them
- Distinguish blocking issues from suggestions

### Structure
- **Blocker**: Must fix before merge
- **Suggestion**: Would improve code but not required
- **Nitpick**: Style preference, non-blocking
- **Question**: Seeking understanding

### Feedback Examples

**Good**: "Consider using a discriminated union here — it would make the exhaustive type checking catch missing cases at compile time."

**Avoid**: "This is wrong. Use a union type."

## Tech Stack Coverage

**Languages:** TypeScript, JavaScript, Python, Go, Swift, Kotlin
**Frontend:** React, Next.js, React Native, Flutter
**Backend:** Node.js, Express, GraphQL, REST APIs
**Database:** PostgreSQL, Prisma, NeonDB, Supabase
**DevOps:** Docker, Kubernetes, Terraform, GitHub Actions
**Cloud:** AWS, GCP, Azure
