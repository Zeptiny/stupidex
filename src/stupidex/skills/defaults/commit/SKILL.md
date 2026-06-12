---
name: commit
description: 'Create a git commit with a clear, value-communicating message. Use when the user says "commit", "commit this", "save my changes", "create a commit", or wants to commit staged or unstaged work.'
---

# Git Commit

Create a single, well-crafted git commit from the current working tree changes.

## Workflow

### Step 1: Gather context

Run this command to gather all context:

```bash
printf '=== STATUS ===\n'; git status; printf '\n=== DIFF ===\n'; git diff HEAD; printf '\n=== BRANCH ===\n'; git branch --show-current; printf '\n=== LOG ===\n'; git log --oneline -10; printf '\n=== DEFAULT_BRANCH ===\n'; git rev-parse --abbrev-ref origin/HEAD 2>/dev/null || echo '__DEFAULT_BRANCH_UNRESOLVED__'
```

If git status shows a clean working tree (no staged, modified, or untracked files), report that there is nothing to commit and stop.

If the current branch is empty (detached HEAD), explain that a branch is required. Ask whether to create a feature branch now.

### Step 2: Determine commit message convention

Follow this priority order:

1. **Repo conventions** - If project instructions specify commit message conventions, follow those.
2. **Recent commit history** - Examine the 10 most recent commits. If a clear pattern emerges (e.g., conventional commits, ticket prefixes), match that pattern.
3. **Default: conventional commits** - Use conventional commit format: `type(scope): description` where type is one of `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `perf`, `ci`, `style`, `build`.

Choose the type that most precisely describes the change. Where `fix:` and `feat:` both seem to fit, default to `fix:`. Reserve `feat:` for capabilities the user could not previously accomplish.

### Step 3: Consider logical commits

Before staging everything together, scan the changed files for naturally distinct concerns. If modified files clearly group into separate logical changes, create separate commits for each group.

Keep this lightweight:
- Group at the **file level only** - do not try to split hunks within a file
- If the separation is obvious (different features, unrelated fixes), split. If it's ambiguous, one commit is fine.
- Two or three logical commits is the sweet spot

### Step 4: Stage and commit

If on the default branch (`main`, `master`), warn the user and ask whether to continue or create a feature branch first.

Write the commit message:
- **Subject line**: Concise, imperative mood, focused on *why* not *what*
- **Body** (when needed): Explain motivation, trade-offs, or anything a future reader would need

Stage and commit:
```bash
git add file1 file2 file3 && git commit -m "$(cat <<'EOF'
type(scope): subject line here

Optional body explaining why this change was made,
not just what changed.
EOF
)"
```

### Step 5: Confirm

Run `git status` after the commit to verify success. Report the commit hash(es) and subject line(s).
