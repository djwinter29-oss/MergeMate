"""Agent domain package.

Role Souls are defined in ``soul.py`` — the canonical identity for
each role (planner, architect, coder, tester, reviewer, chronicler, explainer).
"""

from mergemate.domain.agents.soul import (
    DocPermission,
    Soul,
    all_souls,
    get_soul,
)

__all__ = [
    "DocPermission",
    "Soul",
    "all_souls",
    "get_soul",
]