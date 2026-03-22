"""Built-in source formatter tool for simple MVP cleanup."""


class CodeFormatterTool:
    name = "code_formatter"

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