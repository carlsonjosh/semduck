#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
DB_PATH="$ROOT_DIR/examples/dbt_example/jaffle_shop.duckdb"
CONFIG_PATH="${1:-}"

if [[ -n "$CONFIG_PATH" ]]; then
  exec uv run python -m semduck.cli mcp \
    --db "$DB_PATH" \
    --config "$CONFIG_PATH"
fi

exec uv run python -m semduck.cli mcp \
  --db "$DB_PATH"
