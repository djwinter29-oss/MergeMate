# ToolRegistry Construction — Builder Pattern

## Intent

Eliminate the repetitive `**({...} if condition else {})` pattern used to conditionally register git, GitHub CLI, and GitLab CLI tools in `bootstrap.py`. Replace it with a dedicated builder that encapsulates the conditional logic, reduces noise in the composition root, and makes the tool set explicit at a glance.

## Problem

`bootstrap.py` lines 184–228 construct `ToolRegistry` with an inline dict literal that repeats the same conditional-spread idiom three times:

```python
tool_registry = ToolRegistry(
    {
        "code_formatter": CodeFormatterTool(),
        "package_installer": PackageInstallerTool(...),
        "syntax_checker": SyntaxCheckerTool(),
        **({"git_repository": GitRepositoryTool(...)} if settings.source_control.enable_git else {}),
        **({"github_cli": GitHubCliTool(...)}     if settings.source_control.enable_github else {}),
        **({"gitlab_cli": GitLabCliTool(...)}     if settings.source_control.enable_gitlab else {}),
    }
)
```

**Issues:**

1. **Visual noise** — the `**({...} if X else {})` spread pattern obscures the intent. A reader must parse three levels of nesting (dict literal → spread → ternary → inner dict) to see which tools are always included versus conditionally included.
2. **Error prone** — a missing `**()` wrapper or a misplaced comma silently changes behaviour.
3. **Hard to extend** — adding a new conditional tool requires copying the same pattern, making the dict longer and harder to scan.
4. **No discoverability** — a new team member scanning `bootstrap.py` cannot tell at a glance which tools are registered; they must read through the full conditional block.

## Design

### Approach: ToolRegistryBuilder

Introduce a builder class co-located with `ToolRegistry` in `src/mergemate/infrastructure/tools/registry.py`. The builder provides one method per tool kind, each accepting only the parameters it needs. Always-registered tools are added by the builder automatically; conditional tools are called explicitly.

```python
class ToolRegistryBuilder:
    """Fluent builder for ToolRegistry construction.

    Always-registered tools are added automatically on construction.
    Conditional tools (source-control backends) are added via explicit methods
    that the caller invokes only when the corresponding feature flag is enabled.
    """

    def __init__(self, settings: AppConfig) -> None:
        self._settings = settings
        self._tools: dict[str, object] = {}
        self._add_permanent_tools()

    # ── internal ──────────────────────────────────────────────────────────

    def _add_permanent_tools(self) -> None:
        """Tools that are *always* registered regardless of configuration."""
        s = self._settings
        self._tools["code_formatter"] = CodeFormatterTool()
        self._tools["package_installer"] = PackageInstallerTool(
            allow_package_install=s.tools.allow_package_install,
            allowed_packages=s.tools.allowed_packages,
            pip_executable=s.tools.pip_executable,
            timeout_seconds=s.runtime.default_request_timeout_seconds,
        )
        self._tools["syntax_checker"] = SyntaxCheckerTool()

    # ── source-control backends (conditional) ─────────────────────────────

    def with_git(self) -> ToolRegistryBuilder:
        self._tools["git_repository"] = GitRepositoryTool(
            executable=self._settings.source_control.git_executable,
            working_directory=self._settings.source_control.working_directory,
            timeout_seconds=self._settings.runtime.default_request_timeout_seconds,
        )
        # NOTE: working_directory is the *config-level path*, not the resolved
        # absolute path. bootstrap.py currently passes `working_directory` (the
        # resolved Path). If the builder needs the resolved path, it must be
        # injected separately or the builder must be created after resolution.
        # See "Open Questions" below.
        return self  # allow chaining

    def with_github_cli(self) -> ToolRegistryBuilder:
        self._tools["github_cli"] = GitHubCliTool(
            executable=self._settings.source_control.github_executable,
            working_directory=self._settings.source_control.working_directory,
            timeout_seconds=self._settings.runtime.default_request_timeout_seconds,
        )
        return self

    def with_gitlab_cli(self) -> ToolRegistryBuilder:
        self._tools["gitlab_cli"] = GitLabCliTool(
            executable=self._settings.source_control.gitlab_executable,
            working_directory=self._settings.source_control.working_directory,
            timeout_seconds=self._settings.runtime.default_request_timeout_seconds,
        )
        return self

    # ── finalise ──────────────────────────────────────────────────────────

    def build(self) -> ToolRegistry:
        return ToolRegistry(self._tools)
```

