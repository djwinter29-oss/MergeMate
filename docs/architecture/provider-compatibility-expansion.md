# Provider Compatibility Expansion

- **Status**: Draft
- **Design**: t_4da2550a
- **Roadmap**: Near-Term #3
- **Covers**: Adapter interface, config schema, routing, fallback chain, gateway composition

## 1. Current Architecture

```
LLMClient (Protocol)
  └── generate(system_prompt, user_prompt) -> str

OpenAIAdapter implements LLMClient
  └── httpx POST {provider_url}
  └── hardcoded chat-completions JSON shape
  └── _extract_message_content() parses choices[0].message.content

ParallelLLMGateway
  └── keyed Mapping[str, LLMClient]
  └── per-agent provider resolution via settings.resolve_agent_provider_names()
  └── parallel_mode / combine_strategy / first_success logic
```

Strengths:
- Single-method Protocol is easy to implement
- Gateway handles parallel execution, first-success, sectioned combine
- Config already supports per-agent `provider_names` and role-level override

Constraints:
- `OpenAIAdapter` is the only adapter — all providers treated as OpenAI-compatible
- `LLMClient.generate()` takes only two plain strings — no room for tools, multi-turn, or structured output
- No fallback chain across providers within a single call
- `ProviderConfig` has no `provider_type` discriminator — bootstrap blindly instantiates `OpenAIAdapter` for every entry
- No streaming support in the Protocol

## 2. Provider Adapter Interface

### Proposed: Segregated Protocol Family

Keep the simple `generate` for backward compatibility and add optional Protocols for advanced capabilities.

```python
class LLMClient(Protocol):
    """Minimal — every adapter must implement this."""
    async def generate(self, system_prompt: str, user_prompt: str) -> str: ...

class StreamingLLMClient(Protocol):
    """Optional — adapters that support token-by-token streaming."""
    async def generate_stream(
        self, system_prompt: str, user_prompt: str
    ) -> AsyncIterator[str]: ...

class ToolCallingLLMClient(Protocol):
    """Optional — adapters that support tool/function calling."""
    async def generate_with_tools(
        self,
        system_prompt: str,
        user_prompt: str,
        tools: list[dict[str, object]],
    ) -> ToolCallResult: ...
```

**Rationale for segregated (not unified) Protocols:**
- A unified `generate(system_prompt, user_prompt, *, tools=None, stream=False)` forces every adapter to handle unused branches (e.g., Anthropic's streaming format vs OpenAI's differs significantly). Adapters should only pay for capability they actually implement.
- Gateway code checks `isinstance(client, StreamingLLMClient)` before dispatching streaming — this is Pythonic runtime capability detection and avoids abstract base classes.
- New capabilities (vision, structured output) can be added as new Protocols without breaking existing adapters.

### Adapter Base Class (Convenience, Not Enforcement)

A `BaseLLMAdapter` mixin provides shared utilities: HTTP client lifecycle, timeout handling, response-size limits, error classification. Adapters inherit from it but still satisfy `LLMClient` structurally.

```python
class BaseLLMAdapter:
    """Shared HTTP setup and error classification for all adapters."""
    def __init__(self, config: ProviderConfig, api_key: str | None) -> None:
        self._config = config
        self._api_key = api_key
        self._http = httpx.AsyncClient(timeout=config.timeout_seconds)

    async def _classify_error(self, exc: Exception) -> ProviderError:
        """Map HTTP/network errors to domain exceptions (rate-limit, auth, timeout, server-error)."""

    async def close(self) -> None:
        await self._http.aclose()
```

### AnthropicAdapter Design

```python
class AnthropicAdapter(BaseLLMAdapter):
    """Messages API (https://docs.anthropic.com/en/api/messages)."""

    async def generate(self, system_prompt: str, user_prompt: str) -> str:
        payload = {
            "model": self._config.model,
            "max_tokens": self._config.max_tokens or 4096,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        }
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        response = await self._http.post(
            self._config.provider_url, headers=headers, json=payload
        )
        response.raise_for_status()
        data = response.json()
        return self._extract_content(data)

    @staticmethod
    def _extract_content(data: dict) -> str:
        """Parse Anthropic response — content[0].text vs choices[0].message.content."""
        content = data.get("content", [])
        if isinstance(content, list) and content:
            text_block = content[0]
            if isinstance(text_block, dict) and text_block.get("type") == "text":
                return text_block.get("text", "")
        raise ProviderResponseError("Unexpected Anthropic response format")
```

