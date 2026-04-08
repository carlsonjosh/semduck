from __future__ import annotations

from pathlib import Path

from semduck import ask_question, format_ask_result_text


def main() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    db_path = repo_root / "examples" / "dbt_example" / "jaffle_shop.duckdb"
    config_path = repo_root / "packages" / "semduck" / "examples" / "ask_ollama_config.yaml"
    question = "What is total revenue by customer name?"

    result = ask_question(
        str(db_path),
        question,
        config=str(config_path),
        include_sql=True,
        include_table=True,
        include_summary=True,
    )

    print(f"Database: {db_path}")
    print(f"Config: {config_path}")
    print(f"Question: {question}")
    print()
    print(format_ask_result_text(result))


if __name__ == "__main__":
    main()
