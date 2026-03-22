"""Execution estimate helpers."""


def estimate_duration(workflow: str) -> int:
    estimates = {
        "generate_code": 30,
        "debug_code": 45,
        "explain_code": 20,
    }
    return estimates.get(workflow, 60)