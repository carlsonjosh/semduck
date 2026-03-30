from __future__ import annotations

from semduck.agent import (
    CheckDefinitionArgs,
    CompileRequestArgs,
    DescribeSemanticViewArgs,
    ListSemanticViewsArgs,
    LoadDefinitionArgs,
    QueryRequestArgs,
    SemduckServiceError,
    check_definition_service,
    compile_request_service,
    describe_semantic_view_service,
    list_semantic_views_service,
    load_definition_service,
    query_request_service,
)


def test_list_semantic_views_service_returns_sorted_names(loaded_conn):
    result = list_semantic_views_service(loaded_conn, ListSemanticViewsArgs())
    assert result.view_names == ["orders_semantic"]


def test_describe_semantic_view_service_returns_compact_descriptor(loaded_conn):
    result = describe_semantic_view_service(
        loaded_conn,
        DescribeSemanticViewArgs(view_name="orders_semantic"),
    )

    assert result.view_name == "orders_semantic"
    assert [table.name for table in result.tables] == ["customers", "orders"]
    orders_table = next(table for table in result.tables if table.name == "orders")
    assert [obj.name for obj in orders_table.dimensions] == ["order_date", "region"]
    assert [obj.object_type for obj in orders_table.dimensions] == ["time_dimension", "dimension"]
    assert [obj.name for obj in orders_table.facts] == ["revenue"]
    assert [obj.name for obj in orders_table.metrics] == ["order_count", "total_revenue"]
    assert result.joins[0].left_table == "orders"


def test_compile_request_service_returns_sql(loaded_conn):
    result = compile_request_service(
        loaded_conn,
        CompileRequestArgs(request="orders_semantic dimensions region metrics total_revenue"),
    )

    assert result.semantic_view_ref == "orders_semantic"
    assert "sum" in result.sql.lower()


def test_query_request_service_returns_rows(loaded_conn):
    result = query_request_service(
        loaded_conn,
        QueryRequestArgs(request="orders_semantic dimensions region metrics total_revenue"),
    )

    assert result.columns == ["region", "total_revenue"]
    assert result.rows == [["CA", 200.0], ["US", 250.0]]


def test_check_definition_service_inferrs_yaml_format(conn, orders_yaml_path):
    result = check_definition_service(conn, CheckDefinitionArgs(file=str(orders_yaml_path)))

    assert result.view_name == "orders_semantic"
    assert result.validated_only is True
    assert result.format == "yaml"


def test_load_definition_service_loads_from_ddl(conn, tmp_path):
    ddl_path = tmp_path / "orders_definition.sql"
    ddl_path.write_text(
        """
        create semantic view sample as
        table orders as main.orders
          dimensions (
            region as region
          )
          metrics (
            order_count as count(order_id)
          );
        """,
        encoding="utf-8",
    )

    result = load_definition_service(conn, LoadDefinitionArgs(file=str(ddl_path)))

    assert result.view_name == "sample"
    assert result.format == "ddl"


def test_describe_semantic_view_service_normalizes_errors(conn):
    try:
        describe_semantic_view_service(conn, DescribeSemanticViewArgs(view_name="missing_view"))
    except SemduckServiceError as exc:
        assert exc.detail.code == "registry"
        assert "missing_view" in exc.detail.message
    else:
        raise AssertionError("Expected SemduckServiceError")
