from pathlib import Path

from semduck.cli import _infer_definition_format


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
