"""Built-in source formatter tool for simple MVP cleanup."""

from mergemate.domain.tools.entities import ToolMetadata


class CodeFormatterTool:
    name = "code_formatter"
    metadata = ToolMetadata(
        name=name,
        runtime_mode="manual",
        read_only=True,
        blocks_run_state="waiting_tool",
    )

    def invoke(self, payload: dict[str, str]) -> dict[str, str]:
        source = payload.get("source", "")
        if not source.strip():
            return {"status": "error", "detail": "source is required."}

        formatted_lines = [line.rstrip() for line in source.splitlines()]
        formatted_source = "\n".join(formatted_lines).strip()
        if source.endswith("\n"):
            formatted_source += "\n"

        return {
            "status": "ok",
            "detail": "Source formatted.",
            "formatted_source": formatted_source,
        }