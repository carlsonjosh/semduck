from __future__ import annotations

from typing import Protocol

from semduck.llm.config import ResolvedLLMConfig


class ProviderAdapter(Protocol):
    provider_type: str

    def build_model(self, config: ResolvedLLMConfig):
        ...


class OpenAICompatibleAdapter:
    provider_type = "openai_compatible"

    def build_model(self, config: ResolvedLLMConfig):
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider

        provider = OpenAIProvider(
            base_url=config.base_url,
            api_key=config.api_key,
        )
        return OpenAIChatModel(config.model, provider=provider)


class OllamaAdapter:
    provider_type = "ollama"

    def build_model(self, config: ResolvedLLMConfig):
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.ollama import OllamaProvider

        provider = OllamaProvider(
            base_url=config.base_url,
            api_key=config.api_key,
        )
        return OpenAIChatModel(config.model, provider=provider)
