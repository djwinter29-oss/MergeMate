---
applyTo: "src/mergemate/interfaces/**"
description: "Use when editing MergeMate delivery adapters, especially Telegram handlers, presenters, and progress notifications."
---

# MergeMate Interface Instructions

- Keep `interfaces` focused on delivery concerns only: inbound request normalization, outbound messaging, and presentation formatting.
- Do not move orchestration, workflow decisions, persistence rules, or provider logic into Telegram handlers. Those belong in `application`, `domain`, or `infrastructure`.
- Preserve the responsive Telegram intake path described in the architecture docs. Long-running work must remain in background execution, with handlers triggering dispatch and progress watching rather than doing heavy work inline.
- Keep user-facing message text and formatting in presenter or status-formatting helpers when practical, rather than embedding long response strings in handlers.
- Guard Telegram adapter code against missing `message`, `chat`, or `user` objects and fail gracefully with no side effects when update data is incomplete.
- Prefer small helper functions for parsing command arguments, request construction, and terminal notifications when that keeps handlers readable.
- When behavior changes affect chat flows or command semantics, update or add focused tests under `tests/unit/mergemate/interfaces/telegram` and broader flow coverage only if the interaction contract changes.
- Reference `docs/architecture/01-system-overview.md`, `docs/architecture/02-runtime-architecture.md`, and `docs/architecture/09-operations-and-observability.md` for expected runtime behavior instead of restating that rationale in code comments.