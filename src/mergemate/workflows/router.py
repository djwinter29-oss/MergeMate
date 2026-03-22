"""Workflow router placeholder."""


def resolve_workflow(agent_name: str) -> str:
    mapping = {
        "coder": "generate_code",
        "debugger": "debug_code",
        "explainer": "explain_code",
    }
    return mapping.get(agent_name, "generate_code")