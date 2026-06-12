---
name: brainstorm
description: 'Explore requirements and approaches through collaborative dialogue before writing a requirements document. Use when the user says "let''s brainstorm", "what should we build", "help me think through X", presents a problem with multiple solutions, or seems unsure about scope or direction.'
---

# Brainstorm a Feature or Improvement

Brainstorming helps answer **WHAT** to build through collaborative dialogue. It precedes `plan`, which answers **HOW** to build it.

The output of this workflow is a **requirements document** — a durable artifact strong enough that planning does not need to invent product behavior, scope boundaries, or success criteria.

This skill does not implement code. It explores, clarifies, and documents decisions for later planning or execution.

## Core Principles

1. **Assess scope first** - Match the amount of ceremony to the size and ambiguity of the work.
2. **Be a thinking partner** - Suggest alternatives, challenge assumptions, and explore what-ifs instead of only extracting requirements.
3. **Resolve product decisions here** - User-facing behavior, scope boundaries, and success criteria belong in this workflow. Detailed implementation belongs in planning.
4. **Right-size the artifact** - Simple work gets a compact requirements document. Larger work gets a fuller document. Do not add ceremony that does not help planning.
5. **Apply YAGNI to carrying cost** - Prefer the simplest approach that delivers meaningful value.

## Interaction Rules

1. **Ask one question at a time** - One question per turn, even when sub-questions feel related.
2. **Prefer structured options** - Use numbered options when choosing one direction, one priority, or one next step.
3. **Use prose only when the question is genuinely open** - Drop structured options when the answer is inherently narrative or diagnostic.

## Workflow

### Phase 0: Assess and Route

#### 0.1 Assess Whether Brainstorming Is Needed

**Clear requirements indicators:**
- Specific acceptance criteria provided
- Referenced existing patterns to follow
- Described exact expected behavior
- Constrained, well-defined scope

**If requirements are already clear:** Keep the interaction brief. Confirm understanding and present concise next-step options rather than forcing a long brainstorm.

#### 0.2 Assess Scope

Use the feature description plus a light repo scan to classify the work:
- **Lightweight** - small, well-bounded, low ambiguity
- **Standard** - normal feature or bounded refactor with some decisions to make
- **Deep** - cross-cutting, strategic, or highly ambiguous

### Phase 1: Understand the Idea

#### 1.1 Existing Context Scan

Scan the repo before substantive brainstorming:
- Search for the topic, check if something similar already exists
- Read relevant existing artifacts (brainstorm, plan, spec, feature doc)
- Verify before claiming — when the brainstorm touches checkable infrastructure, read the relevant source files to confirm what actually exists

#### 1.2 Collaborative Dialogue

- Ask what the user is already thinking before offering your own ideas
- Start broad (problem, users, value) then narrow (constraints, exclusions, edge cases)
- Clarify the problem frame, validate assumptions, and ask about success criteria
- Make requirements concrete enough that planning will not need to invent behavior
- Bring ideas, alternatives, and challenges instead of only interviewing

**Exit condition:** Continue until the idea is clear OR the user explicitly wants to proceed.

### Phase 2: Explore Approaches

If multiple plausible directions remain, propose **2-3 concrete approaches**. Otherwise state the recommended direction directly.

For each approach, provide:
- Brief description (2-3 sentences)
- Pros and cons
- Key risks or unknowns
- When it's best suited

After presenting all approaches, state your recommendation and explain why.

### Phase 3: Capture the Requirements

Write a requirements document when the conversation produced durable decisions worth preserving:

```markdown
# [Feature Name]

## Problem Statement
What problem are we solving?

## Proposed Solution
High-level approach

## Requirements
- R1. [Requirement 1]
- R2. [Requirement 2]

## Scope Boundaries
What's NOT included

## Open Questions
Items to resolve during implementation
```

### Phase 4: Handoff

Present next-step options:
1. **Plan the implementation** - hand off to `plan` skill
2. **Start building** - hand off to `work` skill
3. **Done for now** - save the requirements for later
