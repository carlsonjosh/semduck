from __future__ import annotations

import json
import re
from typing import Any

from semduck.authoring.validators import validate_semantic_spec
from semduck.errors import SemanticValidationError


_CREATE_RE = re.compile(r"^create\s+semantic\s+view\s+([A-Za-z_][A-Za-z0-9_]*)\s+as$", re.IGNORECASE)
_TABLE_RE = re.compile(r"^table\s+(.+)\s+as\s+([A-Za-z_][A-Za-z0-9_]*)$", re.IGNORECASE)
_JOIN_RE = re.compile(r"^join\s+([A-Za-z_][A-Za-z0-9_]*)\s*:\s*$", re.IGNORECASE)
_PRIMARY_KEY_RE = re.compile(r"^primary\s+key\s*\((.*)\)$", re.IGNORECASE)
_SECTION_RE = re.compile(
    r"^(dimensions|time_dimensions|facts|metrics)\s*\((.*)\)$",
    re.IGNORECASE | re.DOTALL,
)
_DESCRIPTION_RE = re.compile(r"^description\s+'((?:''|[^'])*)'$", re.IGNORECASE | re.DOTALL)
_AI_CONTEXT_RE = re.compile(r"^ai_context\s+'((?:''|[^'])*)'$", re.IGNORECASE | re.DOTALL)
_AI_CONTEXT_BLOCK_RE = re.compile(r"^ai_context\s*\((.*)\)$", re.IGNORECASE | re.DOTALL)
_JOIN_PROP_RE = re.compile(r"^(left_table|right_table|join_type|on)\s+(.+)$", re.IGNORECASE | re.DOTALL)
_NAME_AND_TAIL_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)(.*)$", re.DOTALL)
_IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


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
                "name": table_match.group(2),
                "base_table": _parse_relation_name(table_match.group(1)),
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

        description_match = _DESCRIPTION_RE.match(line)
        if description_match is not None:
            spec["description"] = _unescape_string(description_match.group(1))
            continue

        ai_context_value = _parse_ai_context_clause(line)
        if ai_context_value is not None:
            if "ai_context" in spec:
                raise SemanticValidationError("semantic view ai_context must be defined only once")
            spec["ai_context"] = ai_context_value
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
        if re.match(r"^(dimensions|time_dimensions|facts|metrics|ai_context)\s*\($", line, re.IGNORECASE):
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

    ai_context_value = _parse_ai_context_clause(line)
    if ai_context_value is not None:
        if "ai_context" in table_spec:
            raise SemanticValidationError(f"table {table_spec['name']} ai_context must be defined only once")
        table_spec["ai_context"] = ai_context_value
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

    ai_context_value = _parse_ai_context_clause(line)
    if ai_context_value is not None:
        if "ai_context" in join_spec:
            raise SemanticValidationError(f"join {join_spec['name']} ai_context must be defined only once")
        join_spec["ai_context"] = ai_context_value
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
    expr, remainder = _split_top_level_as(item, label="field definition")
    match = _NAME_AND_TAIL_RE.match(remainder)
    if match is None:
        raise SemanticValidationError(f"Invalid semantic field definition: {item}")
    obj: dict[str, Any] = {
        "name": match.group(1),
        "expr": expr.strip(),
    }
    _apply_field_tail(obj, match.group(2), item=item)
    return obj


def _parse_metric_def(item: str) -> dict[str, Any]:
    expr, remainder = _split_top_level_as(item, label="metric definition")
    match = _NAME_AND_TAIL_RE.match(remainder)
    if match is None:
        raise SemanticValidationError(f"Invalid metric definition: {item}")
    obj: dict[str, Any] = {
        "name": match.group(1).strip(),
        "expr": expr.strip(),
    }
    _apply_metric_tail(obj, match.group(2), item=item)
    return obj


def _split_top_level_as(value: str, *, label: str) -> tuple[str, str]:
    in_single_quotes = False
    in_double_quotes = False
    depth = 0
    split_index: int | None = None
    lower_value = value.lower()
    index = 0

    while index < len(value):
        ch = value[index]
        if ch == "'" and not in_double_quotes:
            if in_single_quotes and index + 1 < len(value) and value[index + 1] == "'":
                index += 2
                continue
            in_single_quotes = not in_single_quotes
        elif ch == '"' and not in_single_quotes:
            in_double_quotes = not in_double_quotes
        elif not in_single_quotes and not in_double_quotes:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            elif (
                depth == 0
                and lower_value.startswith(" as ", index)
            ):
                split_index = index
        index += 1

    if split_index is None:
        raise SemanticValidationError(f"Expected 'as' in {label}: {value}")

    left = value[:split_index].strip()
    right = value[split_index + 4 :].strip()
    if not left or not right:
        raise SemanticValidationError(f"Expected '<expr> as <name>' in {label}: {value}")
    return left, right


