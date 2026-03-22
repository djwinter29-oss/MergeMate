"""Workflow policies."""


def supports_background_execution(workflow: str) -> bool:
    return workflow in {"generate_code", "debug_code", "explain_code"}