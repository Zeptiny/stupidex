---
name: debug
description: 'Systematically find root causes and fix bugs. Use when debugging errors, investigating test failures, or when stuck on a problem after failed fix attempts. Also use when the user says "debug this", "why is this failing", "fix this bug", "trace this error", or pastes stack traces or error messages.'
---

# Debug and Fix

Find root causes, then fix them. This skill investigates bugs systematically — tracing the full causal chain before proposing a fix.

## Core Principles

1. **Investigate before fixing.** Do not propose a fix until you can explain the full causal chain from trigger to symptom with no gaps.
2. **One change at a time.** Test one hypothesis, change one thing. If you're changing multiple things to "see if it helps," stop — that is shotgun debugging.
3. **When stuck, diagnose why — don't just try harder.**

## Execution Flow

| Phase | Name | Purpose |
|-------|------|---------|
| 0 | Triage | Parse input, reach clear problem statement |
| 1 | Investigate | Reproduce the bug, trace the code path |
| 2 | Root Cause | Form hypotheses, test them, confirm causal chain |
| 3 | Fix | Test-first fix with workspace safety checks |
| 4 | Summary | Structured summary of what was found and fixed |

---

### Phase 0: Triage

Parse the input and reach a clear problem statement.

**If the input references an issue tracker** (GitHub `#123`, URL): fetch the issue details using `gh issue view` or by fetching the URL content.

**Everything else** (stack traces, error messages, descriptions of broken behavior): Proceed directly to Phase 1.

**Questions:**
- Do not ask questions by default — investigate first (read code, run tests, trace errors)
- Only ask when a genuine ambiguity blocks investigation and cannot be resolved by reading code or running tests
- When asking, ask one specific question

---

### Phase 1: Investigate

#### 1.1 Reproduce the bug

Confirm the bug exists and understand its behavior. Run the test, trigger the error, follow reported reproduction steps.

- **Does not reproduce after 2-3 attempts:** Document what was tried and what conditions appear to be missing.
- **Cannot reproduce at all:** Document what was tried. Ask the user for more details about the environment or conditions.

#### 1.2 Verify environment sanity

Before deep code tracing, confirm the environment is what you think it is:
- Correct branch checked out; no unintended uncommitted changes
- Dependencies installed and up to date
- Expected interpreter or runtime version
- Required env vars present and non-empty
- No stale build artifacts

#### 1.3 Trace the code path

Read the relevant source files. Follow the execution path from entry point to where the error manifests. Trace backward through the call chain:

- Start at the error
- Ask "where did this value come from?" and "who called this?"
- Keep going upstream until finding the point where valid state first became invalid
- Do not stop at the first function that looks wrong — the root cause is where bad state originates, not where it is first observed

As you trace:
- Check recent changes: `git log --oneline -10 -- [file]`
- If the bug looks like a regression, use `git log` to find when it was introduced

---

### Phase 2: Root Cause

**Form hypotheses** ranked by likelihood. For each, state:
- What is wrong and where (file:line)
- The causal chain: how the trigger leads to the observed symptom, step by step

**Causal chain gate:** Do not proceed to Phase 3 until you can explain the full causal chain — from the original trigger through every step to the observed symptom — with no gaps.

#### Present findings

Once the root cause is confirmed, present:
- The root cause (causal chain summary with file:line references)
- The proposed fix and which files would change
- Which tests to add or modify to prevent recurrence

Then offer next steps:
1. **Fix it now** — proceed to Phase 3
2. **Diagnosis only** — skip the fix, end with the summary

#### Smart escalation

If 2-3 hypotheses are exhausted without confirmation, diagnose why:

| Pattern | Diagnosis | Next move |
|---------|-----------|-----------|
| Hypotheses point to different subsystems | Architecture/design problem | Present findings, suggest brainstorm |
| Evidence contradicts itself | Wrong mental model | Step back, re-read without assumptions |
| Works locally, fails in CI/prod | Environment problem | Focus on env differences |

---

### Phase 3: Fix

**Workspace check:** Before editing files:
- Check for uncommitted changes (`git status`). If the user has unstaged work in files that need modification, confirm before editing.
- If on the default branch, ask whether to create a feature branch first.

**Test-first:**
1. Write a failing test that captures the bug (or use the existing failing test)
2. Verify it fails for the right reason — the root cause, not unrelated setup
3. Implement the minimal fix — address the root cause and nothing else
4. Verify the test passes
5. Run the broader test suite for regressions

**3 failed fix attempts = smart escalation.** Diagnose using the table from Phase 2. If fixes keep failing, the root cause identification was likely wrong. Return to Phase 2.

---

### Phase 4: Summary

Write a structured summary:

```
## Debug Summary
**Problem**: [What was broken]
**Root Cause**: [Full causal chain, with file:line references]
**Recommended Tests**: [Tests to add/modify to prevent recurrence]
**Fix**: [What was changed — or "diagnosis only" if Phase 3 was skipped]
**Confidence**: [High/Medium/Low]
```

If Phase 3 was skipped (user chose "Diagnosis only"), stop after the summary.
