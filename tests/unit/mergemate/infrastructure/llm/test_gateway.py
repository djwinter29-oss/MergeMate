from dataclasses import dataclass, field

import pytest

from mergemate.infrastructure.llm.gateway import ParallelLLMGateway


class ClientStub:
    def __init__(self, result: str | Exception) -> None:
        self.result = result
        self.calls = []

    async def generate(self, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


@dataclass(slots=True)
class AgentStub:
    parallel_mode: str = "single"
    combine_strategy: str = "sectioned"


@dataclass(slots=True)
class SettingsStub:
    provider_names: list[str]
    agents: dict[str, AgentStub] = field(default_factory=dict)

    def resolve_agent_provider_names(self, agent_name: str) -> list[str]:
        return self.provider_names


@pytest.mark.asyncio
async def test_generate_raises_when_no_providers_available() -> None:
    gateway = ParallelLLMGateway(SettingsStub(provider_names=["missing"]), {})

    with pytest.raises(ValueError, match="No configured providers"):
        await gateway.generate("coder", "system", "user")


@pytest.mark.asyncio
async def test_generate_uses_first_available_provider_for_single_mode() -> None:
    client = ClientStub("ok")
    settings = SettingsStub(provider_names=["one"], agents={"coder": AgentStub(parallel_mode="single")})
    gateway = ParallelLLMGateway(settings, {"one": client})

    result = await gateway.generate("coder", "system", "user")

    assert result == "ok"
    assert client.calls == [("system", "user")]


@pytest.mark.asyncio
async def test_generate_returns_first_success_for_parallel_mode() -> None:
    first = ClientStub("first")
    second = ClientStub("second")
    settings = SettingsStub(
        provider_names=["one", "two"],
        agents={"coder": AgentStub(parallel_mode="parallel", combine_strategy="first_success")},
    )
    gateway = ParallelLLMGateway(settings, {"one": first, "two": second})

    result = await gateway.generate("coder", "system", "user")

    assert result == "first"


@pytest.mark.asyncio
async def test_generate_formats_sectioned_parallel_results_and_failures() -> None:
    first = ClientStub(" first result ")
    second = ClientStub(RuntimeError("broken"))
    settings = SettingsStub(
        provider_names=["one", "two"],
        agents={"coder": AgentStub(parallel_mode="parallel", combine_strategy="sectioned")},
    )
    gateway = ParallelLLMGateway(settings, {"one": first, "two": second})

    result = await gateway.generate("coder", "system", "user")

    assert "## one\nfirst result" in result
    assert "## failed_models" in result
    assert "- two: broken" in result


@pytest.mark.asyncio
async def test_generate_raises_when_all_parallel_calls_fail() -> None:
    settings = SettingsStub(
        provider_names=["one", "two"],
        agents={"coder": AgentStub(parallel_mode="parallel")},
    )
    gateway = ParallelLLMGateway(
        settings,
        {"one": ClientStub(RuntimeError("boom")), "two": ClientStub(RuntimeError("snap"))},
    )

    with pytest.raises(RuntimeError, match="All parallel model calls failed"):
        await gateway.generate("coder", "system", "user")
