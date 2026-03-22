# Architecture Decision Records

This directory records the architectural decisions that shape MergeMate.

## Current ADRs

| ADR | Decision | Why It Matters |
| --- | --- | --- |
| [ADR-001](./ADR-001-python-modular-monolith.md) | Python modular monolith | keeps the MVP simple to build, package, and operate |
| [ADR-002](./ADR-002-local-yaml-config.md) | local YAML config with CLI override | supports both repo-local defaults and user-space deployment |
| [ADR-003](./ADR-003-non-blocking-telegram-jobs.md) | non-blocking Telegram jobs | keeps chat responsive while long-running work happens in the background |
| [ADR-004](./ADR-004-provider-abstraction.md) | endpoint-based provider abstraction | keeps workflow code independent from provider-specific configuration |
| [ADR-005](./ADR-005-approval-gated-multi-stage-workflow.md) | approval-gated multi-stage workflow | requires planning and confirmation before expensive execution begins |
| [ADR-006](./ADR-006-role-based-agent-model-assignment.md) | role-based agent model assignment | lets planning, design, coding, testing, and review use different model setups |
| [ADR-007](./ADR-007-review-driven-replanning-loop.md) | bounded review-driven replanning | allows serious review findings to trigger replanning without unbounded loops |
| [ADR-008](./ADR-008-scm-integration-through-local-clis.md) | SCM integration through local authenticated CLIs | reuses existing `git`, `gh`, and `glab` login state instead of embedding OAuth |
| [ADR-009](./ADR-009-config-driven-workflow-dispatch.md) | config-driven workflow dispatch | keeps workflow selection and execution shape aligned with the real runtime |

## How To Read These

- start with `ADR-001` through `ADR-004` for the original MVP foundation
- read `ADR-005` through `ADR-009` for the later workflow and integration decisions
- when a new requirement changes structure, deployment, provider strategy, or workflow control, it should usually become a new ADR rather than being buried only in code changes

## When To Create A New ADR

Create a new ADR when a decision is hard to reverse later, affects multiple parts of the system, or chooses one architectural approach over another real alternative. Do not create an ADR for routine implementation details, small refactors, or isolated bug fixes.

## Superseding Older ADRs

If a later decision replaces an older one, do not silently rewrite the older ADR. Instead:

- keep the old ADR for history
- change its status to `Superseded` if appropriate
- add a short note pointing to the newer ADR
- have the newer ADR say which earlier ADR it supersedes

This keeps the reasoning trail intact and makes architectural drift easier to understand.