from __future__ import annotations

from semduck.llm.config import LLMConfig, ResolvedLLMConfig, load_llm_config, resolve_llm_config
from semduck.llm.providers import OllamaAdapter, OpenAICompatibleAdapter, ProviderAdapter


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, ProviderAdapter] = {}

    def register(self, adapter: ProviderAdapter) -> None:
        self._providers[adapter.provider_type] = adapter

    def get(self, provider_type: str) -> ProviderAdapter:
        try:
            return self._providers[provider_type]
        except KeyError as exc:
            raise ValueError(f"Unsupported provider type: {provider_type}") from exc

    def build_model(self, config: ResolvedLLMConfig):
        return self.get(config.provider_type).build_model(config)


def create_provider_registry() -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register(OpenAICompatibleAdapter())
    registry.register(OllamaAdapter())
    return registry


def load_and_resolve_llm_config(
    config_path: str | None = None,
    *,
    provider: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    env: dict[str, str] | None = None,
) -> tuple[LLMConfig, ResolvedLLMConfig]:
    config = load_llm_config(config_path, env=env)
    resolved = resolve_llm_config(
        config,
        provider=provider,
        model=model,
        base_url=base_url,
        api_key=api_key,
        env=env,
    )
    return config, resolved
