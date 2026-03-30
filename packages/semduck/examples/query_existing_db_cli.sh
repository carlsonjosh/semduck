#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
DB_PATH="$ROOT_DIR/examples/dbt_example/jaffle_shop.duckdb"
REQUEST="orders_semantic dimensions customer_name metrics total_revenue"

echo "Database: $DB_PATH"
echo "Request: $REQUEST"
echo
echo "Compiled SQL:"
uv run python -m semduck.cli compile --db "$DB_PATH" --request "$REQUEST"
echo
echo "Query results:"
uv run python -m semduck.cli query --db "$DB_PATH" --request "$REQUEST"