### Usage in `bootstrap.py`

The inline dict disappears. The calling code becomes:

```python
builder = ToolRegistryBuilder(settings)
if settings.source_control.enable_git:
    builder.with_git()
if settings.source_control.enable_github:
    builder.with_github_cli()
if settings.source_control.enable_gitlab:
    builder.with_gitlab_cli()
tool_registry = builder.build()
```

**What changed at a glance:**

- Three `if` blocks instead of three nested `**({...} if ... else {})` spreads.
- Each block is a simple method call on the builder — no dict literals, no ternaries.
- The builder constructor registers the three permanent tools automatically.

### Alternative considered: Pure function helper

A standalone `_build_tool_dict(settings: AppConfig) -> dict[str, object]` was considered and rejected because:

- It still returns a raw dict that must be passed to `ToolRegistry(...)` — the naming doesn't signal a construction boundary.
- Adding a new tool later means editing a function body that mixes permanent and conditional logic in one large dict literal. The builder's method-per-tool pattern scales better.

### Alternative considered: `add_tool(name, tool)` on ToolRegistry itself

Mutating a built registry at bootstrap time is possible but conflates the registry's runtime contract ("I hold tools") with its construction contract ("how are tools assembled"). Keeping the builder separate preserves single responsibility: `ToolRegistry` is a frozen collection after build.

## What does not change

| Aspect | Status |
|--------|--------|
| `ToolRegistry.__init__` signature | Unchanged — still takes `dict[str, object]` |
| `ToolService` / `AgentOrchestrator` | Unchanged — they receive the same `ToolRegistry` instance |
| Tool behaviour, metadata, invocation | Unchanged — all tools remain identical instances |
| Settings schema | Unchanged — `SourceControlConfig` fields are read, not modified |

## Files to change

### `src/mergemate/infrastructure/tools/registry.py`

- Add `ToolRegistryBuilder` class (the full implementation above).
- No changes to the existing `ToolRegistry` class itself.
- Update module docstring if desired.

### `src/mergemate/bootstrap.py`

- Remove lines 184–228 (the inline `ToolRegistry(` dict construction).
- Replace with the 7-line builder pattern shown above.
- Remove imports that become unused? The tool imports (`CodeFormatterTool`, `PackageInstallerTool`, `SyntaxCheckerTool`, `GitRepositoryTool`, `GitHubCliTool`, `GitLabCliTool`) are consumed inside the builder now. However, `bootstrap.py` may not need to import them at all — the builder imports them internally. If no other code in `bootstrap.py` references these classes, the imports can be removed.

## Open Questions (resolved during implementation)

1. **Working directory resolution** — The builder currently accesses `self._settings.source_control.working_directory`, which is the *config-level relative string* (e.g. `"."`). In the current `bootstrap.py`, the resolved absolute `working_directory` (from `settings.resolve_working_directory(resolved_config_path)`) is passed to the tool constructors. The builder needs the resolved path, not the raw config string.  
   → **Resolution**: Accept the resolved `working_directory: Path` as a constructor parameter alongside `settings`, or pass it to `.with_*()` methods. The simpler approach is adding a `working_directory: Path = Path(".")` parameter to `ToolRegistryBuilder.__init__`.

2. **Builder location** — Should the builder live in `registry.py` (co-located with its product) or in a new `tool_builder.py` module?  
   → **Recommendation**: Co-locate in `registry.py`. The builder is tightly coupled to `ToolRegistry` construction and unlikely to be reused elsewhere. A new module is justified only when the builder grows beyond ~100 lines or acquires its own dependencies.

## Verification

- Existing tests that construct `ToolRegistry` directly (unit tests with `ToolRegistryStub`) are unaffected — they never go through the builder.
- `bootstrap()` integration tests (if any) must still produce a `ToolRegistry` with the same tool names.
- No behavioural change is expected: the same tools with the same parameters are registered under the same names.