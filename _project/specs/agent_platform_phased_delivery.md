# Agent Platform v1: Phased Delivery Plan

## Status

Proposed.

## Addresses Issue

- None yet.

## Implemented By

- None yet.

## Summary

Add an agent-facing platform to `semduck` in phases so each phase is independently implementable,
testable, and useful on its own.

The end state remains:

- `semduck ask`, implemented with `pydantic_ai`
- `semduck mcp`, implemented with `FastMCP`
- one shared semduck-owned tool/service core used by both

The phased plan deliberately avoids building both front ends at once. It establishes the shared
typed core first, then adds the CLI ask flow, then adds the MCP server with prompts/resources for
host-driven ask workflows.

## Key Changes

### Final architecture

The completed implementation should have these layers:

- existing `semduck.api` and runtime/compiler stay as the execution engine
- a new shared `semduck.agent` core defines typed services and tool schemas
- `semduck ask` uses a `pydantic_ai` agent wired to that shared core
- `semduck mcp` uses `FastMCP` to expose the shared core as tools, plus MCP resources and prompts

The MCP server should not expose `ask` as a tool. In MCP, the host LLM is the question-answering
agent. The server should expose the capabilities and guidance needed for the host to run the ask
workflow itself.

### Phase 1: Shared typed core

Goal:

- establish the reusable semduck-owned operations that both front ends will call

Scope:

- add a new package area such as `semduck.agent`
- define service functions and Pydantic request/response models for:
  - `init_registry`
  - `check_definition`
  - `load_definition`
  - `compile_request`
  - `query_request`
  - `list_semantic_views`
  - `describe_semantic_view`
- normalize common result and error shapes
- keep all business logic in this layer framework-agnostic

Implementation notes:

- the core should wrap existing `semduck.api` functions rather than duplicating runtime logic
- `list_semantic_views` should read the registry and return view names only
- `describe_semantic_view` should return a compact typed descriptor suitable for prompts and MCP
  resources
- add additive Python exports for these new APIs

Out of scope:

- no `pydantic_ai`
- no `FastMCP`
- no LLM provider config yet unless needed as a stub for later phases

Deliverable:

- a stable internal tool/service layer that can be called directly from tests or future adapters

### Phase 2: LLM config and provider registry

Goal:

- make model/provider selection explicit before building the ask agent

Scope:

- add `semduck.llm.config` for file + env + explicit override resolution
- add `semduck.llm.registry` and provider adapters that build `pydantic_ai` model backends
- support these provider types in v1:
  - `openai_compatible`
  - `ollama`

Implementation notes:

- config precedence should be:
  1. explicit CLI arguments
  2. environment variables
  3. config file defaults
- config should support provider defaults and named provider entries
- secrets should be referenced by env var name where possible instead of stored directly in config

Deliverable:

- a resolved provider/model configuration that the ask agent can consume without needing provider
  decisions in the agent layer

### Phase 3: `semduck ask` via `pydantic_ai`

Goal:

- ship a usable natural-language query flow in the CLI

Scope:

- add `semduck ask`
- implement the ask workflow as a `pydantic_ai.Agent`
- register shared semduck tools from Phase 1
- constrain the agent to generate semduck requests and use semduck compile/query tools

Required CLI flags:

- `--db`
- `--question`

Optional CLI flags:

- `--config`
- `--provider`
- `--model`
- `--view`
- `--sql-only`
- `--output-format text|json`

Behavior:

- execute by default
- `--sql-only` generates a semduck request and compiled SQL but does not execute
- default output includes:
  - concise answer
  - generated semduck request
  - compiled SQL
  - tabular results
- JSON output returns the full typed result payload

Agent workflow:

1. inspect available semantic views
2. inspect the selected or constrained view
3. generate a semduck request
4. call `compile_request`
5. call `query_request` unless `--sql-only`
6. return answer text plus provenance

Deliverable:

- a working ask CLI backed by `pydantic_ai` and the shared semduck tool core

### Phase 4: FastMCP server

Goal:

- expose semduck to external MCP-capable clients without embedding a second ask agent

Scope:

- add `semduck mcp`
- implement a `FastMCP` server over `stdio`
- register shared semduck tools from Phase 1
- expose MCP resources and prompts for host-driven ask workflows

MCP tools:

- `list_semantic_views`
- `describe_semantic_view`
- `compile_request`
- `query_request`
- `check_definition`
- `load_definition`
- `init_registry`

MCP resources:

- registry overview resource
- per-view semantic descriptor resources
- semduck request grammar / usage resource

MCP prompts:

- `ask_semduck_question`
- `choose_semantic_view`
- `debug_failed_request`

Prompt responsibilities:

- tell the host LLM to inspect views first
- instruct it to generate semduck requests rather than SQL
- require `compile_request` before `query_request`
- instruct retry and revision on compile failure
- require final answer provenance that includes the semduck request and SQL

Out of scope:

- no MCP `ask` tool
- no separate server-side ask orchestration hidden behind MCP

Deliverable:

- a FastMCP server that gives generic LLM clients both the semduck capabilities and the guidance
  needed to perform ask workflows themselves

### Phase 5: Refinement and hardening

Goal:

- make the platform stable enough for repeated real usage

Scope:

- improve prompt/resource content based on real ask failures
- add better structured errors and troubleshooting hints
- improve output formatting for larger result sets
- add optional guardrails such as query row limits or result truncation metadata
- document recommended configs for Ollama and OpenAI-compatible local servers

Deliverable:

- a hardened v1 suitable for iterative expansion to more providers or richer workflows later

## Public Interfaces

Additive Python interfaces:

- `list_semantic_views(conn) -> list[str]`
- `describe_semantic_view(conn, view_name) -> ...`
- `ask_question(conn_or_db, question, *, config=None, provider=None, model=None, view=None, execute=True) -> AskResult`

CLI additions:

- `semduck ask`
- `semduck mcp`

Config interface:

- file + env override model/provider config
- initial provider types:
  - `ollama`
  - `openai_compatible`

MCP interface:

- tools for core semduck operations
- resources for semantic context
- prompts for host-driven ask workflows

## Test Plan

### Phase 1 tests

- shared service functions wrap existing semduck behavior correctly
- Pydantic request/response models validate as expected
- `list_semantic_views` and `describe_semantic_view` return stable structured outputs
- error normalization is consistent across compile/query/load failures

### Phase 2 tests

- config file defaults load correctly
- env vars override config defaults
- explicit overrides beat both env and config
- `openai_compatible` provider builds a usable `pydantic_ai` backend
- `ollama` provider builds a usable `pydantic_ai` backend
- unknown provider and missing credentials fail clearly

### Phase 3 tests

- ask agent selects the correct or constrained semantic view
- generated semduck request compiles in the happy path
- `--sql-only` compiles without executing
- default behavior executes and returns answer + provenance
- malformed model outputs or unusable requests fail clearly

### Phase 4 tests

- FastMCP registers the expected tools, resources, and prompts
- MCP tool schemas match the shared Pydantic models
- per-view resources serialize as expected
- MCP prompts contain the intended workflow guidance
- no MCP `ask` tool is registered

### Phase 5 tests

- large result sets are formatted or truncated predictably
- prompt/resource refinements improve known failure cases
- local-hosted provider examples work in documented integration scenarios

## Assumptions And Defaults

- the CLI ask flow uses `pydantic_ai`
- the MCP server uses `FastMCP`
- both front ends share one canonical semduck-owned tool/service layer
- MCP ask behavior is guided by prompts and resources, not a dedicated `ask` tool
- semduck requests remain the authoritative query contract; arbitrary SQL generation is not the
  intended model output
- initial provider support is limited to `ollama` and `openai_compatible`
