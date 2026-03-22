"""Built-in syntax checker tool."""


class SyntaxCheckerTool:
    name = "syntax_checker"

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