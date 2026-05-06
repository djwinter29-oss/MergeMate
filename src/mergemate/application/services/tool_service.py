"""Tool selection and invocation service."""

import asyncio
from collections.abc import Iterator

from mergemate.domain.tools.entities import ToolMetadata
from mergemate.domain.runs.value_objects import RunStage, RunStatus, tool_stage


class ToolService:
    def __init__(self, tool_registry, settings, *, run_repository=None, tool_event_repository=None) -> None:
        self._tool_registry = tool_registry
        self._settings = settings
        self._run_repository = run_repository
        self._tool_event_repository = tool_event_repository

    def list_enabled_tools(self, agent_name: str) -> list[str]:
        agent = self._settings.agents.get(agent_name)
        if agent is None:
            return []
        return [tool_name for tool_name in agent.tools if self._tool_registry.get_tool(tool_name) is not None]

    def install_package(self, package_name: str) -> dict[str, str]:
        installer = self._tool_registry.get_tool("package_installer")
        if installer is None:
            return {"status": "blocked", "detail": "Package installer tool is not available."}
        return installer.invoke({"package_name": package_name})

    def _record_tool_event(
        self,
        run_id: str | None,
        tool_name: str,
        *,
        action: str | None,
        status: str,
        detail: str,
    ) -> None:
        if run_id is None or self._tool_event_repository is None:
            return
        self._tool_event_repository.record(
            run_id=run_id,
            tool_name=tool_name,
            action=action or "invoke",
            status=status,
            detail=detail,
        )

    def _transition_run_for_tool(
        self,
        run_id: str | None,
        *,
        blocks_run_state: str | None,
        tool_name: str,
        resume_stage: str | RunStage,
        entering: bool,
    ) -> None:
        if run_id is None or self._run_repository is None or blocks_run_state != RunStatus.WAITING_TOOL.value:
            return
        current_run = self._run_repository.get(run_id) if hasattr(self._run_repository, "get") else None
        if current_run is not None and current_run.status in {
            RunStatus.COMPLETED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
        }:
            return
        if entering:
            self._run_repository.try_update_status(
                run_id,
                RunStatus.WAITING_TOOL,
                expected_current_status=RunStatus.RUNNING,
                current_stage=tool_stage(tool_name),
            )
            return
        if current_run is not None and current_run.status != RunStatus.WAITING_TOOL:
            return
        self._run_repository.try_update_status(
            run_id,
            RunStatus.RUNNING,
            expected_current_status=RunStatus.WAITING_TOOL,
            current_stage=resume_stage,
        )

    @staticmethod
    def _tool_exception_result(tool_name: str, error: Exception) -> dict[str, str]:
        detail = str(error).strip() or error.__class__.__name__
        return {
            "status": "error",
            "detail": f"Tool {tool_name} failed: {detail}",
        }

    def execute_enabled_tool(
        self,
        agent_name: str,
        tool_name: str,
        payload: dict[str, str],
        *,
        run_id: str | None = None,
        resume_stage: str | RunStage = RunStage.RETRIEVE_CONTEXT,
    ) -> dict[str, str]:
        agent = self._settings.agents.get(agent_name)
        configured_tools = agent.tools if agent is not None else []
        metadata = self._tool_registry.get_tool_metadata(tool_name)
        action = payload.get("action")
        if tool_name not in configured_tools:
            blocked_result = {
                "status": "blocked",
                "detail": f"Tool {tool_name} is not enabled for agent {agent_name}.",
            }
            self._record_tool_event(run_id, tool_name, action=action, status="blocked", detail=blocked_result["detail"])
            return blocked_result
        tool = self._tool_registry.get_tool(tool_name)
        if tool is None:
            blocked_result = {"status": "blocked", "detail": f"Tool {tool_name} is not available."}
            self._record_tool_event(run_id, tool_name, action=action, status="blocked", detail=blocked_result["detail"])
            return blocked_result

        blocks_run_state = metadata.blocks_run_state if metadata is not None else None
        self._transition_run_for_tool(
            run_id,
            blocks_run_state=blocks_run_state,
            tool_name=tool_name,
            resume_stage=resume_stage,
            entering=True,
        )
        self._record_tool_event(run_id, tool_name, action=action, status="started", detail="Invoking tool.")
        try:
            result = tool.invoke(payload)
        except Exception as error:
            result = self._tool_exception_result(tool_name, error)
        self._record_tool_event(
            run_id,
            tool_name,
            action=action,
            status=result.get("status", "unknown"),
            detail=result.get("detail", ""),
        )
        self._transition_run_for_tool(
            run_id,
            blocks_run_state=blocks_run_state,
            tool_name=tool_name,
            resume_stage=resume_stage,
            entering=False,
        )
        return result

    def build_runtime_tool_context(
        self,
        run_id: str,
        agent_name: str,
        *,
        resume_stage: str | RunStage = RunStage.RETRIEVE_CONTEXT,
    ) -> str:
        enabled_tools = self.list_enabled_tools(agent_name)
        if not enabled_tools:
            return ""

        lines = ["Enabled runtime tools:", *[f"- {tool_name}" for tool_name in enabled_tools]]
        for tool_name in enabled_tools:
            metadata = self._tool_registry.get_tool_metadata(tool_name)
            if (
                metadata is None
                or metadata.runtime_mode != "context"
                or metadata.default_action is None
                or not metadata.read_only
            ):
                continue
            result = self.execute_enabled_tool(
                agent_name,
                tool_name,
                {"action": metadata.default_action},
                run_id=run_id,
                resume_stage=resume_stage,
            )
            lines.extend(
                (
                    "",
                    f"{metadata.context_key or tool_name} ({result['status']}):",
                    result.get("detail", "").strip() or "(no detail)",
                )
            )
        return "\n".join(lines).strip()

    async def build_runtime_tool_context_async(
        self,
        run_id: str,
        agent_name: str,
        *,
        resume_stage: str | RunStage = RunStage.RETRIEVE_CONTEXT,
    ) -> str:
        return await asyncio.to_thread(
            self.build_runtime_tool_context,
            run_id,
            agent_name,
            resume_stage=resume_stage,
        )

    def _iter_platform_tool_metadata(self, platform: str | None = None) -> Iterator[tuple[str, ToolMetadata]]:
        for tool_name in self._tool_registry.list_tools():
            metadata = self._tool_registry.get_tool_metadata(tool_name)
            if metadata is None:
                continue
            if platform is not None and metadata.platform != platform:
                continue
            yield tool_name, metadata

    def get_repository_context(self, platform: str | None = None) -> dict[str, dict[str, str]]:
        context: dict[str, dict[str, str]] = {}
        platform_name = platform or self._settings.source_control.default_platform

        for tool_name, metadata in self._iter_platform_tool_metadata():
            if metadata.runtime_mode != "context" or metadata.default_action is None or not metadata.read_only:
                continue
            if metadata.platform is not None and metadata.platform != platform_name:
                continue
            tool = self._tool_registry.get_tool(tool_name)
            if tool is None:
                continue
            if metadata.context_key == "git":
                context[metadata.context_key] = tool.invoke({"action": metadata.default_action})
                continue
            if metadata.context_key is not None:
                context[metadata.context_key] = tool.invoke({"action": metadata.default_action})

        return context

    def get_platform_auth_status(self, platform: str) -> dict[str, str]:
        saw_platform_metadata = False
        for tool_name, metadata in self._iter_platform_tool_metadata(platform):
            saw_platform_metadata = True
            if metadata.auth_action is None:
                break
            tool = self._tool_registry.get_tool(tool_name)
            if tool is None:
                return {"status": "blocked", "detail": f"Platform tool {tool_name} is not enabled."}
            return tool.invoke({"action": metadata.auth_action})
        if saw_platform_metadata:
            return {"status": "blocked", "detail": f"Platform tool for {platform} is not enabled."}
        return {"status": "error", "detail": f"Unsupported platform: {platform}"}