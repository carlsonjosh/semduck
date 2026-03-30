#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
DB_PATH="$ROOT_DIR/examples/dbt_example/jaffle_shop.duckdb"
CONFIG_PATH="$ROOT_DIR/packages/semduck/examples/ask_ollama_config.yaml"
QUESTION="${1:-What is total revenue by customer name?}"

echo "Database: $DB_PATH"
echo "Config: $CONFIG_PATH"
echo "Question: $QUESTION"
echo
echo "semduck ask --sql-only:"
uv run python -m semduck.cli ask \
  --db "$DB_PATH" \
  --config "$CONFIG_PATH" \
  --question "$QUESTION" \
  --sql-only
echo
echo "semduck ask:"
uv run python -m semduck.cli ask \
  --db "$DB_PATH" \
  --config "$CONFIG_PATH" \
  --question "$QUESTION"
