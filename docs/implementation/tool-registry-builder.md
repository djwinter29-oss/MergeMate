# ToolRegistryBuilder Implementation

## Changes Made

### 1. `src/mergemate/infrastructure/tools/registry.py`

Added `ToolRegistryBuilder` class co-located with `ToolRegistry`:

- **Constructor** takes `settings: AppConfig` and `working_directory: Path` (keyword-only).
- `_add_permanent_tools()` is called automatically on construction, registering `code_formatter`, `package_installer`, and `syntax_checker` with their config-derived parameters.
- `with_git()`, `with_github_cli()`, `with_gitlab_cli()` each register the corresponding source-control tool and return `self` for fluent chaining. Each uses the resolved `working_directory` from the constructor parameter, not the raw config path.
- `build()` returns a `ToolRegistry(self._tools)`.
- All tool classes are imported inside the builder methods (lazy imports) rather than at module level, keeping the module's public surface clean.

Tool class imports used:
- `mergemate.infrastructure.tools.builtin.code_formatter.CodeFormatterTool`
- `mergemate.infrastructure.tools.builtin.package_installer.PackageInstallerTool`
- `mergemate.infrastructure.tools.builtin.syntax_checker.SyntaxCheckerTool`
- `mergemate.infrastructure.tools.builtin.source_control.GitRepositoryTool`
- `mergemate.infrastructure.tools.builtin.source_control.GitHubCliTool`
- `mergemate.infrastructure.tools.builtin.source_control.GitLabCliTool`

### 2. `src/mergemate/bootstrap.py`

Replaced the inline `ToolRegistry({...})` dict construction block (~45 lines of nested conditional spreads) with builder usage:

```python
builder = ToolRegistryBuilder(settings, working_directory=working_directory)
if settings.source_control.enable_git:
    builder.with_git()
if settings.source_control.enable_github:
    builder.with_github_cli()
if settings.source_control.enable_gitlab:
    builder.with_gitlab_cli()
tool_registry = builder.build()
```

Removed 6 unused import lines (the tool classes are now imported inside the builder).

## Verification

- `ToolRegistryBuilder` creates correct tool sets: permanent tools always present, conditional tools added only when requested.
- Fluent chaining works: `.with_git().with_github_cli()` registers both tools.
- All tools receive the same parameters as before (resolved `working_directory`, config-derived settings).
- No behavioural change — `ToolRegistry.__init__` signature unchanged, same `ToolRegistry` instances reach downstream consumers.
- 891 tests passed, 38 deselected (integration and e2e excluded), 0 failures.

## Files Changed

| File | Change |
|------|--------|
| `src/mergemate/infrastructure/tools/registry.py` | Added `ToolRegistryBuilder` class (+88 lines). Module docstring updated to "Tool registry and builder." |
| `src/mergemate/bootstrap.py` | Replaced inline ToolRegistry dict construction (~45 lines) with builder pattern. Removed 6 import lines. |
| `docs/implementation/tool-registry-builder.md` | This file. |