### GoogleGeminiAdapter (Outline)

```python
class GoogleGeminiAdapter(BaseLLMAdapter):
    """Gemini API (generateContent endpoint)."""

    async def generate(self, system_prompt: str, user_prompt: str) -> str:
        payload = {
            "contents": [{"parts": [{"text": user_prompt}]}],
            "systemInstruction": {"parts": [{"text": system_prompt}]},
        }
        headers = {"Content-Type": "application/json"}
        # API key goes as query param: ?key=...
        ...
```

## 3. Provider Configuration Schema

### Add `provider_type` discriminator to ProviderConfig

```python
class ProviderType(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    OPENAI_COMPATIBLE = "openai_compatible"  # Third-party OpenAI clones (DeepSeek, Together, etc.)

class ProviderConfig(BaseModel):
    provider_type: ProviderType = ProviderType.OPENAI  # NEW
    api_key_env: str
    model: str
    max_tokens: int | None = None  # NEW — Anthropic and others require explicit max_tokens
    timeout_seconds: int = Field(default=90, ge=1)
    provider_url: str = "https://api.openai.com/v1/chat/completions"
    api_key_header: str = "Authorization"
    api_key_prefix: str = "Bearer"
    extra_headers: dict[str, str] = Field(default_factory=dict)
```

### Configuration Example

```yaml
providers:
  gpt4:
    provider_type: openai
    api_key_env: OPENAI_API_KEY
    model: gpt-4o
  claude:
    provider_type: anthropic
    api_key_env: ANTHROPIC_API_KEY
    model: claude-sonnet-4-20250514
    max_tokens: 8192
    provider_url: https://api.anthropic.com/v1/messages
  gemini:
    provider_type: google
    api_key_env: GOOGLE_API_KEY
    model: gemini-2.0-flash
    provider_url: https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent
  deepseek:
    provider_type: openai_compatible
    api_key_env: DEEPSEEK_API_KEY
    model: deepseek-chat
    provider_url: https://api.deepseek.com/v1/chat/completions
```

### Bootstrap: Adapter Factory

Replace the `OpenAIAdapter(...)` loop in bootstrap.py with a factory:

```python
def _build_adapter(provider_name: str, provider_cfg: ProviderConfig, api_key: str | None) -> LLMClient:
    factory_map: dict[ProviderType, type[BaseLLMAdapter]] = {
        ProviderType.OPENAI: OpenAIAdapter,
        ProviderType.OPENAI_COMPATIBLE: OpenAIAdapter,
        ProviderType.ANTHROPIC: AnthropicAdapter,
        ProviderType.GOOGLE: GoogleGeminiAdapter,
    }
    adapter_cls = factory_map.get(provider_cfg.provider_type)
    if adapter_cls is None:
        raise ConfigurationError(f"No adapter for provider_type={provider_cfg.provider_type}")
    return adapter_cls(provider_cfg, api_key=api_key)
```

**OPENAI vs OPENAI_COMPATIBLE distinction**: Both use the same `OpenAIAdapter` class but the enum value signals intention in config validation and future differentiation (e.g., custom rate-limit profiles for third-party endpoints that may have stricter concurrency limits).

## 4. Provider Routing Logic

### Current State

Already supports per-agent/role `provider_names` list. `resolve_agent_provider_names()` returns the list with fallback to `default_provider`.

### Enhancement: Provider Weighting and Selection Strategy

```python
class ProviderSelector:
    """Encapsulates routing logic for choosing which provider(s) to use."""

    @staticmethod
    def resolve(
        agent_providers: list[str],
        available: Mapping[str, LLMClient],
        strategy: RoutingStrategy = "ordered",
    ) -> list[str]:
        """Return resolved, available provider names in invocation order."""
```

Strategies:

| Strategy | Behavior |
|----------|----------|
| `ordered` | Use providers in the order listed. First is primary, subsequent are fallbacks. |
| `priority` | Each provider has a priority score in config. Highest first. |
| `round_robin` | Distribute across equally-weighted providers for load spreading. |
| `cost_optimized` | Rank by per-token cost (requires `cost_per_token` in config). |

The ParallelLLMGateway already implements two execution modes (`single` and `parallel`). The routing strategy enhances the *ordering* of the list, not the parallelism. These are orthogonal:
- **Routing strategy** = which order to try/run providers
- **Parallel mode** = whether to run them simultaneously (`parallel`) or sequentially (`single`/`first_success`)

