from __future__ import annotations

import re
from typing import Any

from semduck.authoring.validators import validate_semantic_spec
from semduck.errors import SemanticValidationError


_CREATE_RE = re.compile(r"^create\s+semantic\s+view\s+([A-Za-z_][A-Za-z0-9_]*)\s+as$", re.IGNORECASE)
_TABLE_RE = re.compile(r"^table\s+([A-Za-z_][A-Za-z0-9_]*)\s+as\s+(.+)$", re.IGNORECASE)
_JOIN_RE = re.compile(r"^join\s+([A-Za-z_][A-Za-z0-9_]*)\s*:\s*$", re.IGNORECASE)
_PRIMARY_KEY_RE = re.compile(r"^primary\s+key\s*\((.*)\)$", re.IGNORECASE)
_SECTION_RE = re.compile(
    r"^(dimensions|time_dimensions|facts|metrics)\s*\((.*)\)$",
    re.IGNORECASE | re.DOTALL,
)
_DESCRIPTION_RE = re.compile(r"^description\s+'((?:''|[^'])*)'$", re.IGNORECASE | re.DOTALL)
_JOIN_PROP_RE = re.compile(r"^(left_table|right_table|join_type|on)\s+(.+)$", re.IGNORECASE | re.DOTALL)
_FIELD_RE = re.compile(
    r"^([A-Za-z_][A-Za-z0-9_]*)\s+as\s+(.+?)(?:\s+type\s+([A-Za-z_][A-Za-z0-9_]*|\"[^\"]+\"))?(?:\s+description\s+'((?:''|[^'])*)')?$",
    re.IGNORECASE | re.DOTALL,
)


def load_ddl_spec(ddl_text: str) -> dict[str, Any]:
    spec = parse_semantic_ddl(ddl_text)
    validate_semantic_spec(spec)
    return spec


def parse_semantic_ddl(ddl_text: str) -> dict[str, Any]:
    lines = _normalized_lines(ddl_text)
    if not lines:
        raise SemanticValidationError("semantic DDL must not be empty")

    create_match = _CREATE_RE.match(lines[0])
    if create_match is None:
        raise SemanticValidationError("semantic DDL must start with 'create semantic view <name> as'")

    spec: dict[str, Any] = {"name": create_match.group(1), "tables": [], "joins": []}
    current_table: dict[str, Any] | None = None
    current_join: dict[str, Any] | None = None

    for line in lines[1:]:
        table_match = _TABLE_RE.match(line)
        if table_match is not None:
            current_join = None
            current_table = {
                "name": table_match.group(1),
                "base_table": _parse_relation_name(table_match.group(2)),
            }
            spec["tables"].append(current_table)
            continue

        join_match = _JOIN_RE.match(line)
        if join_match is not None:
            current_table = None
            current_join = {"name": join_match.group(1)}
            spec["joins"].append(current_join)
            continue

        if current_table is not None:
            _apply_table_clause(current_table, line)
            continue

        if current_join is not None:
            _apply_join_clause(current_join, line)
            continue

        raise SemanticValidationError(f"Unexpected semantic DDL line: {line}")

    return spec


def _normalized_lines(ddl_text: str) -> list[str]:
    text = ddl_text.strip()
    if text.endswith(";"):
        text = text[:-1]

    raw_lines = []
    for line in text.splitlines():
        candidate = line.strip()
        if not candidate or candidate.startswith("--"):
            continue
        raw_lines.append(candidate)

    lines: list[str] = []
    index = 0
    while index < len(raw_lines):
        line = raw_lines[index]
        if re.match(r"^(dimensions|time_dimensions|facts|metrics)\s*\($", line, re.IGNORECASE):
            block_lines = [line]
            depth = line.count("(") - line.count(")")
            index += 1
            while index < len(raw_lines) and depth > 0:
                block_lines.append(raw_lines[index])
                depth += raw_lines[index].count("(") - raw_lines[index].count(")")
                index += 1
            if depth != 0:
                raise SemanticValidationError(f"Unclosed semantic DDL section: {block_lines[0]}")
            lines.append(" ".join(block_lines))
            continue

        lines.append(line)
        index += 1

    return lines


def _parse_relation_name(raw: str) -> dict[str, Any]:
    relation = raw.strip()
    parts = _split_qualified_name(relation)
    if len(parts) == 2:
        return {"schema": parts[0], "table": parts[1]}
    if len(parts) == 3:
        return {"database": parts[0], "schema": parts[1], "table": parts[2]}
    raise SemanticValidationError("table relation must be schema.table or database.schema.table")


