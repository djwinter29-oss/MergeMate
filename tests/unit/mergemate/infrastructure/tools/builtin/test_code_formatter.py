from mergemate.infrastructure.tools.builtin.code_formatter import CodeFormatterTool


def test_code_formatter_trims_trailing_whitespace() -> None:
    tool = CodeFormatterTool()

    result = tool.invoke({"source": "x = 1   \nprint(x)   \n"})

    assert result["status"] == "ok"
    assert result["formatted_source"] == "x = 1\nprint(x)\n"


def test_code_formatter_requires_source() -> None:
    tool = CodeFormatterTool()

    result = tool.invoke({"source": "   "})

    assert result["status"] == "error"