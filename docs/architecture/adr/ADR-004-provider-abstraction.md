# ADR-004: Provider Abstraction

## Status

Accepted

## Decision

Provider integrations are hidden behind an LLM client abstraction. The first concrete implementation target is OpenAI.

## Rationale

- reduces lock-in
- keeps workflows independent from SDK details
- makes testing easier