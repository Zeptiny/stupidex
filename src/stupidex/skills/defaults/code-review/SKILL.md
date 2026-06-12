---
name: code-review
description: 'Review code for bugs, style issues, and improvements. Use when the user says "review this", "check my code", "code review", or before merging changes.'
---

# Code Review

Perform thorough code reviews to find real bugs, security issues, and design problems.

## Workflow

### Phase 1: Context Gathering

1. **Understand the change**
   - What problem does this solve?
   - What's the scope?
   - What are the key decisions?

2. **Read the code**
   - All changed files
   - Related code for context
   - Tests and documentation

### Phase 2: Review

Check for:

#### Bugs (Primary Focus)
- Logic errors, off-by-one mistakes
- Missing edge cases
- Race conditions
- Error handling gaps
- Null/undefined handling

#### Security
- Injection vulnerabilities
- Auth/authorization issues
- Data exposure
- Input validation

#### Design
- Follows existing patterns?
- Appropriate abstractions?
- Clear naming?
- Separation of concerns?

#### Performance
- Obvious bottlenecks?
- N+1 queries?
- Unnecessary allocations?

#### Testing
- Adequate coverage?
- Meaningful assertions?
- Edge cases covered?

### Phase 3: Report

Structure findings by priority:

```
**Verdict:** [Approve | Request Changes | Comment]

**Findings:**

**[P0/P1/P2/P3] Title** — `file.ts:42`
- What: Description
- Why: Impact
- Fix: Suggestion (if not obvious)

**Strengths:**
What was done well
```

## Priority Levels

- **P0 (Critical)** - Must fix before merge
- **P1 (Urgent)** - Should fix soon
- **P2 (Normal)** - Fix when convenient
- **P3 (Low)** - Nice to have

## Key Principles

- **Be certain** - If you call something a bug, be confident it actually is one
- **Be constructive** - Suggest fixes, don't just complain
- **Respect scope** - Review the change, not the entire codebase
- **No flattery** - Be specific about what's good, not generic praise
- **Cite evidence** - Every finding needs a file:line reference
