"""OpenAI adapter for the MVP provider integration."""

import httpx


class OpenAIAdapter:
    def __init__(
        self,
        model: str,
        api_key: str | None,
        timeout_seconds: int,
        provider_url: str,
        api_key_header: str,
        api_key_prefix: str,
        extra_headers: dict[str, str],
    ) -> None:
        self._model = model
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._provider_url = provider_url
        self._api_key_header = api_key_header
        self._api_key_prefix = api_key_prefix
        self._extra_headers = extra_headers

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
        auth_value = self._api_key
        if self._api_key_prefix:
            auth_value = f"{self._api_key_prefix} {self._api_key}"
        headers = {
            self._api_key_header: auth_value,
            "Content-Type": "application/json",
            **self._extra_headers,
        }

        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            response = await client.post(
                self._provider_url,
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
        return data["choices"][0]["message"]["content"].strip()