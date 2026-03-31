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
    def fake_ask_question(*args, **kwargs):
        kwargs["progress"]("resolving ask configuration")
        kwargs["progress"]("finished")
        return SimpleNamespace(
            answer_text="US revenue is 250.0",
            chosen_view="orders_semantic",
            provider="ollama",
            model="llama3.1",
            semantic_request="orders_semantic dimensions region metrics total_revenue where region = 'US'",
            sql="select 1",
            executed=True,
            columns=["region", "total_revenue"],
            rows=[["US", 250.0]],
        )

    monkeypatch.setattr(
        "semduck.cli.ask_question",
        fake_ask_question,
    )

    code = main(["ask", "--db", ":memory:", "--question", "What is US revenue?"])

    captured = capsys.readouterr()
    assert code == 0
    assert "Answer: US revenue is 250.0" in captured.out
    assert "status: resolving ask configuration" in captured.err
    assert "status: finished" in captured.err


def test_cli_ask_prints_json_output(monkeypatch, capsys):
    def fake_ask_question(*args, **kwargs):
        kwargs["progress"]("resolving ask configuration")
        kwargs["progress"]("finished")
        return SimpleNamespace(
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
        )

    monkeypatch.setattr(
        "semduck.cli.ask_question",
        fake_ask_question,
    )

    code = main(["ask", "--db", ":memory:", "--question", "What is US revenue?", "--output-format", "json"])

    captured = capsys.readouterr()
    assert code == 0
    assert '"answer_text": "US revenue is 250.0"' in captured.out
    assert "status: resolving ask configuration" in captured.err
    assert "status: finished" in captured.err


def test_cli_ask_passes_llm_logging_options(monkeypatch, capsys):
    captured_kwargs = {}

    def fake_ask_question(*args, **kwargs):
        captured_kwargs.update(kwargs)
        kwargs["progress"]("resolving ask configuration")
        kwargs["progress"]("finished")
        return SimpleNamespace(
            answer_text="US revenue is 250.0",
            chosen_view="orders_semantic",
            provider="ollama",
            model="llama3.1",
            semantic_request="orders_semantic dimensions region metrics total_revenue where region = 'US'",
            sql="select 1",
            executed=False,
            columns=[],
            rows=[],
        )

    monkeypatch.setattr(
        "semduck.cli.ask_question",
        fake_ask_question,
    )

    code = main(
        [
            "ask",
            "--db",
            ":memory:",
            "--question",
            "What is US revenue?",
            "--llm-log-dir",
            "trace-logs",
            "--no-llm-log",
        ]
    )

    assert code == 0
    assert captured_kwargs["llm_log_dir"] == "trace-logs"
    assert captured_kwargs["disable_llm_log"] is True
    assert captured_kwargs["progress"] is not None

    captured = capsys.readouterr()
    assert "status: resolving ask configuration" in captured.err
    assert "status: finished" in captured.err


def test_cli_status_reporter_prints_expected_format(capsys):
    from semduck.cli import _print_ask_status

    _print_ask_status("planning semantic request")

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "status: planning semantic request\n"
