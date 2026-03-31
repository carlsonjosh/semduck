from __future__ import annotations

from semduck.llm import (
    LLMConfig,
    ProviderConfig,
    create_provider_registry,
    load_and_resolve_llm_config,
    load_llm_config,
    resolve_llm_log_dir,
    resolve_llm_config,
)


def test_load_llm_config_reads_yaml_shape(tmp_path):
    config_path = tmp_path / "semduck.yaml"
    config_path.write_text(
        """
        llm:
          default_provider: ollama
          default_model: llama3.1
          providers:
            ollama:
              type: ollama
              model: llama3.1
              base_url: http://localhost:11434/v1
        """,
        encoding="utf-8",
    )

    config = load_llm_config(config_path)

    assert config.default_provider == "ollama"
    assert config.log_dir is None
    assert config.providers["ollama"].base_url == "http://localhost:11434/v1"


def test_load_llm_config_reads_log_dir(tmp_path):
    config_path = tmp_path / "semduck.yaml"
    config_path.write_text(
        """
        llm:
          default_provider: ollama
          log_dir: .semduck/llm-logs
          providers:
            ollama:
              type: ollama
              model: llama3.1
        """,
        encoding="utf-8",
    )

    config = load_llm_config(config_path)

    assert config.log_dir == ".semduck/llm-logs"


def test_resolve_llm_config_uses_override_precedence():
    config = LLMConfig(
        default_provider="ollama",
        default_model="llama3.1",
        providers={
            "ollama": ProviderConfig(
                type="ollama",
                model="llama3.1",
                base_url="http://config-host:11434/v1",
            ),
        },
    )

    resolved = resolve_llm_config(
        config,
        provider="ollama",
        model="custom-model",
        base_url="http://override-host:11434/v1",
        env={
            "SEMDUCK_LLM_MODEL": "env-model",
            "SEMDUCK_LLM_BASE_URL": "http://env-host:11434/v1",
        },
    )

    assert resolved.model == "custom-model"
    assert resolved.base_url == "http://override-host:11434/v1"


def test_resolve_llm_config_uses_env_for_api_key_reference():
    config = LLMConfig(
        default_provider="openai",
        providers={
            "openai": ProviderConfig(
                type="openai_compatible",
                model="gpt-4.1-mini",
                api_key_env="OPENAI_API_KEY",
            ),
        },
    )

    resolved = resolve_llm_config(
        config,
        env={"OPENAI_API_KEY": "secret-key"},
    )

    assert resolved.provider_type == "openai_compatible"
    assert resolved.api_key == "secret-key"


def test_resolve_llm_log_dir_uses_override_precedence():
    config = LLMConfig(log_dir=".semduck/default-logs")

    assert str(resolve_llm_log_dir(config)) == ".semduck/default-logs"
    assert str(resolve_llm_log_dir(config, env={"SEMDUCK_LLM_LOG_DIR": "env-logs"})) == "env-logs"
    assert str(resolve_llm_log_dir(config, log_dir="cli-logs")) == "cli-logs"
    assert resolve_llm_log_dir(config, disable_log=True) is None


def test_load_and_resolve_llm_config_uses_env_provider_override(tmp_path):
    config_path = tmp_path / "semduck.yaml"
    config_path.write_text(
        """
        llm:
          default_provider: ollama
          providers:
            ollama:
              type: ollama
              model: llama3.1
              base_url: http://localhost:11434/v1
            local_openai:
              type: openai_compatible
              model: qwen2.5
              base_url: http://localhost:8000/v1
        """,
        encoding="utf-8",
    )

    _, resolved = load_and_resolve_llm_config(
        str(config_path),
        env={"SEMDUCK_LLM_PROVIDER": "local_openai"},
    )

    assert resolved.provider_name == "local_openai"
    assert resolved.model == "qwen2.5"


def test_provider_registry_builds_openai_compatible_model():
    registry = create_provider_registry()
    resolved = resolve_llm_config(
        LLMConfig(
            default_provider="openai_compatible",
            default_model="test-model",
        ),
        base_url="http://localhost:8000/v1",
    )

    model = registry.build_model(resolved)

    assert model.model_name == "test-model"


def test_provider_registry_builds_ollama_model():
    registry = create_provider_registry()
    resolved = resolve_llm_config(
        LLMConfig(
            default_provider="ollama",
            default_model="llama3.1",
        ),
        base_url="http://localhost:11434/v1",
    )

    model = registry.build_model(resolved)

    assert model.model_name == "llama3.1"


def test_resolve_llm_config_rejects_unknown_provider():
    try:
        resolve_llm_config(LLMConfig(), provider="unknown")
    except ValueError as exc:
        assert "Unknown LLM provider" in str(exc)
    else:
        raise AssertionError("Expected ValueError")