def _split_qualified_name(value: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    in_quotes = False
    for ch in value:
        if ch == '"':
            in_quotes = not in_quotes
            continue
        if ch == "." and not in_quotes:
            parts.append("".join(current).strip())
            current = []
            continue
        current.append(ch)
    if in_quotes:
        raise SemanticValidationError(f"Unclosed quoted identifier in relation: {value}")
    parts.append("".join(current).strip())
    return [part for part in parts if part]


def _apply_table_clause(table_spec: dict[str, Any], line: str) -> None:
    primary_key_match = _PRIMARY_KEY_RE.match(line)
    if primary_key_match is not None:
        columns = [col.strip() for col in primary_key_match.group(1).split(",") if col.strip()]
        table_spec["primary_key"] = {"columns": columns}
        return

    description_match = _DESCRIPTION_RE.match(line)
    if description_match is not None:
        table_spec["description"] = _unescape_string(description_match.group(1))
        return

    section_match = _SECTION_RE.match(line)
    if section_match is None:
        raise SemanticValidationError(f"Unknown table clause: {line}")

    section = section_match.group(1).lower()
    body = section_match.group(2).strip()
    if section == "metrics":
        table_spec[section] = [_parse_metric_def(item) for item in _split_top_level_commas(body)]
    else:
        table_spec[section] = [_parse_field_def(item) for item in _split_top_level_commas(body)]


def _apply_join_clause(join_spec: dict[str, Any], line: str) -> None:
    description_match = _DESCRIPTION_RE.match(line)
    if description_match is not None:
        join_spec["description"] = _unescape_string(description_match.group(1))
        return

    join_prop_match = _JOIN_PROP_RE.match(line)
    if join_prop_match is None:
        raise SemanticValidationError(f"Unknown join clause: {line}")

    key = join_prop_match.group(1).lower()
    value = join_prop_match.group(2).strip()
    if key == "on":
        join_spec["join_expr"] = value
    else:
        join_spec[key] = value


def _split_top_level_commas(body: str) -> list[str]:
    items: list[str] = []
    current: list[str] = []
    depth = 0
    in_quotes = False

    for ch in body:
        if ch == "'" and (not current or current[-1] != "\\"):
            in_quotes = not in_quotes
        elif ch == "(" and not in_quotes:
            depth += 1
        elif ch == ")" and not in_quotes:
            depth -= 1
        elif ch == "," and depth == 0 and not in_quotes:
            item = "".join(current).strip()
            if item:
                items.append(item)
            current = []
            continue
        current.append(ch)

    item = "".join(current).strip()
    if item:
        items.append(item)
    return items


def _parse_field_def(item: str) -> dict[str, Any]:
    match = _FIELD_RE.match(item)
    if match is None:
        raise SemanticValidationError(f"Invalid semantic field definition: {item}")
    obj: dict[str, Any] = {
        "name": match.group(1),
        "expr": match.group(2).strip(),
    }
    if match.group(3):
        obj["data_type"] = match.group(3).strip('"')
    if match.group(4):
        obj["description"] = _unescape_string(match.group(4))
    return obj


def _parse_metric_def(item: str) -> dict[str, Any]:
    name, remainder = _split_once(item, " as ")
    metric_type, expr, tail = _parse_metric_call(remainder)
    obj: dict[str, Any] = {
        "name": name.strip(),
        "metric_type": metric_type,
        "expr": expr,
    }
    tail = tail.strip()
    if tail:
        default_match = re.search(r"\bdefault_agg\s+([A-Za-z_][A-Za-z0-9_]*)", tail, re.IGNORECASE)
        if default_match:
            obj["default_agg"] = default_match.group(1)
        description_match = re.search(r"\bdescription\s+'((?:''|[^'])*)'$", tail, re.IGNORECASE)
        if description_match:
            obj["description"] = _unescape_string(description_match.group(1))
    return obj


def _parse_metric_call(remainder: str) -> tuple[str, str, str]:
    remainder = remainder.strip()
    open_paren = remainder.find("(")
    if open_paren == -1:
        raise SemanticValidationError(f"Metric definition must use <metric_type>(<expr>): {remainder}")
    metric_type = remainder[:open_paren].strip()
    depth = 0
    in_quotes = False
    for index in range(open_paren, len(remainder)):
        ch = remainder[index]
        if ch == "'" and (index == 0 or remainder[index - 1] != "\\"):
            in_quotes = not in_quotes
        elif ch == "(" and not in_quotes:
            depth += 1
        elif ch == ")" and not in_quotes:
            depth -= 1
            if depth == 0:
                expr = remainder[open_paren + 1 : index].strip()
                tail = remainder[index + 1 :]
                return metric_type, expr, tail
    raise SemanticValidationError(f"Unclosed metric expression: {remainder}")


def _split_once(value: str, separator: str) -> tuple[str, str]:
    parts = value.split(separator, 1)
    if len(parts) != 2:
        raise SemanticValidationError(f"Expected '{separator.strip()}' in definition: {value}")
    return parts[0], parts[1]


def _unescape_string(value: str) -> str:
    return value.replace("''", "'")
