# Packaging And Distribution

## Goal

MergeMate should be structured so it can later be released to PyPI and installed by other users with minimal restructuring.

## Packaging Decisions

- use `pyproject.toml`
- use `src/` layout
- expose a `mergemate` CLI entrypoint
- keep optional features behind dependency groups later

## User Installation Model

Current local-development usage:

```bash
pip install -e .[dev]
mergemate validate-config
mergemate run-bot
```

Planned installed-package usage:

```bash
pip install mergemate
mergemate run-bot --config ~/.config/mergemate/config.yaml
```

## Service-Oriented Operation

The CLI design allows the same package to run:

- as a foreground local process
- as a containerized process
- as a user-space service managed by systemd or another supervisor

## Release Roadmap

1. Stabilize config and CLI surface.
2. Make package versioning fully release-driven from the package source and build metadata.
3. Add integration tests around config resolution and startup behavior.
4. Publish pre-release builds.
5. Publish stable release to PyPI.