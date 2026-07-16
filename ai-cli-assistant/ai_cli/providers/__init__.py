from __future__ import annotations

from typing import Any, Dict

from ..config import resolve_api_key
from .base import Provider, ProviderError

_REGISTRY = {}


def _lazy_registry():
    if not _REGISTRY:
        from .anthropic_provider import AnthropicProvider
        from .ollama_provider import OllamaProvider
        from .openai_provider import OpenAIProvider

        _REGISTRY.update(
            {
                "anthropic": AnthropicProvider,
                "openai": OpenAIProvider,
                "ollama": OllamaProvider,
                # All of these speak the OpenAI-compatible chat completions
                # API, so they reuse OpenAIProvider with a different
                # base_url / api key baked in via provider_options.
                "openrouter": OpenAIProvider,
                "groq": OpenAIProvider,
                "together": OpenAIProvider,
                "deepseek": OpenAIProvider,
                "openai_compatible": OpenAIProvider,
            }
        )
    return _REGISTRY


def build_provider(model_name: str, cfg: Dict[str, Any]) -> Provider:
    models = cfg.get("models", {})
    if model_name not in models:
        raise ProviderError(
            f"Unknown model '{model_name}'. Known models: {', '.join(sorted(models)) or '(none configured)'}"
        )
    spec = models[model_name]
    provider_key = spec["provider"]
    registry = _lazy_registry()
    if provider_key not in registry:
        raise ProviderError(f"Unknown provider '{provider_key}'")

    provider_cls = registry[provider_key]
    provider_opts = dict(cfg.get("provider_options", {}).get(provider_key, {}))
    # Per-model overrides win over the provider's defaults -- this is what
    # lets several "openai"-provider models point at different endpoints
    # (OpenAI itself, Groq, OpenRouter, Gemini's OpenAI-compatible API, ...).
    per_model_overrides = {k: v for k, v in spec.items() if k not in ("provider", "model")}
    provider_opts.update(per_model_overrides)

    kwargs: Dict[str, Any] = {"model": spec["model"]}
    if "api_key_env" in provider_opts:
        kwargs["api_key"] = resolve_api_key(provider_opts.pop("api_key_env"))
    kwargs.update(provider_opts)
    return provider_cls(**kwargs)


__all__ = ["build_provider", "Provider", "ProviderError"]
