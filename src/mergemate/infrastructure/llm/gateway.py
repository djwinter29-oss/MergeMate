"""Gateway for single-model and parallel multi-model execution."""

import asyncio


class ParallelLLMGateway:
    def __init__(self, settings, clients: dict[str, object]) -> None:
        self._settings = settings
        self._clients = clients

    async def generate(self, agent_name: str, system_prompt: str, user_prompt: str) -> str:
        provider_names = self._settings.resolve_agent_provider_names(agent_name)
        available_names = [name for name in provider_names if name in self._clients]
        if not available_names:
            raise ValueError(f"No configured providers are available for agent {agent_name}")

        agent = self._settings.agents.get(agent_name)
        parallel_mode = agent.parallel_mode if agent is not None else "single"
        combine_strategy = agent.combine_strategy if agent is not None else "sectioned"

        if parallel_mode != "parallel" or len(available_names) == 1:
            return await self._clients[available_names[0]].generate(system_prompt, user_prompt)

        tasks = [
            self._generate_from_provider(name, system_prompt, user_prompt)
            for name in available_names
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        successful_results: list[tuple[str, str]] = []
        failures: list[tuple[str, str]] = []
        for provider_name, result in zip(available_names, results, strict=True):
            if isinstance(result, Exception):
                failures.append((provider_name, str(result)))
                continue
            successful_results.append((provider_name, result))

        if not successful_results:
            failure_detail = "; ".join(f"{name}: {detail}" for name, detail in failures)
            raise RuntimeError(f"All parallel model calls failed. {failure_detail}")

        if combine_strategy == "first_success":
            return successful_results[0][1]

        return self._format_sectioned_results(successful_results, failures)

    async def _generate_from_provider(
        self,
        provider_name: str,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        return await self._clients[provider_name].generate(system_prompt, user_prompt)

    @staticmethod
    def _format_sectioned_results(
        successful_results: list[tuple[str, str]],
        failures: list[tuple[str, str]],
    ) -> str:
        sections = []
        for provider_name, result_text in successful_results:
            sections.append(f"## {provider_name}\n{result_text.strip()}")
        if failures:
            failure_lines = [f"- {provider_name}: {detail}" for provider_name, detail in failures]
            sections.append("## failed_models\n" + "\n".join(failure_lines))
        return "\n\n".join(sections)