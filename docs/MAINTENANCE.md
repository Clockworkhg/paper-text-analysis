# Maintenance

This document records the low-friction rules for keeping the repository tidy.

## What Belongs In Git

Keep source code, tests, examples, documentation, packaging files, and small
curated fixtures in git.

Do not commit generated runtime outputs, local project workspaces, caches,
virtual environments, build products, OCR logs, or private research material.
Those are ignored by `.gitignore`.

## Common Checks

Run the full test suite before committing functional or structural changes:

```powershell
python research_tool.py test
```

For documentation-only changes, a quick smoke check is usually enough:

```powershell
python research_tool.py docs
```

## Branch And Commit Practice

- Use `codex/<short-description>` for cleanup and feature branches.
- Keep each cleanup phase independently testable.
- Stage explicit files when the worktree contains unrelated changes.
- Prefer small compatibility-preserving refactors over large moves.

## Runtime Outputs

Use `projects/`, `output/`, `outputs/`, `runtime/`, or `workspace/` for local
runs. If a run needs to become a reproducible example, copy only the smallest
necessary fixture into `examples/` and document how it was generated.
