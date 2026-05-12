# mypy: allow-untyped-defs
"""Learning memory service backed by persisted successful runs."""

import json
import logging

logger = logging.getLogger(__name__)

_EXTRACT_SYSTEM_PROMPT = """You are a lesson extraction assistant. Analyze the
following result text and extract structured lessons in JSON format. Respond
with ONLY valid JSON, no commentary, no markdown formatting."""


class LearningService:
    def __init__(
        self,
        learning_repository,
        enabled: bool,
        max_context_items: int,
        max_result_chars: int,
        llm_gateway=None,
        extraction_agent_name: str | None = None,
        repo_knowledge_repository=None,
    ) -> None:
        self._learning_repository = learning_repository
        self._enabled = enabled
        self._max_context_items = max_context_items
        self._max_result_chars = max_result_chars
        self._llm_gateway = llm_gateway
        self._extraction_agent_name = extraction_agent_name or "default"
        self._repo_knowledge_repository = repo_knowledge_repository

    async def remember_success(
        self, *, chat_id: int, workflow: str, prompt: str, result_text: str
    ) -> None:
        if not self._enabled:
            return
        excerpt = result_text.strip()[: self._max_result_chars]
        lessons = await self._extract_lessons(result_text)
        self._learning_repository.record(chat_id, workflow, prompt, excerpt, lessons)

    def load_recent_learnings(self, chat_id: int) -> list[dict[str, str]]:
        if not self._enabled:
            return []
        return self._learning_repository.list_recent(chat_id, limit=self._max_context_items)

    def remember_repo_knowledge(
        self, *, chat_id: int, repo_name: str, topic: str, summary: str
    ) -> None:
        if not self._enabled or self._repo_knowledge_repository is None:
            return
        self._repo_knowledge_repository.record(chat_id, repo_name, topic, summary)

    def load_repo_knowledge(
        self, chat_id: int, repo_name: str | None = None
    ) -> list[dict[str, str]]:
        if not self._enabled or self._repo_knowledge_repository is None:
            return []
        return self._repo_knowledge_repository.list_recent(
            chat_id, repo_name=repo_name, limit=self._max_context_items
        )

    def load_grouped_learnings(self, chat_id: int, current_workflow: str) -> list[dict[str, str]]:
        if not self._enabled:
            return []
        return self._learning_repository.list_grouped_by_workflow(
            chat_id=chat_id,
            current_workflow=current_workflow,
            same_workflow_limit=self._max_context_items,
            other_workflow_limit=1,
        )

    async def _extract_lessons(self, result_text: str) -> str:
        """Extract structured lessons from result text using LLM.

        Returns a JSON string with keys: technical_points, pitfalls,
        patterns, conclusion. Returns ``"{}"`` on failure or when
        ``llm_gateway`` is not configured (best-effort extraction).
        """
        if self._llm_gateway is None:
            return "{}"
        try:
            raw = await self._llm_gateway.generate(
                self._extraction_agent_name,
                _EXTRACT_SYSTEM_PROMPT,
                result_text,
            )
            # Validate it's parseable JSON with expected keys
            parsed = json.loads(raw)
            if not isinstance(parsed, dict):
                return "{}"
            # Ensure at least the 4 expected keys exist
            for key in ("technical_points", "pitfalls", "patterns", "conclusion"):
                if key not in parsed:
                    parsed[key] = [] if key != "conclusion" else ""
            return json.dumps(parsed)
        except Exception:
            logger.exception("Failed to extract lessons from result text")
            return "{}"
