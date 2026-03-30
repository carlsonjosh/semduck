from pathlib import Path
from types import SimpleNamespace

from semduck.cli import _infer_definition_format, main


def test_infer_definition_format_from_yaml_extension(tmp_path):
    path = tmp_path / "orders_definition.yml"
    path.write_text("name: sample\n", encoding="utf-8")
    assert _infer_definition_format(str(path), "auto") == "yaml"


def test_infer_definition_format_from_sql_extension(tmp_path):
    path = tmp_path / "orders_definition.sql"
    path.write_text("create semantic view sample as\n", encoding="utf-8")
    assert _infer_definition_format(str(path), "auto") == "ddl"


def test_infer_definition_format_from_content(tmp_path):
    path = tmp_path / "orders_definition.txt"
    path.write_text("\ncreate semantic view sample as\n", encoding="utf-8")
    assert _infer_definition_format(str(path), "auto") == "ddl"


def test_infer_definition_format_honors_explicit_override(tmp_path):
    path = tmp_path / "orders_definition.sql"
    path.write_text("create semantic view sample as\n", encoding="utf-8")
    assert _infer_definition_format(str(path), "yaml") == "yaml"


def test_cli_ask_prints_text_output(monkeypatch, capsys):
    monkeypatch.setattr(
        "semduck.cli.ask_question",
        lambda *args, **kwargs: SimpleNamespace(
            answer_text="US revenue is 250.0",
            chosen_view="orders_semantic",
            provider="ollama",
            model="llama3.1",
            semantic_request="orders_semantic dimensions region metrics total_revenue where region = 'US'",
            sql="select 1",
            executed=True,
            columns=["region", "total_revenue"],
            rows=[["US", 250.0]],
        ),
    )

    code = main(["ask", "--db", ":memory:", "--question", "What is US revenue?"])

    captured = capsys.readouterr()
    assert code == 0
    assert "Answer: US revenue is 250.0" in captured.out


def test_cli_ask_prints_json_output(monkeypatch, capsys):
    monkeypatch.setattr(
        "semduck.cli.ask_question",
        lambda *args, **kwargs: SimpleNamespace(
            model_dump=lambda: {
                "answer_text": "US revenue is 250.0",
                "chosen_view": "orders_semantic",
                "provider": "ollama",
                "model": "llama3.1",
                "semantic_request": "orders_semantic dimensions region metrics total_revenue where region = 'US'",
                "sql": "select 1",
                "executed": False,
                "columns": [],
                "rows": [],
            }
        ),
    )

    code = main(["ask", "--db", ":memory:", "--question", "What is US revenue?", "--output-format", "json"])

    captured = capsys.readouterr()
    assert code == 0
    assert '"answer_text": "US revenue is 250.0"' in captured.out
