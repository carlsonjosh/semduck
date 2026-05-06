from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal, Mapping, Sequence

import yaml
from pydantic import BaseModel, Field


ProviderType = Literal["openai_compatible", "ollama"]

DEFAULT_CONFIG_LOCATIONS = (
    Path(".semduck.yaml"),
    Path.home() / ".config" / "semduck" / "config.yaml",
)


class ProviderConfig(BaseModel):
    type: ProviderType
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    api_key_env: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)


class TaskLLMConfig(BaseModel):
    provider: str
    model: str


class LLMConfig(BaseModel):
    default_provider: str | None = None
    default_model: str | None = None
    log_dir: str | None = None
    tasks: dict[str, TaskLLMConfig] = Field(default_factory=dict)
    providers: dict[str, ProviderConfig] = Field(default_factory=dict)


class ResolvedLLMConfig(BaseModel):
    provider_name: str
    provider_type: ProviderType
    model: str
    base_url: str | None = None
    api_key: str | None = None
    api_key_env: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)


def default_config_path(env: Mapping[str, str] | None = None) -> Path | None:
    values = env or os.environ
    explicit = values.get("SEMDUCK_CONFIG")
    if explicit:
        return Path(explicit)

    for path in DEFAULT_CONFIG_LOCATIONS:
        if path.exists():
            return path

    return None


def load_llm_config(path: str | Path | None = None, *, env: Mapping[str, str] | None = None) -> LLMConfig:
    selected_path = Path(path) if path is not None else default_config_path(env)
    if selected_path is None:
        return LLMConfig()
    if not selected_path.exists():
        raise FileNotFoundError(f"Config file not found: {selected_path}")

    try:
        payload = yaml.safe_load(selected_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid LLM config YAML: {exc}") from exc
    llm_payload = payload.get("llm") if isinstance(payload, dict) else None
    if llm_payload is None:
        return LLMConfig()
    if not isinstance(llm_payload, dict):
        raise ValueError("llm config must be a mapping")
    return LLMConfig.model_validate(llm_payload)


def resolve_llm_config(
    config: LLMConfig | None = None,
    *,
    provider: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    env: Mapping[str, str] | None = None,
) -> ResolvedLLMConfig:
    values = env or os.environ
    current = config or LLMConfig()

    selected_provider = (
        provider
        or values.get("SEMDUCK_LLM_PROVIDER")
        or current.default_provider
    )
    if not selected_provider:
        raise ValueError("No LLM provider configured")

    named_provider = current.providers.get(selected_provider)
    if named_provider is not None:
        provider_name = selected_provider
        provider_type = named_provider.type
        config_model = named_provider.model
        config_base_url = named_provider.base_url
        config_api_key = named_provider.api_key
        config_api_key_env = named_provider.api_key_env
        config_options = dict(named_provider.options)
    else:
        if selected_provider not in {"openai_compatible", "ollama"}:
            raise ValueError(f"Unknown LLM provider: {selected_provider}")
        provider_name = selected_provider
        provider_type = selected_provider
        config_model = None
        config_base_url = None
        config_api_key = None
        config_api_key_env = None
        config_options = {}

    resolved_model = model or values.get("SEMDUCK_LLM_MODEL") or config_model or current.default_model
    if not resolved_model:
        raise ValueError(f"No model configured for provider: {provider_name}")

    resolved_base_url = base_url or values.get("SEMDUCK_LLM_BASE_URL") or config_base_url
    resolved_api_key_env = values.get("SEMDUCK_LLM_API_KEY_ENV") or config_api_key_env
    resolved_api_key = api_key or values.get("SEMDUCK_LLM_API_KEY") or config_api_key
    if resolved_api_key is None and resolved_api_key_env:
        resolved_api_key = values.get(resolved_api_key_env)

    return ResolvedLLMConfig(
        provider_name=provider_name,
        provider_type=provider_type,
        model=resolved_model,
        base_url=resolved_base_url,
        api_key=resolved_api_key,
        api_key_env=resolved_api_key_env,
        options=config_options,
    )


def resolve_llm_log_dir(
    config: LLMConfig | None = None,
    *,
    log_dir: str | None = None,
    disable_log: bool = False,
    env: Mapping[str, str] | None = None,
) -> Path | None:
    if disable_log:
        return None

    values = env or os.environ
    current = config or LLMConfig()
    selected_log_dir = log_dir or values.get("SEMDUCK_LLM_LOG_DIR") or current.log_dir
    if not selected_log_dir:
        return None
    return Path(selected_log_dir).expanduser()


def resolve_llm_task_configs(
    config: LLMConfig | None = None,
    *,
    task_names: Sequence[str],
    provider: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, ResolvedLLMConfig]:
    current = config or LLMConfig()
    values = env or os.environ

    if provider is not None or model is not None or base_url is not None or api_key is not None:
        resolved = resolve_llm_config(
            current,
            provider=provider,
            model=model,
            base_url=base_url,
            api_key=api_key,
            env=env,
        )
        return {task_name: resolved.model_copy(deep=True) for task_name in task_names}

    if current.tasks:
        missing_tasks = [task_name for task_name in task_names if task_name not in current.tasks]
        if missing_tasks:
            raise ValueError(
                "Task-specific LLM config must define all required tasks: "
                + ", ".join(task_names)
            )
        return {
            task_name: resolve_llm_config(
                current,
                provider=provider or values.get("SEMDUCK_LLM_PROVIDER") or current.tasks[task_name].provider,
                model=model or values.get("SEMDUCK_LLM_MODEL") or current.tasks[task_name].model,
                base_url=base_url,
                api_key=api_key,
                env=env,
            )
            for task_name in task_names
        }

    resolved = resolve_llm_config(
        current,
        provider=provider,
        model=model,
        base_url=base_url,
        api_key=api_key,
        env=env,
    )
    return {task_name: resolved.model_copy(deep=True) for task_name in task_names}
