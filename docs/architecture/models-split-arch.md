# Architecture: Split `hermes_cli/models.py` into 3 files

**Author:** architect
**Date:** 2026-05-10
**Task:** t_d9a9cc61

## Motivation

`hermes_cli/models.py` has grown to 3556 lines with three distinct concerns mixed together:

1. **Data/model definitions** — static model catalogs, provider registries, config constants
2. **Resolver/fetcher functions** — I/O-bound functions that contact external APIs, resolve credentials, discover and normalize models
3. **Validator/helper functions** — pure validation, pricing formatting, boolean checks, URL/path helpers

Splitting into three files gives each concern a single place to evolve without polluting the others, and makes the module graph easier to reason about.

## Target Structure

```
hermes_cli/
  models.py        ← data definitions + cache vars + re-exports (remains importable as before)
  resolver.py      ← new: resolver/fetcher/normalizer functions
  validators.py    ← new: validator/formatting/boolean-helper functions
```

### File: `hermes_cli/models.py` (remaining)

**Contains only**:
- Static model catalogs:
  - `OPENROUTER_MODELS`, `VERCEL_AI_GATEWAY_MODELS`
  - `_PROVIDER_MODELS`, `_XAI_STATIC_FALLBACK`
  - `COPILOT_MODEL_ALIASES`
  - `_AZURE_FOUNDRY_RESPONSES_PREFIXES`, `_OPENAI_FAST_MODE_PREFIXES`
  - `_AGGREGATOR_PROVIDERS`, `_MODELS_DEV_PREFERRED`
  - `COPILOT_BASE_URL`, `COPILOT_MODELS_URL`, `COPILOT_EDITOR_VERSION`
  - `COPILOT_REASONING_EFFORTS_O_SERIES`, `COPILOT_REASONING_EFFORTS_GPT5`
  - `_HERMES_USER_AGENT`
- Provider registry:
  - `ProviderEntry` (NamedTuple)
  - `CANONICAL_PROVIDERS`, `_PROVIDER_LABELS`, `_PROVIDER_ALIASES`
  - `_KNOWN_PROVIDER_NAMES`
- Cache variables (all module-level `_*_cache` / `_*_cache_time` / `_*_cache_ttl` vars)
- Re-exports at bottom:
  ```python
  from hermes_cli.resolver import <all public resolver symbols>
  from hermes_cli.validators import <all public validator symbols>
  ```
- An `__all__` that lists all re-exported symbols + local data

### File: `hermes_cli/resolver.py` (new)

**Contains** all functions that involve any form of resolution, fetching, or probing:

| Category | Functions |
|---|---|
| Credential resolvers | `_resolve_openrouter_api_key`, `_resolve_nous_pricing_credentials`, `_resolve_copilot_catalog_api_key`, `_resolve_nous_portal_url`, `_get_custom_base_url` |
| Catalog fetchers (live API) | `fetch_openrouter_models`, `fetch_ai_gateway_models`, `fetch_models_with_pricing`, `fetch_ai_gateway_pricing`, `fetch_api_models`, `probe_api_models`, `_fetch_anthropic_models`, `_fetch_github_models`, `fetch_github_model_catalog`, `_fetch_ai_gateway_models`, `fetch_ollama_cloud_models` |
| LM Studio lifecycle | `probe_lmstudio_models`, `fetch_lmstudio_models`, `ensure_lmstudio_model_loaded`, `lmstudio_model_reasoning_options` |
| Nous Portal | `fetch_nous_account_tier`, `is_nous_free_tier`, `check_nous_free_tier`, `partition_nous_models_by_tier`, `fetch_nous_recommended_models`, `get_nous_recommended_aux_model`, `_extract_model_name`, `get_curated_nous_model_ids` |
| Provider & model resolution | `model_ids`, `ai_gateway_model_ids`, `get_pricing_for_provider`, `curated_models_for_provider`, `provider_model_ids`, `normalize_provider`, `provider_label`, `parse_model_input`, `detect_provider_for_model`, `detect_static_provider_for_model`, `_find_openrouter_slug`, `_resolve_static_model_alias`, `list_available_providers`, `normalize_copilot_model_id`, `normalize_opencode_model_id`, `_merge_with_models_dev`, `get_copilot_model_context`, `_payload_items` |
| API mode helpers | `copilot_model_api_mode`, `azure_foundry_model_api_mode`, `opencode_model_api_mode` |
| Context/reasoning | `github_model_reasoning_efforts`, `_github_reasoning_efforts_for_model_id` |
| Disk cache helpers | `_load_ollama_cloud_cache`, `_save_ollama_cloud_cache` |

**Imports from models.py:** needs all the provider registry constants (`CANONICAL_PROVIDERS`, `_PROVIDER_MODELS`, `_PROVIDER_LABELS`, `_PROVIDER_ALIASES`, etc.) and cache variables.

### File: `hermes_cli/validators.py` (new)

**Contains** all validation, formatting, and boolean-check functions:

| Category | Functions |
|---|---|
| Price helpers | `_is_model_free`, `_openrouter_model_is_free`, `_ai_gateway_model_is_free`, `_format_price_per_mtok`, `format_model_pricing_table` |
| Fast mode checks | `model_supports_fast_mode`, `resolve_fast_mode_overrides`, `_is_openai_fast_model`, `_is_anthropic_fast_model` |
| Model validation | `validate_requested_model`, `get_default_model_for_provider` |
| Copilot helpers | `_copilot_catalog_item_is_text_model`, `_is_github_models_base_url`, `_should_use_copilot_responses_api`, `copilot_default_headers`, `_copilot_catalog_ids` |
| Reasoning helpers | `_github_reasoning_efforts_for_model_id` |
| URL/path helpers | `_lmstudio_server_root`, `_lmstudio_request_headers`, `_strip_vendor_prefix`, `_strip_ollama_cloud_suffix`, `_ollama_cloud_cache_path` |
| Provider membership | `_provider_keys`, `_model_in_provider_catalog` |

## Backward Compatibility

All existing callers import from `hermes_cli.models`:

```python
from hermes_cli.models import normalize_provider   # still works
from hermes_cli.models import fetch_openrouter_models  # still works
from hermes_cli.models import validate_requested_model  # still works
```

The re-exports at the bottom of `models.py` ensure every previously-exported symbol is still importable from the same location. No caller changes needed.

Direct imports from the new files also work:

```python
from hermes_cli.resolver import normalize_provider
from hermes_cli.validators import validate_requested_model
```

## Cross-File Dependencies

```
models.py (data)     ← imports by: resolver.py, validators.py
     ↑                         ↑
     └── re-exports ───────────┘
                            (no caller changes needed)

resolver.py ←─ may import from → validators.py (if any helper function needs a validator)
validators.py ←─ may import from → resolver.py (if any validator needs a resolver)
```

In practice, some functions currently in models.py call others that will end up in different files. These cross-references need to become explicit imports between the new files. The coder should identify and update these during extraction.

## Implementation Notes

1. **Prefer identity** — don't rename, refactor, or reformat during the move. Exact code only.
2. **Cross-references** — if function A in resolver.py calls function B that's moving to validators.py, add `from hermes_cli.validators import B` to resolver.py.
3. **Circular imports** — avoid them. If two functions call each other, one must be a local import (inside the function) rather than a module-level import. Currently no evidence of cycles in models.py.
4. **Module docstrings** — each new file gets a docstring describing its concern.
5. **Verification** — `pytest tests` must pass, and all three import patterns listed above must work.