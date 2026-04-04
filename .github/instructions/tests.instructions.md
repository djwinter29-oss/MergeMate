---
applyTo: "tests/**"
description: "Use when editing MergeMate tests under tests/. Covers pytest structure, scope, and behavior-oriented validation."
---

# MergeMate Test Instructions

- Follow the existing split across `tests/unit`, `tests/integration`, and `tests/e2e`.
- Mirror the package layout under `src/mergemate` where practical.
- Prefer focused pytest tests with local stubs, fixtures, and temporary paths over broad end-to-end setup for unit behavior.
- Keep tests behavior-oriented. Assert observable run states, persisted values, Telegram replies, and workflow transitions instead of implementation trivia.
- When changing config behavior, cover path resolution, workspace-root scoping, and explicit-config override behavior with `tmp_path` tests.
- When changing Telegram handlers or presenters, assert user-visible messages and confirm the intake path stays defensive around missing chat or message objects.
- Add or update the smallest relevant test first, then expand coverage only if the change crosses module boundaries.
- Use the repo validation commands from `.github/copilot-instructions.md`: `pytest` and `ruff check src tests`.