"""OpenAI adapter for the MVP provider integration."""

import httpx


def _extract_message_content(data: dict[str, object]) -> str:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("Provider returned an invalid response: missing choices[0].")
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise RuntimeError("Provider returned an invalid response: choices[0] was not an object.")
    message = first_choice.get("message")
    if not isinstance(message, dict):
        raise RuntimeError("Provider returned an invalid response: choices[0].message was missing.")
    content = message.get("content")
    if not isinstance(content, str):
        raise RuntimeError("Provider returned an invalid response: choices[0].message.content was not text.")
    return content.strip()


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
            raise RuntimeError(
                "Provider is not configured. Set the configured API key environment variable "
                f"for model {self._model} before executing this workflow."
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
        if not isinstance(data, dict):
            raise RuntimeError("Provider returned an invalid response: top-level JSON object was expected.")
        return _extract_message_content(data)