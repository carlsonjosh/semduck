from __future__ import annotations

from importlib.resources import files
from typing import Any


def init_registry_schema(conn: Any) -> None:
    ddl_path = files("semduck.ddl").joinpath("registry.sql")
    conn.execute(ddl_path.read_text(encoding="utf-8"))
    _migrate_metrics_schema(conn)


def _migrate_metrics_schema(conn: Any) -> None:
    columns = [
        row[1]
        for row in conn.execute("pragma table_info('semantic.metrics')").fetchall()
    ]
    if "metric_type" not in columns and "default_agg" not in columns:
        return

    conn.execute("drop view if exists semantic.v_metrics")
    conn.execute("alter table semantic.metrics rename to metrics_legacy")
    conn.execute(
        """
        create table semantic.metrics (
            view_name varchar not null,
            table_name varchar not null,
            metric_name varchar not null,
            expr text not null,
            description varchar,
            created_at timestamp default current_timestamp,
            updated_at timestamp default current_timestamp,
            primary key (view_name, table_name, metric_name)
        )
        """
    )
    conn.execute(
        """
        insert into semantic.metrics (
            view_name, table_name, metric_name, expr, description, created_at, updated_at
        )
        select
            view_name,
            table_name,
            metric_name,
            case
                when metric_type = 'sum' then 'sum(' || expr || ')'
                when metric_type = 'count' and expr = '*' then 'count(*)'
                when metric_type = 'count' then 'count(' || expr || ')'
                when metric_type = 'count_distinct' then 'count(distinct ' || expr || ')'
                when metric_type = 'avg' then 'avg(' || expr || ')'
                else expr
            end,
            description,
            created_at,
            updated_at
        from semantic.metrics_legacy
        """
    )
    conn.execute("drop table semantic.metrics_legacy")
    conn.execute(
        """
        create or replace view semantic.v_metrics as
        select
            view_name,
            table_name,
            metric_name,
            expr
        from semantic.metrics
        """
    )
