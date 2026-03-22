from __future__ import annotations

import argparse
import sys

import duckdb

from semduck.api import compile_request, init_registry, load_semantic_yaml_file
from semduck.errors import SemanticViewError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="semduck")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_cmd = subparsers.add_parser("init")
    init_cmd.add_argument("--db", required=True)

    validate_cmd = subparsers.add_parser("validate-yaml")
    validate_cmd.add_argument("--db", required=True)
    validate_cmd.add_argument("--file", required=True)

    load_cmd = subparsers.add_parser("load-yaml")
    load_cmd.add_argument("--db", required=True)
    load_cmd.add_argument("--file", required=True)
    load_cmd.add_argument("--no-replace", action="store_true")

    compile_cmd = subparsers.add_parser("compile")
    compile_cmd.add_argument("--db", required=True)
    compile_cmd.add_argument("--request", required=True)

    query_cmd = subparsers.add_parser("query")
    query_cmd.add_argument("--db", required=True)
    query_cmd.add_argument("--request", required=True)

    return parser


def _connect(path: str):
    return duckdb.connect(path)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        with _connect(args.db) as conn:
            if args.command == "init":
                init_registry(conn)
                print("ok init")
                return 0

            if args.command == "validate-yaml":
                init_registry(conn)
                result = load_semantic_yaml_file(conn, args.file, validate_only=True)
                print(f"ok validate-yaml view_name={result.view_name}")
                return 0

            if args.command == "load-yaml":
                init_registry(conn)
                result = load_semantic_yaml_file(
                    conn,
                    args.file,
                    replace_existing=not args.no_replace,
                )
                print(f"ok load-yaml view_name={result.view_name}")
                return 0

            if args.command == "compile":
                compiled = compile_request(conn, args.request)
                print(compiled.sql)
                return 0

            if args.command == "query":
                relation = conn.sql(compile_request(conn, args.request).sql)
                print(relation.df().to_string(index=False))
                return 0
    except SemanticViewError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
