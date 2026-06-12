"""Execution estimate helpers."""

from __future__ import annotations

import re

_WORKFLOW_BASE_SECONDS: dict[str, int] = {
    "generate_code": 30,
    "debug_code": 45,
    "explain_code": 20,
}

_REFERENCE_KEYWORDS = (
    "database",
    "api",
    "auth",
    "migration",
    "model",
    "schema",
    "config",
)

_MULTI_FILE_KEYWORDS = (
    "class",
    "interface",
    "module",
    "component",
    "service",
    "controller",
    "workflow",
    "tests",
)

_FILE_REFERENCE_PATTERN = re.compile(r"\b[\w./-]+\.(?:py|js|ts|md|yaml|yml|json|toml|sql|txt)\b")


def estimate_duration(workflow: str, prompt: str | None = None) -> int:
    """Estimate execution time for a workflow.

    The workflow still provides the base value, but prompt structure can now
    nudge the estimate up or down so user-facing progress messages are less
    stale than a pure per-workflow lookup.
    """

    base_seconds = _WORKFLOW_BASE_SECONDS.get(workflow, 60)
    multiplier = _prompt_complexity_multiplier(prompt)
    return max(5, int(round(base_seconds * multiplier)))


def _prompt_complexity_multiplier(prompt: str | None) -> float:
    if prompt is None:
        return 1.0

    normalized = prompt.strip()
    if not normalized:
        return 1.0

    word_count = len(normalized.split())
    if word_count < 20:
        multiplier = 0.8
    elif word_count <= 80:
        multiplier = 1.0
    elif word_count <= 200:
        multiplier = 1.15
    else:
        multiplier = 1.35

    lower_prompt = normalized.lower()
    keyword_bonus = min(
        sum(0.06 for keyword in _REFERENCE_KEYWORDS if keyword in lower_prompt),
        0.42,
    )
    multi_file_bonus = min(
        sum(0.12 for keyword in _MULTI_FILE_KEYWORDS if keyword in lower_prompt),
        0.48,
    )
    structural_bonus = 0.0
    if re.search(r"(?m)^\s*(?:[-*]|\d+[\).\]])\s+", normalized):
        structural_bonus += 0.08
    code_block_count = normalized.count("```") // 2
    structural_bonus += min(code_block_count * 0.08, 0.24)
    if _FILE_REFERENCE_PATTERN.search(normalized):
        structural_bonus += 0.08

    multiplier += keyword_bonus + multi_file_bonus + structural_bonus
    return max(0.5, min(multiplier, 2.5))
