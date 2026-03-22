# ADR-002: Local YAML Config With CLI Override

## Status

Accepted

## Decision

Use YAML as the user-facing config format. Keep a default local config in `./config/config.yaml` and allow an explicit path to be passed at startup.

## Rationale

- supports local development naturally
- supports repo-scoped defaults
- supports user-space service operation without restructuring the project
- easier to edit and document than JSON