# Git Workflow

Deliberately simple — customize branch naming, commit conventions, PR rules, reviewers, and CI requirements later as the team sees fit. This is the default until then.

## Starting work

1. Ensure your local repository is up to date.
2. Pull the latest default branch (`main`).
3. Create a new feature/fix branch.
4. Use a meaningful branch name:
   ```
   feature/<short-description>
   fix/<short-description>
   ```

## During work

- Make focused commits — one logical change per commit.
- Do not mix unrelated changes in a single commit.
- Keep commit messages understandable on their own, without needing to open the diff.
- Run relevant tests before committing (see `testing.md` for which category applies to your change).
- Review your own diff before committing — `git diff` is part of the workflow, not optional.

## Before pushing

- Confirm you're on the correct branch (`git status`).
- Run relevant tests/checks.
- Inspect `git diff` and `git status` one more time.
- Commit with a meaningful message.

## Push

Push the feature branch to the remote repository.

## Integration

Simple PR-based workflow:

```
main
  ↑
Pull Request
  ↑
feature branch
```

A PR should include:

- Summary of the change
- Files changed
- Tests performed
- Screenshots if UI-affecting
- Known limitations
- Related issue/task, if applicable

No specific branch-protection or CI policy is assumed yet — add one when the team decides it's needed.

## AI coding-agent rule

AI agents must never work directly on `main`. Always:

```
update main → create branch → implement → test → review diff → commit → push branch → PR
```

This mirrors the AI Coding Agent Operating Procedure in `project-context.md` — that file's steps 10–11 ("commit the work using the project's Git workflow," "push the branch") point here for the exact mechanics.
