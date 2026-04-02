from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb
from fastmcp import FastMCP

from semduck.agent.models import (
    CheckDefinitionArgs,
    CompileRequestArgs,
    DescribeSemanticViewArgs,
    LoadDefinitionArgs,
    QueryRequestArgs,
)
from semduck.agent.services import (
    check_definition_service,
    compile_request_service,
    describe_semantic_view_service,
    init_registry_service,
    list_semantic_views_service,
    load_definition_service,
    query_request_service,
)
from semduck.llm import load_and_resolve_llm_config


@dataclass
class ServerDependencies:
    db_path: str
    config_path: str | None = None
    provider: str | None = None
    model: str | None = None
    conn: Any | None = None

    def connect(self):
        if self.conn is None:
            self.conn = duckdb.connect(self.db_path)
        return self.conn


def _provider_defaults_summary(deps: ServerDependencies) -> str:
    try:
        _, resolved = load_and_resolve_llm_config(
            deps.config_path,
            provider=deps.provider,
            model=deps.model,
        )
    except Exception:
        return "No default ask model is configured on the server."

    return (
        "Default ask model configuration for clients: "
        f"provider={resolved.provider_name}, model={resolved.model}."
    )


def build_mcp_server(
    *,
    db_path: str,
    config_path: str | None = None,
    provider: str | None = None,
    model: str | None = None,
) -> FastMCP:
    deps = ServerDependencies(
        db_path=db_path,
        config_path=config_path,
        provider=provider,
        model=model,
    )
    mcp = FastMCP("semduck")

    @mcp.tool
    def init_registry() -> dict[str, Any]:
        """Initialize the semduck registry schema in the configured DuckDB database."""
        return init_registry_service(deps.connect()).model_dump()

    @mcp.tool
    def check_definition(file: str, format: str = "auto") -> dict[str, Any]:
        """Validate a semantic definition file without writing it to the registry."""
        return check_definition_service(
            deps.connect(),
            CheckDefinitionArgs(file=file, format=format),
        ).model_dump()

    @mcp.tool
    def load_definition(file: str, format: str = "auto", replace_existing: bool = True) -> dict[str, Any]:
        """Load a semantic definition file into the registry."""
        return load_definition_service(
            deps.connect(),
            LoadDefinitionArgs(file=file, format=format, replace_existing=replace_existing),
        ).model_dump()

    @mcp.tool
    def compile_request(request: str) -> dict[str, Any]:
        """Compile a semduck semantic request to SQL."""
        return compile_request_service(
            deps.connect(),
            CompileRequestArgs(request=request),
        ).model_dump()

    @mcp.tool
    def query_request(request: str) -> dict[str, Any]:
        """Execute a semduck semantic request and return SQL plus tabular results."""
        return query_request_service(
            deps.connect(),
            QueryRequestArgs(request=request),
        ).model_dump()

    @mcp.tool
    def list_semantic_views() -> dict[str, Any]:
        """List semantic views available in the registry."""
        return list_semantic_views_service(deps.connect()).model_dump()

    @mcp.tool
    def describe_semantic_view(view_name: str) -> dict[str, Any]:
        """Describe one semantic view, including tables, dimensions, facts, metrics, and joins."""
        return describe_semantic_view_service(
            deps.connect(),
            DescribeSemanticViewArgs(view_name=view_name),
        ).model_dump()

    @mcp.resource("semduck://registry")
    def registry_overview() -> str:
        view_names = list_semantic_views_service(deps.connect()).view_names
        lines = [
            f"Database: {deps.db_path}",
            "Available semantic views:",
        ]
        if view_names:
            lines.extend(f"- {name}" for name in view_names)
        else:
            lines.append("- none loaded")
            lines.append("Hint: initialize and load semantic definitions before using ask-oriented MCP workflows.")
        lines.append(_provider_defaults_summary(deps))
        return "\n".join(lines)

    @mcp.resource("semduck://grammar")
    def request_grammar() -> str:
        return (
            "Semduck requests use this general shape:\n"
            "<view_name> dimensions <dimension list> metrics <metric list> where <optional predicate>\n\n"
            "Examples:\n"
            "- orders_semantic dimensions region metrics total_revenue\n"
            "- orders_semantic dimensions customer_name metrics total_revenue where region = 'US'\n\n"
            "Use compile_request before query_request. Generate semduck requests, not arbitrary SQL.\n"
            "If no semantic views are loaded yet, initialize and load the registry before attempting ask workflows."
        )

    @mcp.resource("semduck://views/{view_name}")
    def semantic_view_resource(view_name: str) -> dict[str, Any]:
        return describe_semantic_view_service(
            deps.connect(),
            DescribeSemanticViewArgs(view_name=view_name),
        ).model_dump()

    @mcp.prompt
    def ask_semduck_question(question: str) -> str:
        """Guide a host LLM through answering a user analytics question with semduck tools."""
        return (
            f"Answer this analytics question using semduck: {question}\n\n"
            "Workflow:\n"
            "1. Call list_semantic_views.\n"
            "2. Call describe_semantic_view for the most relevant view.\n"
            "3. Draft a semduck request, not SQL.\n"
            "4. Call compile_request to validate it and inspect the SQL.\n"
            "5. If compile fails, revise the semduck request and retry.\n"
            "6. Call query_request only after compilation succeeds.\n"
            "7. Return the final answer with the semantic request and compiled SQL."
        )

    @mcp.prompt
    def choose_semantic_view(question: str) -> str:
        """Guide a host LLM through selecting the right semantic view before compiling a request."""
        return (
            f"Choose the best semduck semantic view for this question: {question}\n\n"
            "Call list_semantic_views first, then inspect candidate views with describe_semantic_view.\n"
            "Prefer the smallest view that contains the needed dimensions and metrics."
        )

    @mcp.prompt
    def debug_failed_request(request: str, error: str) -> str:
        """Guide a host LLM through revising a semduck request after a compile or query failure."""
        return (
            f"The semduck request failed.\nRequest: {request}\nError: {error}\n\n"
            "Inspect the semantic view again if needed. Revise the semduck request rather than writing raw SQL. "
            "Re-run compile_request before trying query_request again."
        )

    return mcp


def run_mcp_server(
    *,
    db_path: str,
    config_path: str | None = None,
    provider: str | None = None,
    model: str | None = None,
) -> None:
    server = build_mcp_server(
        db_path=db_path,
        config_path=config_path,
        provider=provider,
        model=model,
    )
    server.run(transport="stdio")
