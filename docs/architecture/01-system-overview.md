# System Overview

## Purpose

MergeMate is an AI-powered Telegram agent for code generation, debugging help, and explanations. The MVP optimizes for responsive chat interactions, context-aware conversations, and a Python package layout that can later be published to PyPI.

## Goals

- Acknowledge user prompts quickly in Telegram.
- Execute longer agent workflows in the background.
- Keep conversation context per chat.
- Support multiple programming languages through prompt assets and workflow policies.
- Package the system so users can install and run it locally or as a user-space service.

## Non-Goals For MVP

- Full sandboxed code execution.
- Distributed microservices.
- Multi-tenant SaaS administration.
- Embedded OAuth flows for source-control platforms.

## Core Quality Attributes

- Responsiveness: chat remains unblocked while jobs run.
- Extensibility: tools, workflows, and providers are replaceable.
- Operability: config can be local by default and overridden at startup.
- Packaging: repo structure supports installable distribution.
- Evolvability: internals can later be split into services if needed.

## MVP Runtime Shape

- Telegram receives prompt.
- Intake layer validates and creates a run record.
- Bot returns an immediate acknowledgement with the run ID and estimate.
- Planning agent drafts a plan that always includes design and test approach on the background path.
- Bot sends the drafted plan for confirmation as a follow-up message, or sends an auto-start notice once planning completes when confirmation is disabled.
- Background worker executes one of two delivery shapes:
	- multi-stage delivery for `generate_code`
	- direct single-agent execution for `debug_code` and `explain_code`
- Bot sends proactive progress updates and a final result back into the chat.

For a visual overview, see the diagram guide in `docs/diagrams/index.md`.