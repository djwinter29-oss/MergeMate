---
applyTo: "src/mergemate/config/**"
description: "Use when editing MergeMate configuration models, defaults, loading, and runtime path resolution."
---

# MergeMate Config Instructions

- Keep YAML as the user-facing configuration model and preserve the config resolution order documented in the architecture docs.
- Maintain the boundary of this package area: defaults, schema models, config loading, path resolution, and logging configuration belong here.
- Preserve endpoint-based provider configuration. Avoid adding vendor-specific branching in config loading unless the decision is documented in the ADRs.
- Keep secrets represented as environment-variable names in config, with runtime resolution happening from those names rather than checked-in secret values.
- Relative runtime paths should continue resolving from `storage.workspace_root`, including database, docs, and working-directory paths.
- Prefer backward-compatible schema evolution where possible. When adding settings, give them explicit defaults or validation behavior that matches the current local-first model.
- Update `src/mergemate/config/defaults.yaml` and the relevant tests together when schema or default behavior changes.
- Reference `docs/architecture/04-configuration-model.md`, `docs/architecture/08-security-and-sandboxing.md`, and the ADR index for the governing decisions instead of duplicating those explanations across code.