### Route to Per-Agent / Per-Role / Per-Default

Already solved. Summary of precedence:

1. `roles[agent_name].provider_names` (if non-empty)
2. `agents[agent_name].provider_names` (if non-empty)
3. `default_provider`

### Add `routing_strategy` to AgentConfig and RoleConfig

```python
class RoutingStrategy(str, Enum):
    ORDERED = "ordered"
    PRIORITY = "priority"
    ROUND_ROBIN = "round_robin"
    COST_OPTIMIZED = "cost_optimized"

# Add to AgentConfig and RoleConfig:
routing_strategy: RoutingStrategy = "ordered"
```

## 5. Fallback Chain

### Sequential Fallback (Within a Single Gateway Call)

When a provider fails (network error, rate-limit, server-error), the gateway retries with the next provider in the resolved list — without the caller knowing anything happened.

```python
async def _generate_with_fallback(
    self,
    agent_name: str,
    system_prompt: str,
    user_prompt: str,
) -> str:
    provider_names = self._resolve_provider_names_for_agent(agent_name)
    last_error: Exception | None = None

    for provider_name in provider_names:
        try:
            return await self._clients[provider_name].generate(system_prompt, user_prompt)
        except Exception as exc:
            last_error = exc
            logger.warning("Provider %s failed, falling back: %s", provider_name, exc)
            continue

    raise AllProvidersFailedError(
        f"All providers failed for agent {agent_name}. Last error: {last_error}"
    )
```

**When to fall back** (error classification in `BaseLLMAdapter._classify_error`):

| Error | Action |
|-------|--------|
| HTTP 429 (rate-limit) | Fall back immediately |
| HTTP 5xx (server error) | Fall back immediately |
| HTTP 4xx (auth/bad-request) | **Do NOT fall back** — re-raise, as it will fail identically on another provider |
| Network timeout | Fall back immediately |
| Parse error in response | Fall back (provider returned garbage) |

### Connection to Parallel Mode

- `parallel_mode = "single"` + `fallback = True` → sequential fallback across providers
- `parallel_mode = "parallel"` + `combine_strategy = "first_success"` → race across providers, already implemented
- `parallel_mode = "parallel"` + `combine_strategy = "sectioned"` → gather all results, combine with source attribution, already implemented

Add per-agent config flag `fallback_enabled: bool = True` to allow disabling.

## 6. ParallelLLMGateway Composition

### Current Gateway Architecture

```
ParallelLLMGateway
  └── _clients: Mapping[str, LLMClient]  — flat dict of all adapters
  └── generate()  — single method, delegates to strategy
  └── _generate_from_provider()  — thin wrapper
```

### Proposed: Layered Gateway with Fallback

```python
class FallbackProviderGroup:
    """A group of providers tried in sequence with fallback."""
    def __init__(self, providers: list[str], clients: Mapping[str, LLMClient]):
        ...

    async def generate(self, system_prompt: str, user_prompt: str) -> str:
        for provider_name in self.providers:
            try:
                return await self._clients[provider_name].generate(...)
            except ProviderError as exc:
                if _should_skip_fallback(exc):
                    raise
                continue
        raise AllProvidersFailedError(...)

class ParallelLLMGateway:
    _clients: Mapping[str, LLMClient]

    async def generate(
        self, agent_name: str, system_prompt: str, user_prompt: str
    ) -> str:
        provider_names = self._resolve_available_provider_names(agent_name)
        agent = self._settings.agents.get(agent_name)

        if agent and agent.parallel_mode == "parallel":
            # Current parallel logic — unchanged
            return await self._generate_parallel(
                provider_names, system_prompt, user_prompt, agent.combine_strategy
            )

        # Sequential with fallback (new)
        return await self._generate_sequential(
            provider_names, system_prompt, user_prompt
        )

    async def _generate_sequential(
        self, provider_names: list[str], system_prompt: str, user_prompt: str
    ) -> str:
        for name in provider_names:
            try:
                return await self._clients[name].generate(system_prompt, user_prompt)
            except ProviderError as exc:
                if _should_skip_fallback(exc):  # 4xx re-raises
                    raise
                logger.warning("Falling back from %s: %s", name, exc)
                continue
        raise AllProvidersFailedError(f"All providers failed")
```

### Key Design Decision: No Nested Gateway Composition

The design deliberately keeps a single `ParallelLLMGateway` with internal fallback logic rather than creating a separate `FallbackGateway` wrapper. Rationale:

