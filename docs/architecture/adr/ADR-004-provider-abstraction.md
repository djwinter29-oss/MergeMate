# ADR-004: Endpoint-Based Provider Abstraction

## Status

Accepted

## Decision

Provider integrations are hidden behind an LLM client abstraction. Providers are configured by endpoint URL and request metadata so one workflow can use multiple OpenAI-compatible providers without changing workflow code.

## Rationale

- reduces lock-in
- keeps workflows independent from SDK details
- makes testing easier
- supports multiple provider aliases for different workflow roles
- supports custom gateway URLs and Azure-style endpoint variants

## In Plain Terms

The workflow layer should ask for planning, design, coding, testing, or review output without caring whether that output comes from OpenAI, Azure-hosted deployments, Kimi, DeepSeek, or another compatible endpoint.

## Consequences

- workflow code stays vendor-agnostic
- provider-specific auth headers and URLs stay in configuration and adapter code
- the current adapter assumes an OpenAI-compatible chat-completions shape
- non-compatible providers may still need additional adapters later