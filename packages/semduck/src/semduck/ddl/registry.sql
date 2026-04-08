create schema if not exists semantic;

create table if not exists semantic.semantic_views (
    view_name varchar primary key,
    description varchar,
    source_yaml text,
    created_at timestamp default current_timestamp,
    updated_at timestamp default current_timestamp
);

create table if not exists semantic.semantic_view_tables (
    view_name varchar not null,
    table_name varchar not null,
    physical_schema varchar,
    physical_table varchar not null,
    table_alias varchar not null,
    primary_key_columns text,
    description varchar,
    created_at timestamp default current_timestamp,
    updated_at timestamp default current_timestamp,
    primary key (view_name, table_name)
);

create table if not exists semantic.dimensions (
    view_name varchar not null,
    table_name varchar not null,
    dimension_name varchar not null,
    dimension_kind varchar not null,
    expr text not null,
    data_type varchar,
    description varchar,
    created_at timestamp default current_timestamp,
    updated_at timestamp default current_timestamp,
    primary key (view_name, table_name, dimension_name)
);

create table if not exists semantic.facts (
    view_name varchar not null,
    table_name varchar not null,
    fact_name varchar not null,
    expr text not null,
    data_type varchar,
    description varchar,
    created_at timestamp default current_timestamp,
    updated_at timestamp default current_timestamp,
    primary key (view_name, table_name, fact_name)
);

create table if not exists semantic.metrics (
    view_name varchar not null,
    table_name varchar not null,
    metric_name varchar not null,
    expr text not null,
    description varchar,
    created_at timestamp default current_timestamp,
    updated_at timestamp default current_timestamp,
    primary key (view_name, table_name, metric_name)
);

create table if not exists semantic.joins (
    view_name varchar not null,
    join_name varchar not null,
    left_table varchar not null,
    right_table varchar not null,
    join_type varchar not null,
    join_expr text not null,
    description varchar,
    created_at timestamp default current_timestamp,
    updated_at timestamp default current_timestamp,
    primary key (view_name, join_name)
);

create or replace view semantic.v_semantic_views as
select
    view_name,
    description,
    created_at,
    updated_at
from semantic.semantic_views;

create or replace view semantic.v_dimensions as
select
    view_name,
    table_name,
    dimension_name,
    dimension_kind,
    expr,
    data_type
from semantic.dimensions;

create or replace view semantic.v_metrics as
select
    view_name,
    table_name,
    metric_name,
    expr
from semantic.metrics;
