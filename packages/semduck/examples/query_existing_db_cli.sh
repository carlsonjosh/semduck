#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
DB_PATH="$ROOT_DIR/examples/dbt_example/jaffle_shop.duckdb"
REQUEST="orders dimensions customer_name metrics total_revenue"

cat <<'EOF'
Note: this example queries the checked-in DuckDB file directly.
Semduck processes must follow DuckDB's concurrency rules:
https://duckdb.org/docs/current/connect/concurrency
If another DuckDB process already has that file open in a conflicting mode, close it first or copy the database to a temporary path.

EOF

echo "Database: $DB_PATH"
echo "Request: $REQUEST"
echo
echo "Compiled SQL:"
uv run python -m semduck.cli compile --db "$DB_PATH" --request "$REQUEST"
echo
echo "Query results:"
uv run python -m semduck.cli query --db "$DB_PATH" --request "$REQUEST"
