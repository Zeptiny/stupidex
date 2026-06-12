---
name: simplify-code
description: 'Simplify and refine recently changed code for clarity, reuse, quality, and efficiency while preserving behavior. Use when the user says "simplify this", "clean up the code", "refactor this", or after completing a feature to improve code quality.'
---

# Simplify Code

Review and simplify recently changed code for clarity, reuse, quality, and efficiency while preserving exact functionality.

## Step 1: Identify scope

Resolve the simplification scope in this order:

1. **If the user explicitly named a scope** (a file, a directory, "the function I just wrote"), use that scope.
2. **In a git repository**, default to the diff between the current branch and its base branch:
   ```bash
   git diff origin/main..
   ```
   If no upstream, fall back to staged + unstaged changes:
   ```bash
   git diff HEAD
   ```
3. **Outside a git repository**, review the most recently modified files mentioned by the user.

If none of the above produces a non-empty scope, ask the user what to simplify.

## Step 2: Review for issues

Review the changes for these categories:

### Code Reuse

1. **Search for existing utilities and helpers** that could replace newly written code
2. **Flag any new function that duplicates existing functionality** — suggest the existing function instead
3. **Flag inline logic that could use an existing utility** — hand-rolled string manipulation, manual path handling, custom type guards, etc.

### Code Quality

1. **Redundant state**: state that duplicates existing state, cached values that could be derived
2. **Parameter sprawl**: adding new parameters instead of restructuring
3. **Copy-paste with slight variation**: near-duplicate code blocks that should be unified
4. **Leaky abstractions**: exposing internal details that should be encapsulated
5. **Stringly-typed code**: using raw strings where constants or enums already exist
6. **Nested conditionals**: ternary chains or nested if/else 3+ levels deep — flatten with early returns or guard clauses
7. **Unnecessary comments**: comments explaining WHAT the code does (well-named identifiers already do that) — keep only non-obvious WHY
8. **Dead code, unused imports**: code paths no longer reachable, imports not referenced

### Efficiency

1. **Unnecessary work**: redundant computations, repeated file reads, duplicate API calls
2. **Missed concurrency**: independent operations run sequentially when they could run in parallel
3. **Hot-path bloat**: new blocking work added to startup or per-request hot paths
4. **Memory**: unbounded data structures, missing cleanup, event listener leaks
5. **Overly broad operations**: reading entire files when only a portion is needed

## Step 3: Fix issues

Fix each issue found. If a finding is a false positive or not worth addressing, note it and move on.

## Step 4: Verify behavior is preserved

After applying fixes, run the project's existing test suite, lint, and typecheck. Surface any failure clearly. Do not relax assertions or skip tests to make checks pass — that defeats the "preserves functionality" guarantee.

If no test suite, lint, or typecheck is configured, state that explicitly.

## Step 5: Summarize

Briefly summarize what was improved and fixed, including which checks were run and their results. If there were no findings, confirm the code didn't require any changes.