def _unescape_string(value: str) -> str:
    return value.replace("''", "'")


def _parse_ai_context_literal(value: str) -> dict[str, Any]:
    unescaped = _unescape_string(value)
    try:
        loaded = json.loads(unescaped)
    except json.JSONDecodeError as exc:
        raise SemanticValidationError(f"Invalid ai_context JSON: {unescaped}") from exc
    if not isinstance(loaded, dict):
        raise SemanticValidationError("ai_context must decode to a JSON object")
    return loaded


def _parse_ai_context_clause(value: str) -> dict[str, Any] | None:
    literal_match = _AI_CONTEXT_RE.match(value)
    block_match = _AI_CONTEXT_BLOCK_RE.match(value)
    if literal_match is not None:
        return _parse_ai_context_literal(literal_match.group(1))
    if block_match is not None:
        return _parse_ai_context_block(block_match.group(1))
    return None


def _parse_ai_context_block(body: str) -> dict[str, Any]:
    context = _parse_ai_context_properties(body, allow_concepts=True, label="ai_context")
    return context


def _parse_ai_context_properties(body: str, *, allow_concepts: bool, label: str) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    concepts: list[dict[str, Any]] = []
    position = 0
    while True:
        position = _skip_ws(body, position)
        if position >= len(body):
            break
        if _starts_with_keyword(body, position, "concept"):
            if not allow_concepts:
                raise SemanticValidationError(f"{label} nested concept blocks are not allowed")
            position += len("concept")
            position = _skip_ws(body, position)
            concept_id, position = _parse_identifier(body, position, label="concept id")
            position = _skip_ws(body, position)
            concept_body, position = _parse_parenthesized_content(body, position, label=f"concept {concept_id}")
            concept = _parse_ai_context_properties(
                concept_body,
                allow_concepts=False,
                label=f"concept {concept_id}",
            )
            concept["concept_id"] = concept_id
            concepts.append(concept)
            continue
        parsed_properties, position = _parse_single_ai_context_property(body, position, label=label)
        for key, parsed_value in parsed_properties.items():
            if key in properties:
                raise SemanticValidationError(f"Duplicate {label} property: {key}")
            properties[key] = parsed_value
    if concepts:
        properties["concepts"] = concepts
    return properties


def _parse_single_ai_context_property(body: str, position: int, *, label: str) -> tuple[dict[str, Any], int]:
    keyword, position = _parse_identifier(body, position, label=f"{label} property")
    key = keyword.lower()
    position = _skip_ws(body, position)
    if key == "phrases":
        phrases_body, position = _parse_parenthesized_content(body, position, label=f"{label} phrases")
        return {"phrases": _parse_string_list(phrases_body, label=f"{label} phrases")}, position
    if key in {"preferred", "requires_filter"}:
        value, position = _parse_bool_literal(body, position, label=f"{label} {key}")
        return {key: value}, position
    if key in {
        "concept_id",
        "concept_kind",
        "default_grain",
        "default_window",
        "time_dimension",
        "predicate",
        "notes",
    }:
        value, position = _parse_scalar_literal(body, position, label=f"{label} {key}")
        return {key: value}, position
    raise SemanticValidationError(f"Unknown {label} property: {keyword}")


def _skip_ws(value: str, position: int) -> int:
    while position < len(value) and value[position].isspace():
        position += 1
    return position


def _starts_with_keyword(value: str, position: int, keyword: str) -> bool:
    end = position + len(keyword)
    if value[position:end].lower() != keyword.lower():
        return False
    if end < len(value) and (value[end].isalnum() or value[end] == "_"):
        return False
    return True


def _parse_identifier(value: str, position: int, *, label: str) -> tuple[str, int]:
    match = _IDENTIFIER_RE.match(value, position)
    if match is None:
        raise SemanticValidationError(f"Expected {label}")
    return match.group(0), match.end()


def _parse_parenthesized_content(value: str, position: int, *, label: str) -> tuple[str, int]:
    if position >= len(value) or value[position] != "(":
        raise SemanticValidationError(f"Expected '(' after {label}")
    depth = 0
    in_single_quotes = False
    start = position + 1
    index = position
    while index < len(value):
        ch = value[index]
        if ch == "'" and not in_single_quotes:
            in_single_quotes = True
            index += 1
            continue
        if ch == "'" and in_single_quotes:
            if index + 1 < len(value) and value[index + 1] == "'":
                index += 2
                continue
            in_single_quotes = False
            index += 1
            continue
        if not in_single_quotes:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    return value[start:index], index + 1
        index += 1
    raise SemanticValidationError(f"Unclosed parentheses in {label}")


