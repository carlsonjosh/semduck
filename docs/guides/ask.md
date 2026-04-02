# Ask

`semduck ask` adds a natural-language analytics workflow on top of the same registry and compiler used by the CLI and Python API.

## What It Does

Given a question like:

```text
What is total revenue by customer name?
```

Semduck will:

1. inspect the available semantic views
2. build a semantic request
3. compile that request
4. execute the compiled SQL
5. optionally summarize the result

## Provider Configuration

The repository includes example configs for:

- Ollama: `packages/semduck/examples/ask_ollama_config.yaml`
- OpenAI-compatible endpoints: `packages/semduck/examples/ask_openai_compatible_config.yaml`

Example:

```bash
semduck ask \
  --db examples/dbt_example/jaffle_shop.duckdb \
  --config packages/semduck/examples/ask_ollama_config.yaml \
  --question "What is total revenue by customer name?" \
  --sql --table --summary
```

## Planner And Summary Models

The config supports separate task-specific models:

- `llm.tasks.ask_plan`
- `llm.tasks.ask_summary`

That lets you use a tool-capable model for planning and a cheaper or smaller model for summarization.

## Logging

Set logging in either place:

- `llm.log_dir` in the config file
- `--llm-log-dir` on the command line

Use `--no-llm-log` to disable logging even when the config specifies a directory.

## Output Modes

`ask` can will emit different formats depending on flags provided:

- a text table `--table` (default)
- SQL `--sql`
- CSV `--csv`
- a natural-language summary `--summary`
- JSON output via `--output-format json` (includes all formats)

Stage updates are written to `stderr` so final output on `stdout` can remain machine-readable.

## When To Use It

Use `ask` when a human is starting from a business question. Use `compile` or `query` directly when you already know the semantic request you want to run.
