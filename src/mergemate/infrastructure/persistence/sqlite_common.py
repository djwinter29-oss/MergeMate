"""Shared helpers for SQLite persistence."""

from __future__ import annotations

from datetime import datetime
import shlex


def _to_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


def agent_runs_search_text_sql(prefix: str) -> str:
    return (
        f"coalesce({prefix}.run_id, '') || ' ' || coalesce({prefix}.agent_name, '') || ' ' || "
        f"coalesce({prefix}.workflow, '') || ' ' || coalesce({prefix}.repo_name, '') || ' ' || "
        f"coalesce({prefix}.status, '') || ' ' || coalesce({prefix}.current_stage, '') || ' ' || "
        f"coalesce({prefix}.prompt, '') || ' ' || coalesce({prefix}.plan_text, '') || ' ' || "
        f"coalesce({prefix}.design_text, '') || ' ' || coalesce({prefix}.test_text, '') || ' ' || "
        f"coalesce({prefix}.review_text, '') || ' ' || coalesce({prefix}.result_text, '') || ' ' || "
        f"coalesce({prefix}.error_text, '')"
    )


def conversation_messages_search_text_sql(prefix: str) -> str:
    return f"coalesce({prefix}.content, '')"


def fts_quote(token: str) -> str:
    return '"' + token.replace('"', '""') + '"'


def build_fts_query(query: str) -> str | None:
    try:
        tokens = shlex.split(query)
    except ValueError:
        tokens = query.split()
    normalized = [token.strip() for token in tokens if token.strip()]
    if not normalized:
        return None
    return " AND ".join(fts_quote(token) for token in normalized)


__all__ = [
    "_to_datetime",
    "agent_runs_search_text_sql",
    "conversation_messages_search_text_sql",
    "build_fts_query",
    "fts_quote",
]