def _parse_string_list(body: str, *, label: str) -> list[str]:
    items = _split_top_level_commas(body)
    parsed: list[str] = []
    for item in items:
        stripped = item.strip()
        if not stripped:
            continue
        if len(stripped) < 2 or stripped[0] != "'" or stripped[-1] != "'":
            raise SemanticValidationError(f"{label} must contain only quoted strings")
        parsed.append(_unescape_string(stripped[1:-1]))
    return parsed


def _parse_bool_literal(value: str, position: int, *, label: str) -> tuple[bool, int]:
    if value[position:].lower().startswith("true"):
        end = position + 4
        if end == len(value) or value[end].isspace() or value[end] == ")":
            return True, end
    if value[position:].lower().startswith("false"):
        end = position + 5
        if end == len(value) or value[end].isspace() or value[end] == ")":
            return False, end
    raise SemanticValidationError(f"Expected boolean value for {label}")


def _parse_scalar_literal(value: str, position: int, *, label: str) -> tuple[str, int]:
    if position >= len(value):
        raise SemanticValidationError(f"Expected value for {label}")
    if value[position] == "'":
        index = position + 1
        parsed: list[str] = []
        while index < len(value):
            ch = value[index]
            if ch == "'":
                if index + 1 < len(value) and value[index + 1] == "'":
                    parsed.append("'")
                    index += 2
                    continue
                return "".join(parsed), index + 1
            parsed.append(ch)
            index += 1
        raise SemanticValidationError(f"Unclosed quoted string for {label}")
    parsed, end = _parse_identifier(value, position, label=label)
    return parsed, end


def _consume_keyword_value(tail: str, keyword: str) -> tuple[str, str | None]:
    pattern = re.compile(rf"^\s+{keyword}\s+", re.IGNORECASE)
    match = pattern.match(tail)
    if match is None:
        return tail, None
    remainder = tail[match.end():]
    if keyword == "type":
        type_match = re.match(r'([A-Za-z_][A-Za-z0-9_]*|"[^"]+")', remainder)
        if type_match is None:
            raise SemanticValidationError(f"Invalid {keyword} clause: {tail.strip()}")
        value = type_match.group(1).strip('"')
        return remainder[type_match.end():], value
    quoted_match = re.match(r"'((?:''|[^'])*)'", remainder, re.DOTALL)
    if quoted_match is None:
        raise SemanticValidationError(f"Invalid {keyword} clause: {tail.strip()}")
    return remainder[quoted_match.end():], quoted_match.group(1)


def _consume_ai_context_value(tail: str) -> tuple[str, dict[str, Any] | None]:
    pattern = re.compile(r"^\s+ai_context\s+", re.IGNORECASE)
    match = pattern.match(tail)
    if match is None:
        return tail, None
    remainder = tail[match.end():]
    if remainder.startswith("'"):
        quoted_match = re.match(r"'((?:''|[^'])*)'", remainder, re.DOTALL)
        if quoted_match is None:
            raise SemanticValidationError(f"Invalid ai_context clause: {tail.strip()}")
        return remainder[quoted_match.end():], _parse_ai_context_literal(quoted_match.group(1))
    if remainder.startswith("("):
        body, end = _parse_parenthesized_content(remainder, 0, label="ai_context")
        return remainder[end:], _parse_ai_context_block(body)
    raise SemanticValidationError(f"Invalid ai_context clause: {tail.strip()}")


def _apply_field_tail(obj: dict[str, Any], tail: str, *, item: str) -> None:
    remainder = tail
    while remainder.strip():
        updated, value = _consume_keyword_value(remainder, "type")
        if value is not None:
            obj["data_type"] = value
            remainder = updated
            continue
        updated, value = _consume_keyword_value(remainder, "description")
        if value is not None:
            obj["description"] = _unescape_string(value)
            remainder = updated
            continue
        updated, value = _consume_ai_context_value(remainder)
        if value is not None:
            if "ai_context" in obj:
                raise SemanticValidationError(f"Duplicate ai_context in semantic field definition: {item}")
            obj["ai_context"] = value
            remainder = updated
            continue
        raise SemanticValidationError(f"Invalid semantic field definition: {item}")


def _apply_metric_tail(obj: dict[str, Any], tail: str, *, item: str) -> None:
    remainder = tail
    while remainder.strip():
        updated, value = _consume_keyword_value(remainder, "description")
        if value is not None:
            obj["description"] = _unescape_string(value)
            remainder = updated
            continue
        updated, value = _consume_ai_context_value(remainder)
        if value is not None:
            if "ai_context" in obj:
                raise SemanticValidationError(f"Duplicate ai_context in metric definition: {item}")
            obj["ai_context"] = value
            remainder = updated
            continue
        raise SemanticValidationError(f"Invalid metric definition: {item}")
