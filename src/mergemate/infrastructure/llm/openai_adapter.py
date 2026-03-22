"""OpenAI adapter for the MVP provider integration."""

import httpx


class OpenAIAdapter:
    def __init__(
        self,
        model: str,
        api_key: str | None,
        timeout_seconds: int,
        api_base_url: str | None = None,
    ) -> None:
        self._model = model
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._api_base_url = api_base_url or "https://api.openai.com/v1/chat/completions"

    async def generate(self, system_prompt: str, user_prompt: str) -> str:
        if not self._api_key:
            return (
                "Provider is not configured yet. Set the OpenAI API key in the configured "
                "environment variable to enable model-backed responses.\n\n"
                f"Request summary:\n{user_prompt[:1200]}"
            )

        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            response = await client.post(
                self._api_base_url,
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
        return data["choices"][0]["message"]["content"].strip()