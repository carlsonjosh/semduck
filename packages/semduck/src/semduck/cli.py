from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb

from semduck.agent import ask_question, format_ask_result_json, format_ask_result_text
from semduck.api import compile_request, init_registry, load_semantic_ddl_file, load_semantic_yaml_file
from semduck.agent.services import SemduckServiceError
from semduck.errors import SemanticViewError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="semduck")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_cmd = subparsers.add_parser("init")
    init_cmd.add_argument("--db", required=True)

    check_cmd = subparsers.add_parser("check")
    check_cmd.add_argument("--db", required=True)
    check_cmd.add_argument("--file", required=True)
    check_cmd.add_argument("--format", choices=["auto", "yaml", "ddl"], default="auto")

    load_cmd = subparsers.add_parser("load")
    load_cmd.add_argument("--db", required=True)
    load_cmd.add_argument("--file", required=True)
    load_cmd.add_argument("--no-replace", action="store_true")
    load_cmd.add_argument("--format", choices=["auto", "yaml", "ddl"], default="auto")

    compile_cmd = subparsers.add_parser("compile")
    compile_cmd.add_argument("--db", required=True)
    compile_cmd.add_argument("--request", required=True)

    query_cmd = subparsers.add_parser("query")
    query_cmd.add_argument("--db", required=True)
    query_cmd.add_argument("--request", required=True)

    ask_cmd = subparsers.add_parser("ask")
    ask_cmd.add_argument("--db", required=True)
    ask_cmd.add_argument("--question", required=True)
    ask_cmd.add_argument("--config")
    ask_cmd.add_argument("--provider")
    ask_cmd.add_argument("--model")
    ask_cmd.add_argument("--view")
    ask_cmd.add_argument("--sql-only", action="store_true")
    ask_cmd.add_argument("--output-format", choices=["text", "json"], default="text")

    mcp_cmd = subparsers.add_parser("mcp")
    mcp_cmd.add_argument("--db", required=True)
    mcp_cmd.add_argument("--config")
    mcp_cmd.add_argument("--provider")
    mcp_cmd.add_argument("--model")

    return parser


def _connect(path: str):
    return duckdb.connect(path)


def _infer_definition_format(path: str, explicit_format: str) -> str:
    if explicit_format != "auto":
        return explicit_format

    suffix = Path(path).suffix.lower()
    if suffix in {".yaml", ".yml"}:
        return "yaml"
    if suffix in {".sql", ".ddl"}:
        return "ddl"

    text = Path(path).read_text(encoding="utf-8")
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    if first_line.lower().startswith("create semantic view"):
        return "ddl"
    return "yaml"


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "mcp":
        from semduck.mcp import run_mcp_server

        run_mcp_server(
            db_path=args.db,
            config_path=args.config,
            provider=args.provider,
            model=args.model,
        )
        return 0

    try:
        with _connect(args.db) as conn:
            if args.command == "init":
                init_registry(conn)
                print("ok init")
                return 0

            if args.command == "check":
                init_registry(conn)
                inferred_format = _infer_definition_format(args.file, args.format)
                loader = load_semantic_ddl_file if inferred_format == "ddl" else load_semantic_yaml_file
                result = loader(conn, args.file, validate_only=True)
                print(f"ok check view_name={result.view_name}")
                return 0

            if args.command == "load":
                init_registry(conn)
                inferred_format = _infer_definition_format(args.file, args.format)
                loader = load_semantic_ddl_file if inferred_format == "ddl" else load_semantic_yaml_file
                result = loader(
                    conn,
                    args.file,
                    replace_existing=not args.no_replace,
                )
                print(f"ok load view_name={result.view_name}")
                return 0

            if args.command == "compile":
                compiled = compile_request(conn, args.request)
                print(compiled.sql)
                return 0

            if args.command == "query":
                relation = conn.sql(compile_request(conn, args.request).sql)
                columns = [column[0] for column in relation.description]
                rows = relation.fetchall()
                print(" | ".join(columns))
                for row in rows:
                    print(" | ".join("" if value is None else str(value) for value in row))
                return 0
            if args.command == "ask":
                result = ask_question(
                    conn,
                    args.question,
                    config=args.config,
                    provider=args.provider,
                    model=args.model,
                    view=args.view,
                    execute=not args.sql_only,
                )
                if args.output_format == "json":
                    print(format_ask_result_json(result))
                else:
                    print(format_ask_result_text(result))
                return 0
    except SemanticViewError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except (SemduckServiceError, ValueError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
