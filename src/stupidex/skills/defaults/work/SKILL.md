---
name: work
description: 'Execute work efficiently while maintaining quality and finishing features. Use when the user says "implement this", "build it", "start working", "execute the plan", or provides a task description or plan document to execute.'
---

# Work Execution Command

Execute work efficiently while maintaining quality and finishing features.

This command takes a work document (plan or specification) or a bare prompt describing the work, and executes it systematically. The focus is on **shipping complete features** by understanding requirements quickly, following existing patterns, and maintaining quality throughout.

## Execution Workflow

### Phase 0: Input Triage

**Plan document** (input is a file path to an existing plan) → skip to Phase 1.

**Bare prompt** (input is a description of work):

1. **Scan the work area**
   - Identify files likely to change based on the prompt
   - Find existing test files for those areas
   - Note local patterns and conventions

2. **Assess complexity and route**

   | Complexity | Signals | Action |
   |-----------|---------|--------|
   | **Trivial** | 1-2 files, no behavioral change | Implement directly — no task list |
   | **Small / Medium** | Clear scope, under ~10 files | Build a task list, then execute |
   | **Large** | Cross-cutting, 10+ files | Consider `brainstorm` or `plan` first |

---

### Phase 1: Quick Start

1. **Read Plan and Clarify** _(skip if bare prompt)_

   - Read the work document completely
   - Treat the plan as a decision artifact, not an execution script
   - Use `Implementation Units`, `Requirements`, `Files`, `Test Scenarios`, and `Verification` as primary source material
   - Check for `Execution note` on each unit — these carry execution posture signals (test-first, etc.)
   - Check for `Deferred to Implementation` sections — questions left for execution time
   - Check for `Scope Boundaries` — explicit non-goals
   - If anything is unclear, ask clarifying questions now
   - **Do not edit the plan body during execution** — progress lives in git commits and the task tracker

2. **Setup Environment**

   Check the current branch:
   ```bash
   current_branch=$(git branch --show-current)
   default_branch=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/origin/@@')
   if [ -z "$default_branch" ]; then
     default_branch=$(git rev-parse --verify origin/main >/dev/null 2>&1 && echo "main" || echo "master")
   fi
   ```

   **If on the default branch**, create a feature branch:
   ```bash
   git checkout -b feature-branch-name
   ```

3. **Create Task List**

   - Break the plan into actionable tasks
   - Derive tasks from implementation units, dependencies, files, and verification criteria
   - Preserve U-IDs as task prefixes (e.g., "U3: Add parser coverage")
   - Include dependencies between tasks
   - Keep tasks specific and completable

### Phase 2: Execute

1. **Task Execution Loop**

   ```
   while (tasks remain):
   - Mark task as in-progress
   - Read any referenced files from the plan
   - Look for similar patterns in codebase
   - Find existing test files for implementation files being changed
   - Implement following existing conventions
   - Add, update, or remove tests to match implementation changes
   - Run tests after changes
   - Mark task as completed
   - Evaluate for incremental commit
   ```

2. **Incremental Commits**

   Commit after logical units complete:
   - Logical unit complete (model, service, component)
   - Tests pass + meaningful progress
   - About to switch contexts (backend → frontend)

   ```bash
   # 1. Verify tests pass
   # 2. Stage only files related to this logical unit
   git add <files>
   # 3. Commit with conventional message
   git commit -m "feat(scope): description of this unit"
   ```

3. **Follow Existing Patterns**

   - The plan should reference similar code — read those files first
   - Match naming conventions exactly
   - Reuse existing components where possible
   - When in doubt, grep for similar implementations

4. **Test Continuously**

   - Run relevant tests after each significant change
   - Don't wait until the end to test
   - Fix failures immediately
   - Add new tests for new behavior, update tests for changed behavior

5. **Track Progress**

   - Keep the task list updated as you complete tasks
   - Note any blockers or unexpected discoveries
   - Create new tasks if scope expands

### Phase 3: Quality Check

When all tasks are complete:
- Review all changes
- Run linting and typecheck if available
- Verify all tasks are marked complete
- Check that scope boundaries were respected

### Phase 4: Finishing Work

- Create final commit if needed
- Present summary of what was accomplished
- Suggest next steps (tests, PR, deployment)

## Key Principles

### Start Fast, Execute Faster
- Get clarification once at the start, then execute
- Don't wait for perfect understanding — ask questions and move
- The goal is to **finish the feature**, not create perfect process

### The Plan is Your Guide
- Work documents should reference similar code and patterns
- Load those references and follow them
- Don't reinvent — match what exists

### Test As You Go
- Run tests after each change, not at the end
- Fix failures immediately
- Continuous testing prevents big surprises

### Quality is Built In
- Follow existing patterns
- Write tests for new code
- Run linting before pushing

### Ship Complete Features
- Mark all tasks completed before moving on
- Don't leave features 80% done
- A finished feature that ships beats a perfect feature that doesn't

## Common Pitfalls to Avoid

- **Analysis paralysis** - Don't overthink, read the plan and execute
- **Skipping clarifying questions** - Ask now, not after building wrong thing
- **Ignoring plan references** - The plan has links for a reason
- **Testing at the end** - Test continuously or suffer later
- **Forgetting to track progress** - Update task status as you go
- **80% done syndrome** - Finish the feature, don't move on early
