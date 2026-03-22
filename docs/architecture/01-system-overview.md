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
- Multiple provider implementations on day one.

## Core Quality Attributes

- Responsiveness: chat remains unblocked while jobs run.
- Extensibility: tools, workflows, and providers are replaceable.
- Operability: config can be local by default and overridden at startup.
- Packaging: repo structure supports installable distribution.
- Evolvability: internals can later be split into services if needed.

## MVP Runtime Shape

- Telegram receives prompt.
- Intake layer validates and creates a run record.
- Bot sends immediate acknowledgement with status and rough estimate.
- Background worker executes the selected workflow.
- Bot sends progress or final result back into the chat.