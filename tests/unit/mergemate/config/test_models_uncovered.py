"""Tests for config/models.py uncovered branch paths.

Covers:
1.  resolve_agent_provider_names: agent has provider_names [line 340]
2.  resolve_agent_name_for_workflow: preferred_agent matches [lines 358-360]
3.  resolve_agent_name_for_workflow: fallback agent scan [line 364]
"""

from mergemate.config.models import AppConfig


def _build_config() -> AppConfig:
    return AppConfig.model_validate(
        {
            "default_agent": "coder",
            "default_provider": "primary",
            "providers": {
                "primary": {"api_key_env": "PRIMARY_KEY", "model": "gpt-5.4"},
                "secondary": {"api_key_env": "SECONDARY_KEY", "model": "gpt-4.1"},
            },
            "telegram": {"bot_token_env": "TELEGRAM_TOKEN"},
            "storage": {"workspace_root": "workspace", "database_path": ".state/runtime.db"},
            "source_control": {"working_directory": "repo"},
            "runtime": {"max_concurrent_runs": 2},
            "agents": {
                "planner": {"workflow": "planning"},
                "architect": {"workflow": "design"},
                "coder": {"workflow": "generate_code", "provider_names": ["secondary"]},
                "tester": {"workflow": "testing"},
                "reviewer": {"workflow": "review"},
                "explainer": {"workflow": "explain_code"},
            },
        }
    )


class TestResolveAgentProviderNames:
    def test_returns_agent_provider_names_when_present(self) -> None:
        """Line 340: agent has provider_names -> returns them."""
        config = _build_config()
        result = config.resolve_agent_provider_names("coder")
        assert result == ["secondary"]

    def test_returns_default_when_agent_missing(self) -> None:
        """Line 339: agent not found or no provider_names -> returns [default_provider]."""
        config = _build_config()
        result = config.resolve_agent_provider_names("nonexistent")
        assert result == ["primary"]

    def test_returns_default_when_agent_has_no_provider_names(self) -> None:
        """Line 339: agent exists but provider_names is empty."""
        config = _build_config()
        # tester has no provider_names, falls through to default
        result = config.resolve_agent_provider_names("tester")
        assert result == ["primary"]


class TestResolveAgentNameForWorkflow:
    def test_preferred_agent_matches_returns_it(self) -> None:
        """Lines 358-360: preferred_agent exists and its workflow matches."""
        config = _build_config()
        result = config.resolve_agent_name_for_workflow(
            "generate_code",
            preferred_agent_name="coder",
        )
        assert result == "coder"

    def test_preferred_agent_does_not_match_returns_first_matching(self) -> None:
        """Line 364: preferred_agent doesn't match workflow -> fallback scan."""
        config = _build_config()
        # 'tester' has workflow 'testing', not 'generate_code'
        result = config.resolve_agent_name_for_workflow(
            "generate_code",
            preferred_agent_name="tester",
        )
        # Should fall through to the agent scan and find 'coder'
        assert result == "coder"

    def test_no_preferred_uses_first_matching_agent(self) -> None:
        """Line 364: no preferred_agent -> scan agents for workflow match."""
        config = _build_config()
        result = config.resolve_agent_name_for_workflow("review")
        assert result == "reviewer"
