# Contributing to MergeMate

Thank you for your interest in MergeMate! This guide explains how to contribute code, tests, documentation, or architecture decisions.

## Quick Start

```bash
# Clone the repository
git clone https://github.com/djwinter29-oss/MergeMate
cd MergeMate

# Create a virtual environment and install in editable mode with dev extras
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Install pre-commit hooks (runs ruff, mypy, and formatting checks on commit)
make pre-commit-install

# Run the quality checks locally
make ci         # ruff lint, format check, mypy, and unit tests
make format     # auto-format with ruff
make test-all   # all tests, including integration and e2e
```

## Development Workflow

MergeMate uses a **branch → commit → push → PR → CI → merge** workflow.

1. **Create a feature branch** from `main`:
   ```bash
   git checkout main
   git pull
   git checkout -b feat/my-feature
   ```

2. **Make focused changes**. Follow the conventions below.

3. **Run quality checks locally** before committing:
   ```bash
   make ci
   ```

4. **Commit** using conventional commit messages (see below).

5. **Push and create a pull request**:
   ```bash
   git push -u origin feat/my-feature
   gh pr create --fill
   ```

6. **Wait for CI to go green**. The PR Checks workflow validates:
   - Ruff lint (no violations)
   - Ruff format (already formatted)
   - mypy type-checking on `src/`
   - Unit tests across Python 3.12 and 3.13
   - Integration tests
   - End-to-end tests (stub-based, no real Telegram required)

7. **Address review feedback** by pushing additional commits to the same branch.

8. **Squash-merge** (or rebase-merge) when approved and green.

9. **Clean up**:
   ```bash
   git checkout main
   git pull
   git branch -d feat/my-feature
   ```

## Branch Naming

Use a prefix that describes the kind of change:

| Prefix         | Purpose                                      |
|----------------|----------------------------------------------|
| `feat/`        | New feature or user-facing enhancement       |
| `fix/`         | Bug fix                                      |
| `chore/`       | Maintenance, tooling, CI, dependency bumps   |
| `docs/`        | Documentation-only changes                   |
| `refactor/`    | Code restructuring without behavior change   |
| `test/`        | Test additions or improvements               |
| `arch/`        | Architecture decision or design exploration  |

Examples: `feat/redis-queue-adapter`, `fix/run-status-timeout`, `chore/update-pydantic`.

## Commit Messages

Use **conventional commits** to keep the changelog clear:

```
<type>: <short description>

[optional body with details]
```

Types match the branch prefixes above. Keep the first line under 72 characters.

Examples:
```
feat: add Redis queue adapter for durable job transport

fix: handle empty conversation list in search-runs CLI

docs: add contributing guide and editorconfig

chore: update ruff to 0.9.0 and fix new violations
```

## Code Style

- **Line length**: 100 characters.
- **Formatter**: Ruff (run `make format` before committing).
- **Linter**: Ruff with the project's `pyproject.toml` configuration.
- **Types**: All public functions and methods should have type annotations.
- **Imports**: Use explicit imports; avoid `from module import *`.
- **Logging**: Use `structlog` instead of `print()` or the `logging` stdlib directly.
- **Configuration**: New settings belong in the YAML config model, not as inline constants.

## Testing Conventions

- **Location**: Tests live under `tests/`, mirroring the `src/mergemate/` package structure.
- **Markers**:
  - Unit tests: no marker (default). Mark with `@pytest.mark.unit` if needed for filtering.
  - Integration tests: `@pytest.mark.integration` — exercise real infrastructure (SQLite, filesystem).
  - E2E tests: `@pytest.mark.e2e` — stub-based end-to-end handler flows.
- **Running tests**:
  ```bash
  make test          # unit tests only
  make test-all      # all tests including integration and e2e
  make coverage      # unit tests with coverage report
  ```
- **Fixtures**: Put shared fixtures in `tests/conftest.py`. Use `conftest.py` files in subdirectories for scoped fixtures.
- **Async tests**: Use `pytest-asyncio`; mark test functions with `async def` and the framework handles it.

## Documentation

When your change affects any of the following, update the corresponding documentation:

| What changed                              | Where to document                                                                 |
|-------------------------------------------|-----------------------------------------------------------------------------------|
| Runtime behavior, workflow, or stages     | `docs/architecture/` and `docs/user-guide.md`                                     |
| Configuration schema or resolution        | `README.md` (Configuration Model section) and `docs/architecture/04-configuration-model.md` |
| CLI commands or options                   | `README.md` (Commands section) and `docs/user-guide.md`                           |
| Deployment mode or operations             | `docs/operations/`                                                                |
| Architectural decision                    | `docs/architecture/adr/` — create a new ADR for hard-to-reverse decisions         |
| Implementation notes                      | `docs/implementation/` for design rationale that isn't at ADR level               |

If you are not sure, add a brief note and a reviewer can help decide.

## Pre-commit Hooks

The repository has a `.pre-commit-config.yaml` that enforces:

- Ruff linting with auto-fix
- Ruff formatting
- mypy type-checking on `src/`
- Trailing whitespace removal
- End-of-file fixing
- YAML and TOML validation
- Large file detection (>500 KB)

Install with `make pre-commit-install` or manually:

```bash
pre-commit install
```

## Pull Request Guidelines

- **Keep PRs focused**: One logical change per PR. Split unrelated changes into separate PRs.
- **Write a clear description**: Explain what the change does and why. Reference relevant issues or ADRs.
- **Review your own diff first**: Use `git diff main...HEAD` to check for debug code, commented-out lines, or accidental changes.
- **Update docs**: If the PR changes user-facing behavior, include doc updates in the same PR.
- **CI must be green**: The PR will not be merged until all CI checks pass.

## Architecture Decisions

For any change that is hard to reverse later, affects multiple subsystems, or chooses between real alternatives, create an Architecture Decision Record (ADR).

1. Copy the format from an existing ADR in `docs/architecture/adr/`.
2. Give it the next sequential number.
3. Describe the context, the decision, and the consequences.
4. Link to it from `docs/architecture/adr/index.md`.
5. Reference the ADR number in the PR description.

Small implementation details and isolated bug fixes do not need an ADR.

## Code Of Conduct

Please be respectful and constructive in all interactions. This project follows the standard open-source principle of assuming good faith from all contributors.