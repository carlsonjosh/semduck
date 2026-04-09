from __future__ import annotations

import argparse
import shutil
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import yaml

from semduck import AskExecutionError, ask_question, init_registry, load_semantic_yaml_file


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _default_db_path() -> Path:
    return _repo_root() / "examples" / "ecommerce" / "ecommerce_demo.duckdb"


def _default_config_path() -> Path:
    return _repo_root() / "packages" / "semduck" / "examples" / "ask_ollama_config.yaml"


def _default_eval_set_path() -> Path:
    return Path(__file__).resolve().parent / "eval_set.yaml"


def _default_output_path() -> Path:
    timestamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    return Path(__file__).resolve().parent / "results" / f"ask_results_{timestamp}.yaml"


def _load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _semantic_spec_paths() -> list[Path]:
    base = _repo_root() / "examples" / "ecommerce"
    return [
        base / "orders_semantic.yaml",
        base / "customer_semantic.yaml",
        base / "product_sales_semantic.yaml",
    ]


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(val) for key, val in value.items()}
    return str(value)


def _ensure_registry(db_path: Path) -> None:
    import duckdb

    conn = duckdb.connect(str(db_path))
    try:
        init_registry(conn)
        for spec_path in _semantic_spec_paths():
            load_semantic_yaml_file(conn, str(spec_path), replace_existing=True)
    finally:
        conn.close()


def _select_cases(
    eval_cases: list[dict[str, Any]],
    *,
    case_ids: set[str] | None,
    include_unsupported: bool,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for case in eval_cases:
        if case_ids and case["id"] not in case_ids:
            continue
        if not include_unsupported and not case.get("supported", True):
            continue
        selected.append(case)
    return selected


def _run_case(
    *,
    db_path: Path,
    config_path: Path,
    case: dict[str, Any],
    row_limit: int | None,
    llm_log_dir: Path | None,
    enforce_expected_view: bool,
) -> dict[str, Any]:
    question = case["question"]
    expected_view = case.get("expected_view")
    requested_view = expected_view if enforce_expected_view and expected_view else None

    record: dict[str, Any] = {
        "id": case["id"],
        "title": case["title"],
        "supported": case.get("supported", True),
        "question": question,
        "question_type": case.get("question_type"),
        "expected": {
            "view": expected_view,
            "grain": case.get("expected_grain"),
            "dimensions": case.get("expected_dimensions", []),
            "metrics": case.get("expected_metrics", []),
            "filters": case.get("expected_filters", []),
        },
        "run": {
            "requested_view": requested_view,
            "row_limit": row_limit,
        },
    }

    try:
        result = ask_question(
            str(db_path),
            question,
            config=str(config_path),
            view=requested_view,
            row_limit=row_limit,
            llm_log_dir=str(llm_log_dir) if llm_log_dir else None,
            include_sql=True,
            include_table=True,
            include_summary=True,
        )
        record["status"] = "ok"
        record["observed"] = {
            "chosen_view": result.chosen_view,
            "semantic_request": result.semantic_request,
            "sql": result.sql,
            "answer_text": result.answer_text,
            "columns": _json_safe(result.columns),
            "rows": _json_safe(result.rows),
            "executed": result.executed,
            "provider": result.provider,
            "model": result.model,
            "summary_provider": result.summary_provider,
            "summary_model": result.summary_model,
            "total_row_count": result.total_row_count,
            "omitted_row_count": result.omitted_row_count,
            "requested_outputs": _json_safe(result.requested_outputs),
        }
    except AskExecutionError as exc:
        record["status"] = "error"
        record["error"] = {
            "type": "AskExecutionError",
            "code": exc.code,
            "message": exc.message,
            "failure_stage": exc.failure_stage,
            "troubleshooting": _json_safe(exc.troubleshooting),
        }
    except Exception as exc:  # pragma: no cover - defensive wrapper for runtime failures
        record["status"] = "error"
        record["error"] = {
            "type": type(exc).__name__,
            "message": str(exc),
        }

    return record


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run semduck ask across the ecommerce eval set and store results as YAML.",
    )
    parser.add_argument(
        "--eval-set",
        type=Path,
        default=_default_eval_set_path(),
        help="Path to the machine-readable eval set YAML.",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=_default_db_path(),
        help="Path to the source ecommerce DuckDB database.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=_default_config_path(),
        help="Path to the semduck ask LLM config file.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=_default_output_path(),
        help="Path to the YAML output file to write.",
    )
    parser.add_argument(
        "--row-limit",
        type=int,
        default=20,
        help="Row limit passed to semduck ask.",
    )
    parser.add_argument(
        "--case",
        action="append",
        dest="cases",
        help="Specific eval case ID to run. Repeat to run multiple cases.",
    )
    parser.add_argument(
        "--skip-unsupported",
        action="store_true",
        help="Skip unsupported negative-test cases.",
    )
    parser.add_argument(
        "--enforce-expected-view",
        action="store_true",
        help="Pass the expected view to ask_question(...) for supported cases.",
    )
    parser.add_argument(
        "--llm-log-dir",
        type=Path,
        help="Optional directory for semduck ask LLM traces.",
    )
    parser.add_argument(
        "--list-cases",
        action="store_true",
        help="Print available eval case IDs and exit.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    eval_set = _load_yaml(args.eval_set)
    eval_cases = eval_set["cases"]

    if args.list_cases:
        for case in eval_cases:
            print(f"{case['id']}: {case['title']}")
        return

    case_ids = set(args.cases or [])
    selected_cases = _select_cases(
        eval_cases,
        case_ids=case_ids or None,
        include_unsupported=not args.skip_unsupported,
    )
    if not selected_cases:
        raise SystemExit("No eval cases selected.")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.llm_log_dir:
        args.llm_log_dir.mkdir(parents=True, exist_ok=True)

    with TemporaryDirectory(prefix="semduck-ecommerce-eval-") as tmp_dir:
        working_db = Path(tmp_dir) / args.db.name
        shutil.copy2(args.db, working_db)
        _ensure_registry(working_db)

        results = [
            _run_case(
                db_path=working_db,
                config_path=args.config,
                case=case,
                row_limit=args.row_limit,
                llm_log_dir=args.llm_log_dir,
                enforce_expected_view=args.enforce_expected_view,
            )
            for case in selected_cases
        ]

    output = {
        "version": 1,
        "dataset": eval_set.get("dataset", "ecommerce"),
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "source_eval_set": str(args.eval_set),
        "source_db": str(args.db),
        "config": str(args.config),
        "row_limit": args.row_limit,
        "case_count": len(results),
        "cases": _json_safe(results),
    }
    args.output.write_text(
        yaml.safe_dump(output, sort_keys=False, allow_unicode=False),
        encoding="utf-8",
    )
    print(f"Wrote ask eval results to {args.output}")


if __name__ == "__main__":
    main()
