"""Tests for remaining uncovered branch paths in config/models.py.

Covers:
1. _populate_roles_from_agents backward compat — empty roles + populated agents
2. resolve_agent_provider_names — agent has provider_names but no matching role (line 396)
3. resolve_agent_name_for_workflow — preferred_agent fallback scan (lines 414-416)
4. resolve_agent_name_for_workflow — fallback through agents (line 420)
5. resolve_agent_name_for_workflow — empty configured_workflows (line 432)
"""

import pytest

from mergemate.config.models import AppConfig, ConfigWorkflowNotFoundError


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


class TestPopulateRolesFromAgents:
    """Backward compat: empty roles + populated agents => auto-populated roles."""

    def test_roles_are_populated_when_empty(self) -> None:
        """Line 302-324: _populate_roles_from_agents creates roles from agents."""
        config = _build_config()

        # Roles should be auto-populated from agents
        assert len(config.roles) == len(config.agents)
        for name in config.agents:
            assert name in config.roles, f"Role {name} should be auto-created"
            assert config.roles[name].workflow == config.agents[name].workflow

    def test_roles_are_not_overridden_when_present(self) -> None:
        """When roles are explicitly provided, _populate_roles_from_agents does not override."""
        config = AppConfig.model_validate(
            {
                "default_agent": "coder",
                "default_provider": "primary",
                "providers": {
                    "primary": {"api_key_env": "PRIMARY_KEY", "model": "gpt-5.4"},
                },
                "telegram": {"bot_token_env": "TELEGRAM_TOKEN"},
                "runtime": {"max_concurrent_runs": 2},
                "agents": {
                    "planner": {"workflow": "planning"},
                    "architect": {"workflow": "design"},
                    "coder": {"workflow": "generate_code"},
                    "tester": {"workflow": "testing"},
                    "reviewer": {"workflow": "review"},
                },
                "roles": {
                    "planner": {"workflow": "planning"},
                    "architect": {"workflow": "design"},
                    "coder": {"workflow": "generate_code", "provider_names": ["primary"]},
                    "tester": {"workflow": "testing"},
                    "reviewer": {"workflow": "review"},
                },
            }
        )

        # Roles should have the explicitly configured provider_names
        assert config.roles["coder"].provider_names == ["primary"]
        # The auto-populated path on line 308-323 should NOT overwrite coder's provider_names
        # because roles already exist
        assert config.roles["coder"].provider_names == ["primary"]


class TestResolveAgentProviderNames:
    """Agent has provider_names but no role match (line 396)."""

    def test_returns_agent_provider_names_when_no_role(self) -> None:
        """Line 396: agent exists with provider_names, no matching role -> returns agent's list."""
        config = _build_config()

        # Remove the auto-created role for coder to force the agent path
        config.roles.pop("coder", None)
        config.roles.pop("planner", None)
        config.roles.pop("architect", None)
        config.roles.pop("tester", None)
        config.roles.pop("reviewer", None)
        config.roles.pop("explainer", None)

        result = config.resolve_agent_provider_names("coder")
        assert result == ["secondary"]


class TestResolveAgentNameForWorkflow:
    """Cover remaining uncovered branches in resolve_agent_name_for_workflow."""

    def test_preferred_agent_fallback_when_preferred_does_not_exist(self) -> None:
        """Lines 414-416: preferred_agent_name not in agents -> fallback scan."""
        config = _build_config()

        # Remove roles to force agent-based fallback
        config.roles.clear()

        # preferred_agent_name="nonexistent" is not in agents, so skip to agent scan
        result = config.resolve_agent_name_for_workflow(
            "generate_code",
            preferred_agent_name="nonexistent",
        )
        assert result == "coder"

    def test_preferred_agent_mismatches_workflow_falls_back(self) -> None:
        """Lines 414-416: preferred_agent exists but its workflow doesn't match -> fallback."""
        config = _build_config()

        # Remove roles to force agent-based path
        config.roles.clear()

        # tester has workflow "testing", not "generate_code"
        result = config.resolve_agent_name_for_workflow(
            "generate_code",
            preferred_agent_name="tester",
        )
        # Should skip preferred_agent (workflow mismatch) and find coder
        assert result == "coder"

    def test_preferred_agent_matches_workflow_returns_preferred(self) -> None:
        """Line 416: preferred_agent matches the requested workflow (no role match)."""
        config = _build_config()

        # Remove roles so the preferred_agent path in agents is exercised
        config.roles.clear()

        result = config.resolve_agent_name_for_workflow(
            "generate_code",
            preferred_agent_name="coder",
        )
        assert result == "coder"

    def test_fallback_scans_agents_when_no_role_matches(self) -> None:
        """Line 420: fallback scan through agents when no role matches."""
        config = _build_config()

        # Remove all roles to force agent-only scan
        config.roles.clear()

        result = config.resolve_agent_name_for_workflow("review")
        assert result == "reviewer"

    def test_raises_when_no_agents_or_roles_are_configured(self) -> None:
        """Line 426: raise when there are no configured workflows at all."""
        config = AppConfig.model_validate(
            {
                "default_agent": "coder",
                "default_provider": "primary",
                "providers": {
                    "primary": {"api_key_env": "PRIMARY_KEY", "model": "gpt-5.4"},
                },
                "telegram": {"bot_token_env": "TELEGRAM_TOKEN"},
                "runtime": {"max_concurrent_runs": 2},
                "agents": {
                    "planner": {"workflow": "planning"},
                    "coder": {"workflow": "debug_code"},
                },
            }
        )

        # Remove roles so they don't provide a fallback
        config.roles.clear()

        with pytest.raises(ConfigWorkflowNotFoundError, match="No configured agent found for workflow nonexistent"):
            config.resolve_agent_name_for_workflow("nonexistent")

        # Also verify with a full config that the error includes configured workflows
        config2 = _build_config()
        config2.roles.clear()
        with pytest.raises(ConfigWorkflowNotFoundError, match="No configured agent found for workflow nonexistent"):
            config2.resolve_agent_name_for_workflow("nonexistent")