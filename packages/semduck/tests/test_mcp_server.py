from __future__ import annotations

import asyncio

from semduck.mcp import build_mcp_server


def test_build_mcp_server_registers_expected_components():
    server = build_mcp_server(db_path=":memory:")

    tool_names = set(asyncio.run(server.get_tools()))
    resource_names = set(asyncio.run(server.get_resources()))
    resource_templates = set(asyncio.run(server.get_resource_templates()))
    prompt_names = set(asyncio.run(server.get_prompts()))

    assert tool_names == {
        "init_registry",
        "check_definition",
        "load_definition",
        "compile_request",
        "query_request",
        "list_semantic_views",
        "describe_semantic_view",
    }
    assert "semduck://registry" in resource_names
    assert "semduck://grammar" in resource_names
    assert "semduck://views/{view_name}" in resource_templates
    assert prompt_names == {
        "ask_semduck_question",
        "choose_semantic_view",
        "debug_failed_request",
    }


def test_build_mcp_server_does_not_register_ask_tool():
    server = build_mcp_server(db_path=":memory:")
    tool_names = set(asyncio.run(server.get_tools()))
    assert "ask" not in tool_names


def test_registry_resource_mentions_configured_defaults():
    server = build_mcp_server(
        db_path=":memory:",
        config_path="packages/semduck/examples/ask_ollama_config.yaml",
    )

    resource = asyncio.run(server.get_resource("semduck://registry"))
    content = asyncio.run(resource.read())

    assert "Available semantic views:" in content
    assert "- none loaded" in content
    assert "provider=ollama" in content
    assert "model=gemma3" in content


def test_ask_prompt_contains_expected_workflow_steps():
    server = build_mcp_server(db_path=":memory:")

    prompt = asyncio.run(server.get_prompt("ask_semduck_question"))
    messages = asyncio.run(prompt.render({"question": "What is revenue by region?"}))
    rendered = "\n".join(message.content.text for message in messages)

    assert "Call list_semantic_views" in rendered
    assert "describe_semantic_view" in rendered
    assert "Draft a semduck request, not SQL" in rendered
    assert "Return the final answer with the semantic request and compiled SQL" in rendered


def test_grammar_resource_includes_empty_registry_hint():
    server = build_mcp_server(db_path=":memory:")

    resource = asyncio.run(server.get_resource("semduck://grammar"))
    content = asyncio.run(resource.read())

    assert "Generate semduck requests, not arbitrary SQL" in content
    assert "initialize and load the registry" in content