- Fallback logic is tightly coupled to the error-classification system and routing resolution
- A wrapper would need to re-resolve provider names, creating a leaky abstraction
- Single gateway means single test surface for all provider interaction patterns

### Health Checking (Optional Enhancement)

An optional `health()` method on `LLMClient` enables pre-flight checking:

```python
class HealthCheckable(Protocol):
    async def health(self) -> bool: ...

# Gateway uses it to skip known-dead providers:
available = [n for n in names if await self._is_healthy(n)]
```

Implementation detail for each adapter: a lightweight GET to the provider's status endpoint or a no-op request with `max_tokens=1`.

## 7. Migration Path

### Phase 1 (This design — no code changes)
- Document the `ProviderType` enum and factory pattern
- Define `BaseLLMAdapter` and adapter Protocols
- Specify `AnthropicAdapter` and `GoogleGeminiAdapter` interfaces

### Phase 2 (Developer implementation)
1. Add `provider_type` to `ProviderConfig`, update config schema validation
2. Create `BaseLLMAdapter` (shared HTTP client + error classification)
3. Implement `AnthropicAdapter` and `GoogleGeminiAdapter`
4. Add `_build_adapter()` factory in bootstrap, replace `OpenAIAdapter` instantiation loop
5. Add fallback chain in `_generate_sequential()`
6. Add `routing_strategy` to config models
7. Wire `ProviderSelector` into gateway

### Phase 3 (Future)
- Streaming support via `StreamingLLMClient` Protocol
- Tool calling via `ToolCallingLLMClient` Protocol
- Health-check integration for pre-flight dead-provider detection
- Usage-based cost tracking and `cost_optimized` routing

## 8. Backward Compatibility

- **Config**: `provider_type` defaults to `"openai"` — existing configs with no `provider_type` field load identically
- **Adapter interface**: `LLMClient` Protocol is unchanged. `generate()` signature is stable. New Protocols are opt-in
- **Gateway**: `parallel_mode`/`combine_strategy` unchanged. Sequential fallback is the new default fallback behavior only when `provider_names` lists multiple providers — single-provider configs behave identically
- **Bootstrap**: Old `ProviderConfig` without `provider_type` → defaults to `ProviderType.OPENAI` → `OpenAIAdapter` → identical behavior

## 9. Open Questions

1. **Should `max_tokens` be per-adapter-overridable even for OpenAI?** Currently hardcoded in payload. Adding `max_tokens` to `ProviderConfig` (default None = provider-specific default) is zero-cost and forward-looking.

2. **Should we support provider-specific `api_key_env` only, or also inline keys?** Current approach (env-only) is the right security hygiene. Keep it.

3. **Does Anthropic's system prompt need a different Protocol method?** Anthropic's API puts `system` at the top level of the request JSON while OpenAI puts it inside `messages`. The adapter handles this internally — the `LLMClient.generate(system_prompt, user_prompt)` signature stays uniform. Good.

4. **Should `ProviderSelector` persist state across calls?** For `round_robin`, yes — needs a counter per agent. Use a `defaultdict[str, int]` on the gateway instance. For `cost_optimized`, needs token counters — out of scope for Phase 2.

5. **How does the config schema for `priority` work?** Optional `priority: int = 0` field on `ProviderConfig`. Higher = more preferred. Default 0 means all providers equally preferred when strategy is `priority`.

## 10. Summary of Changes

| Area | Change |
|------|--------|
| `ProviderConfig` | Add `provider_type: ProviderType`, `max_tokens: int \| None` |
| `AgentConfig` / `RoleConfig` | Add `routing_strategy: RoutingStrategy` |
| `LLMClient` Protocol | Unchanged (backward-compat) |
| New Protocols | `StreamingLLMClient`, `ToolCallingLLMClient` (Phase 3) |
| `BaseLLMAdapter` | New shared base with HTTP lifecycle + error classification |
| `OpenAIAdapter` | Refactor to inherit `BaseLLMAdapter` |
| `AnthropicAdapter` | New adapter |
| `GoogleGeminiAdapter` | New adapter |
| Bootstrap | Add `_build_adapter()` factory function |
| `ParallelLLMGateway` | Add `_generate_sequential()` with fallback chain |
| `ProviderSelector` | New utility for routing strategy resolution |
| Config example | Updated YAML showing provider_type for Anthropic, Google, DeepSeek |