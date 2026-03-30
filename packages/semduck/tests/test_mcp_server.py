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
