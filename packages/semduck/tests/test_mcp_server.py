from __future__ import annotations

import asyncio
from pathlib import Path
import sys

import duckdb
import yaml

from semduck.mcp import build_mcp_server


def test_import_semduck_does_not_eagerly_import_mcp():
    sys.modules.pop("semduck", None)
    sys.modules.pop("semduck.mcp", None)
    sys.modules.pop("semduck.mcp.server", None)

    import semduck

    assert "semduck.mcp" not in sys.modules
    assert "semduck.mcp.server" not in sys.modules

    build = semduck.build_mcp_server

    assert callable(build)
    assert "semduck.mcp" in sys.modules


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
    config_path = "packages/semduck/examples/ask_ollama_config.yaml"
    server = build_mcp_server(
        db_path=":memory:",
        config_path=config_path,
    )

    resource = asyncio.run(server.get_resource("semduck://registry"))
    content = asyncio.run(resource.read())
    config = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    model = config["llm"]["providers"]["ollama"]["model"]

    assert "Available semantic views:" in content
    assert "- none loaded" in content
    assert "provider=ollama" in content
    assert f"model={model}" in content


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


def test_mcp_server_reuses_connection_for_memory_database(orders_yaml_path):
    conn = duckdb.connect(":memory:")
    conn.execute("create schema mart")
    conn.execute(
        """
        create table mart.orders_base (
            order_id integer,
            customer_id integer,
            region varchar,
            order_date date,
            revenue double,
            unit_costs double
        )
        """
    )
    conn.execute(
        """
        create table mart.customers_base (
            customer_id integer,
            customer_segment varchar
        )
        """
    )
    conn.execute(
        """
        insert into mart.orders_base values
            (1, 10, 'US', '2024-01-01', 100.0, 60.0),
            (2, 11, 'US', '2024-01-02', 150.0, 90.0),
            (3, 12, 'CA', '2024-01-03', 200.0, 120.0)
        """
    )
    conn.execute(
        """
        insert into mart.customers_base values
            (10, 'Enterprise'),
            (11, 'SMB'),
            (12, 'Consumer')
        """
    )

    connect_calls = 0

    def fake_connect(path: str):
        nonlocal connect_calls
        connect_calls += 1
        assert path == ":memory:"
        return conn

    original_connect = build_mcp_server.__globals__["connect_database"]
    build_mcp_server.__globals__["connect_database"] = fake_connect
    try:
        server = build_mcp_server(db_path=":memory:")
        init_tool = asyncio.run(server.get_tool("init_registry"))
        load_tool = asyncio.run(server.get_tool("load_definition"))
        list_tool = asyncio.run(server.get_tool("list_semantic_views"))
        describe_tool = asyncio.run(server.get_tool("describe_semantic_view"))
        query_tool = asyncio.run(server.get_tool("query_request"))

        asyncio.run(init_tool.run({}))
        asyncio.run(load_tool.run({"file": str(orders_yaml_path)}))
        listed = asyncio.run(list_tool.run({}))
        described = asyncio.run(describe_tool.run({"view_name": "orders_semantic"}))
        query_result = asyncio.run(
            query_tool.run(
                {"request": "orders_semantic dimensions region metrics total_revenue"}
            )
        )
    finally:
        build_mcp_server.__globals__["connect_database"] = original_connect
        conn.close()

    assert connect_calls == 1
    assert listed.structured_content["view_names"] == ["orders_semantic"]
    assert described.structured_content["view_name"] == "orders_semantic"
    assert sorted(query_result.structured_content["rows"]) == [["CA", 200.0], ["US", 250.0]]
