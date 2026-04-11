import json

from semduck import (
    compile_request_sql,
    get_semantic_view,
    load_semantic_ddl,
    load_semantic_spec,
    register_connection,
)
from semduck.errors import SemanticValidationError


VALID_SPEC = {
    "name": "sample",
    "tables": [
        {
            "name": "orders",
            "base_table": {"table": "orders_base"},
            "dimensions": [{"name": "region", "expr": "region"}],
            "metrics": [{"name": "order_count", "expr": "count(order_id)"}],
        }
    ],
}


def test_load_semantic_spec_validate_only(conn):
    result = load_semantic_spec(conn, VALID_SPEC, validate_only=True)
    assert result.ok is True
    assert result.validated_only is True


def test_load_semantic_spec_validate_only_rejects_invalid_spec(conn):
    invalid_spec = {
        "name": "sample",
        "tables": [
            {
                "name": "orders",
                "base_table": {"table": "orders_base"},
                "dimensions": [{"name": "region"}],
            }
        ],
    }

    try:
        load_semantic_spec(conn, invalid_spec, validate_only=True)
    except SemanticValidationError:
        pass
    else:
        raise AssertionError("expected SemanticValidationError")


def test_register_connection_registers_udfs(conn):
    register_connection(conn)
    spec_json = json.dumps(VALID_SPEC).replace("'", "''")

    check_result = conn.sql(
        f"select semduck_check_resolved_spec('{spec_json}') as status"
    ).fetchone()[0]
    assert check_result == "ok check view_name=sample"


def test_register_connection_rejects_invalid_resolved_spec(conn):
    register_connection(conn)
    invalid_spec_json = json.dumps(
        {
            "name": "sample",
            "tables": [
                {
                    "name": "orders",
                    "base_table": {"table": "orders_base"},
                    "dimensions": [{"name": "region"}],
                }
            ],
        }
    ).replace("'", "''")

    try:
        conn.sql(
            f"select semduck_check_resolved_spec('{invalid_spec_json}') as status"
        ).fetchone()[0]
    except Exception as exc:
        assert "missing expr" in str(exc)
    else:
        raise AssertionError("expected invalid resolved spec to fail validation")


def test_compile_request_sql_returns_sql(loaded_conn):
    sql = compile_request_sql(
        loaded_conn, "orders_semantic dimensions region metrics total_revenue"
    )
    assert "select" in sql.lower()
    assert "mart.orders_base" in sql


def test_register_connection_registers_ddl_udfs(conn):
    register_connection(conn)
    ddl_text = """
create semantic view sample as
table mart.orders_base as orders
  dimensions (
    region as region
  )
  metrics (
    count(order_id) as order_count
  );
"""
    ddl_sql = ddl_text.replace("'", "''")
    status = conn.sql(
        f"select semduck_check_ddl('{ddl_sql}') as status"
    ).fetchone()[0]
    assert status == "ok check view_name=sample"


def test_register_connection_registers_ddl_udfs_with_dbt_meta(conn):
    register_connection(conn)
    ddl_text = """
create semantic view sample as
table mart.orders_base as orders
  dimensions (
    region as region
  )
  metrics (
    count(order_id) as order_count
  );
"""
    payload = json.dumps(
        {
            "columns": {
                "region": {
                    "meta": {
                        "ai_context": {
                            "concepts": [
                                {"concept_id": "region", "phrases": ["region"]}
                            ]
                        }
                    }
                }
            }
        }
    ).replace("'", "''")
    ddl_sql = ddl_text.replace("'", "''")
    status = conn.sql(
        "select semduck_check_ddl_with_dbt_meta("
        f"'{ddl_sql}', "
        f"'{payload}'"
        ") as status"
    ).fetchone()[0]
    assert status == "ok check view_name=sample"


def test_load_semantic_ddl_applies_dbt_meta_ai_context_overlay(loaded_conn):
    ddl_text = """
create semantic view sample as
table mart.orders_base as orders
  dimensions (
    region as region
  )
  metrics (
    count(order_id) as order_count
  );
"""
    dbt_metadata = {
        "meta": {
            "ai_context": {
                "concepts": [
                    {
                        "concept_id": "recent",
                        "concept_kind": "modifier",
                        "phrases": ["recent"],
                        "default_window": "30 days",
                        "time_dimension": "region",
                    }
                ]
            }
        },
        "columns": {
            "region": {
                "meta": {
                    "ai_context": {
                        "concepts": [
                            {"concept_id": "region", "phrases": ["region", "regions"]}
                        ]
                    }
                }
            },
            "order_count": {
                "meta": {
                    "ai_context": {
                        "concepts": [
                            {"concept_id": "order_count", "phrases": ["order count", "orders"]}
                        ]
                    }
                }
            },
        },
    }

    load_semantic_ddl(loaded_conn, ddl_text, dbt_metadata=dbt_metadata)
    registry = get_semantic_view(loaded_conn, "sample")
    assert registry.ai_context == dbt_metadata["meta"]["ai_context"]
    orders_table = registry.tables["orders"]
    assert orders_table.dimensions["region"].ai_context == dbt_metadata["columns"]["region"]["meta"]["ai_context"]
    assert orders_table.metrics["order_count"].ai_context == dbt_metadata["columns"]["order_count"]["meta"]["ai_context"]
    concept_count = loaded_conn.execute("select count(*) from semantic.semantic_concepts").fetchone()[0]
    assert concept_count > 0


def test_load_semantic_ddl_rejects_ambiguous_dbt_column_ai_context(conn):
    ddl_text = """
create semantic view sample as
table mart.orders_base as orders
  dimensions (
    region as region
  )

table mart.customer_base as customers
  dimensions (
    region as region
  );
"""
    dbt_metadata = {
        "columns": {
            "region": {
                "meta": {
                    "ai_context": {
                        "concepts": [
                            {"concept_id": "region", "phrases": ["region"]}
                        ]
                    }
                }
            }
        }
    }

    try:
        load_semantic_ddl(conn, ddl_text, validate_only=True, dbt_metadata=dbt_metadata)
    except SemanticValidationError as exc:
        assert "ambiguous across multiple semantic objects" in str(exc)
    else:
        raise AssertionError("expected ambiguous dbt column ai_context to fail")
