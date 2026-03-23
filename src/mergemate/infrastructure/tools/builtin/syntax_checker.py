"""Built-in syntax checker tool."""

from mergemate.domain.tools.entities import ToolMetadata


class SyntaxCheckerTool:
    name = "syntax_checker"
    metadata = ToolMetadata(
        name=name,
        runtime_mode="manual",
        read_only=True,
        blocks_run_state="waiting_tool",
    )

    def invoke(self, payload: dict[str, str]) -> dict[str, str]:
        source = payload.get("source", "")
        language = payload.get("language", "python").strip().lower()

        if not source.strip():
            return {"status": "error", "detail": "source is required."}
        if language != "python":
            return {
                "status": "blocked",
                "detail": f"Syntax checker does not support language: {language}",
            }

        try:
            compile(source, "<mergemate>", "exec")
        except SyntaxError as exc:
            return {
                "status": "error",
                "detail": f"Python syntax error on line {exc.lineno}: {exc.msg}",
            }

        return {"status": "ok", "detail": "Python syntax check passed."}