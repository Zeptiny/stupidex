---
name: plan
description: 'Create structured plans for any multi-step task -- software features, research workflows, events, study plans, or any goal that benefits from structured breakdown. Use when the user says "plan this", "create a plan", "write a tech plan", "plan the implementation", "how should we build", "what''s the approach for", "break this down", or when a brainstorm/requirements document is ready for planning.'
---

# Create Technical Plan

`brainstorm` defines **WHAT** to build. `plan` defines **HOW** to build it. `work` executes the plan. A prior brainstorm is useful context but never required — `plan` works from any input: a requirements doc, a bug report, a feature idea, or a rough description.

This workflow produces a durable implementation plan. It does **not** implement code, run tests, or learn from execution-time results.

## Core Principles

1. **Use requirements as the source of truth** - If `brainstorm` produced a requirements document, planning should build from it rather than re-inventing behavior.
2. **Decisions, not code** - Capture approach, boundaries, files, dependencies, risks, and test scenarios. Do not pre-write implementation code.
3. **Research before structuring** - Explore the codebase before finalizing the plan.
4. **Right-size the artifact** - Small work gets a compact plan. Large work gets more structure.
5. **Keep the plan portable** - The plan should work as a living document or review artifact without embedding tool-specific instructions.

## Plan Quality Bar

Every plan should contain:
- A clear problem frame and scope boundary
- Concrete requirements traceability
- Repo-relative file paths (never absolute paths)
- Decisions with rationale, not just tasks
- Existing patterns or code references to follow
- Test scenarios for each feature-bearing unit
- Clear dependencies and sequencing

## Workflow

### Phase 0: Resume, Source, and Scope

#### 0.1 Resume Existing Plan Work

If the user references an existing plan file:
- Read it
- Confirm whether to update it in place or create a new plan
- If updating, revise only the still-relevant sections

#### 0.2 Find Upstream Requirements Document

Search for requirements documents that match the topic. If found, use as primary input.

#### 0.3 Planning Bootstrap (No Requirements Doc or Unclear Input)

If no relevant requirements document exists, or the input needs more structure:
- Assess whether the request is already clear enough for direct technical planning
- If the ambiguity is mainly product framing, recommend `brainstorm` as a suggestion — but always offer to continue planning here as well
- If the user wants to continue, run the planning bootstrap to establish:
  - Problem frame
  - Intended behavior
  - Scope boundaries and obvious non-goals
  - Success criteria

#### 0.4 Assess Plan Depth

- **Lightweight** - small, well-bounded, low ambiguity
- **Standard** - normal feature or bounded refactor with some technical decisions
- **Deep** - cross-cutting, strategic, high-risk, or highly ambiguous

### Phase 1: Gather Context

#### 1.1 Local Research

- Search for relevant code patterns, conventions, and existing implementations
- Read key files that the plan will touch or reference
- Check for existing tests and test patterns

#### 1.2 Decide on External Research

- If the codebase has strong local patterns, lean toward skipping external research
- If the topic is high-risk (security, payments, external APIs), lean toward external research
- If exploring unfamiliar territory, research current best practices

### Phase 2: Resolve Planning Questions

Build a planning question list from gaps discovered in research.

For each question, decide whether it should be:
- **Resolved during planning** - the answer is knowable from repo context or user choice
- **Deferred to implementation** - the answer depends on code changes or runtime behavior

Ask the user only when the answer materially affects architecture, scope, or risk.

### Phase 3: Structure the Plan

#### 3.1 Break Work into Implementation Units

Each unit should represent one meaningful change that could be an atomic commit.

Good units are:
- Focused on one component, behavior, or integration seam
- Usually touching a small cluster of related files
- Ordered by dependency
- Concrete enough for execution

Each unit carries a stable **U-ID** (`U1`, `U2`, …).

#### 3.2 Define Each Implementation Unit

For each unit, include:
- **Goal** - what this unit accomplishes
- **Requirements** - which requirements it advances (cite R-IDs)
- **Dependencies** - what must exist first (cite by U-ID)
- **Files** - repo-relative file paths to create, modify, or test
- **Approach** - key decisions, data flow, component boundaries
- **Patterns to follow** - existing code or conventions to mirror
- **Test scenarios** - specific test cases to write
- **Verification** - how to know the unit is complete

### Phase 4: Write the Plan

```markdown
---
title: [Plan Title]
type: [feat|fix|refactor]
status: active
date: YYYY-MM-DD
---

# [Plan Title]

## Summary

[1-3 line prose summary]

---

## Problem Frame

[The user/business problem and context]

---

## Requirements

- R1. [Requirement 1]
- R2. [Requirement 2]

---

## Scope Boundaries

- [Explicit non-goal or exclusion]

---

## Context & Research

### Relevant Code and Patterns

- [Existing file, class, component, or pattern to follow]

---

## Key Technical Decisions

- [Decision]: [Rationale]

---

## Implementation Units

- U1. **[Name]**

**Goal:** [What this unit accomplishes]

**Requirements:** [R1, R2]

**Dependencies:** [None / U1]

**Files:**
- Create: `path/to/new_file`
- Modify: `path/to/existing_file`
- Test: `path/to/test_file`

**Approach:**
- [Key design or sequencing decision]

**Patterns to follow:**
- [Existing file, class, or pattern]

**Test scenarios:**
- [Scenario: specific input/action -> expected outcome]

**Verification:**
- [Outcome that should hold when this unit is complete]

---

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| [Meaningful risk] | [How it is addressed or accepted] |

---

## Open Questions

### Deferred to Implementation

- [Question or unknown]: [Why it is intentionally deferred]
```

#### 4.1 Planning Rules

- **All file paths must be repo-relative** — never use absolute paths
- Prefer path plus class/component/pattern references over brittle line numbers
- Do not include implementation code — no imports, exact method signatures, or framework-specific syntax
- Do not include git commands, commit messages, or exact test command recipes
- Do not expand implementation units into micro-step instructions

### Phase 5: Final Review and Handoff

Before finalizing, check:
- Every major decision is grounded in the origin document or research
- Each implementation unit is concrete, dependency-ordered, and implementation-ready
- Each feature-bearing unit has test scenarios
- Deferred items are explicit

Present next-step options:
1. **Execute the plan** - hand off to `work` skill
2. **Review the plan** - discuss specific sections
3. **Done for now** - save the plan for later
