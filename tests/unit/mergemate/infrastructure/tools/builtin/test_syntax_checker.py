from mergemate.infrastructure.tools.builtin.syntax_checker import SyntaxCheckerTool


def test_syntax_checker_accepts_valid_python() -> None:
    tool = SyntaxCheckerTool()

    result = tool.invoke({"source": "value = 1\nprint(value)\n", "language": "python"})

    assert result["status"] == "ok"


def test_syntax_checker_rejects_invalid_python() -> None:
    tool = SyntaxCheckerTool()

    result = tool.invoke({"source": "def broken(:\n    pass\n", "language": "python"})

    assert result["status"] == "error"
    assert "line" in result["detail"]


def test_syntax_checker_blocks_unsupported_languages() -> None:
    tool = SyntaxCheckerTool()

    result = tool.invoke({"source": "const x = 1;", "language": "javascript"})

    assert result["status"] == "blocked"