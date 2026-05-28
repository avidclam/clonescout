# ADR 001: Do Not Use GitHub Issues

## Status
Accepted

## Context
A git workflow with GitHub Issues was set up early in the project (`scripts/git-workflow.sh`).
Issues turned out to duplicate the files already kept in `issues/` and add no real value:
tasks are short-lived (one session), there is no long-term planning, and no PRs are created.
The development history is preserved through `issues/<slug>.md` files and squash-merge commits.

## Decision
Do not create GitHub Issues. Task context lives in `issues/<slug>.md`. The connection
between commits and tasks is established through branch naming and squash-commit messages.

## Consequences
- `scripts/git-workflow.sh` stays as the working tool but the following should be removed:
  the `gh issue create` and `gh issue close` calls, the `git config branch.*` and correcponding
  `git config --unset ` calls that store issue numbers in the git config and clean them up later.
- The issues opened during the initial workflow setup remain open on GitHub
  and are not worth closing — they are simply ignored going forward.