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

## In Plain Terms

The app should work out of the box with a repo-local config file, but operators can point it at another config file when running it as a personal service or from another directory.

## Consequences

- good default for local development
- easy to document and review in source control
- supports per-user deployment without changing code
- secrets still stay in environment variables rather than the YAML file