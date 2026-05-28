# Repository Maintenance

## Purpose

This document captures the light-weight repository hygiene workflow that keeps local branches and
remote tracking refs from accumulating over time.

## Available Make Targets

The repository includes read-only branch maintenance helpers in the `Makefile`:

- `make branches-list` — show all local branches and any stale tracking refs
- `make branches-merged` — show local and remote branches already merged into `main`
- `make branches-clean` — print the exact cleanup commands that would delete merged local
  branches and prune stale remote tracking refs

These targets are intentionally safe to run during routine maintenance because they only inspect the
branch state or print suggested cleanup commands.

## Recommended Routine

1. Run `make branches-merged` after a merge-heavy week or before starting a new cleanup pass.
2. Use `make branches-list` to spot stale local branches and tracking refs that are no longer useful.
3. Run `make branches-clean` and review the printed commands before executing anything destructive.
4. Use `git remote prune origin` when you want to remove stale remote-tracking refs locally.

## Notes

- `branches-clean` is informative by design; it does not delete branches automatically.
- If you are cleaning up a feature branch after merge, delete it manually only after confirming it
  is fully merged everywhere you need it.