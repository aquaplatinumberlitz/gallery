"""Parse fielded library search syntax and build matching SQL predicates."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any

FIELD_PATTERN = re.compile(
    r"""(?ix)
    \b(
        prompt|positive|negative|
        date|generation_time|gen_time|
        source|tool|
        seed|steps|cfg|cfg_scale|
        sampler|scheduler|
        size|width|height|aspect_ratio|ratio|
        model|checkpoint|model_hash|model_or_hash|
        lora|resource|resource_hash|
        clip_skip|hires_upscale|hires_steps|
        denoising_strength|
        vae|ensd|aesthetic_score|
        path|folder|location|
        name|
        param|advanced|raw
    )
    \s*:\s*
    """
)

COMP_OP_PATTERN = re.compile(r"^(>=?|<=?)\s*")


def _normalize_field_name(field: str) -> str:
    aliases: dict[str, str] = {
        "positive": "prompt",
        "gen_time": "generation_time",
        "source": "tool",
        "cfg": "cfg_scale",
        "checkpoint": "model",
        "ratio": "aspect_ratio",
        "folder": "path",
        "location": "path",
        "resource": "lora",
    }
    # model_or_hash is NOT aliased — it is a distinct field with its own SQL predicate.
    return aliases.get(field, field)


@dataclass
class FieldToken:
    """A parsed `field:value` search token with optional operator and key data."""

    field: str
    value: str
    operator: str = "="
    quote_char: str = ""
    key: str | None = None


@dataclass
class ParsedQuery:
    """A search query split into free text and structured field filters."""

    residual_text: str
    fields: list[FieldToken] = field(default_factory=list)


@dataclass
class ParserState:
    """Mutable cursor over query characters while extracting field values."""

    buf: list[str]
    pos: int = 0

    def peek(self, offset: int = 0) -> str:
        """Return the character at the current cursor plus offset, or an empty string."""
        idx = self.pos + offset
        return self.buf[idx] if 0 <= idx < len(self.buf) else ""

    def advance(self, n: int = 1) -> None:
        """Move the parser cursor forward by `n` characters."""
        self.pos += n

    def remaining(self) -> str:
        """Return the unconsumed query text from the current cursor."""
        return "".join(self.buf[self.pos :])

    def finished(self) -> bool:
        """Return whether the cursor has consumed the full query buffer."""
        return self.pos >= len(self.buf)


def parse_fielded_query(raw: str) -> ParsedQuery:
    """Parse free text plus supported `field:value` filters from a search query."""
    chars = list(raw)
    fields: list[FieldToken] = []
    residual_parts: list[str] = []
    state = ParserState(chars)

    while not state.finished():
        remaining = state.remaining()
        fm = FIELD_PATTERN.search(remaining)
        if fm is None:
            residual_parts.append(remaining)
            break

        prefix = remaining[: fm.start()]
        if prefix:
            residual_parts.append(prefix.rstrip())

        field_name_raw = fm.group(1)
        state.advance(fm.end())

        value, quote_char = _read_field_value(state)
        normalized_field = _normalize_field_name(field_name_raw.lower())
        operator = "="
        actual_value = value
        actual_key: str | None = None

        if normalized_field in {"param", "advanced"}:
            if value.endswith(":"):
                actual_key = value[:-1]
                next_value, qc = _read_field_value(state)
                actual_value = next_value
                quote_char = qc
            elif ":" in value:
                actual_key, actual_value = value.split(":", 1)
            else:
                actual_key = value
                actual_value = ""
        elif normalized_field not in {"raw"}:
            op_match = COMP_OP_PATTERN.match(value)
            if op_match:
                operator = op_match.group(1)
                actual_value = value[op_match.end() :].strip()

        if actual_key is not None:
            ft = FieldToken(
                field=normalized_field,
                key=actual_key,
                value=actual_value,
            )
        else:
            ft = FieldToken(
                field=normalized_field,
                value=actual_value,
                operator=operator,
                quote_char=quote_char,
            )
        fields.append(ft)

    residual_text = "".join(residual_parts).strip()
    return ParsedQuery(residual_text=residual_text, fields=fields)


def _read_field_value(state: ParserState) -> tuple[str, str]:
    while state.peek() == " ":
        state.advance()

    if state.peek() in ('"', "'"):
        quote = state.peek()
        state.advance()
        value_parts: list[str] = []
        while not state.finished():
            ch = state.peek()
            state.advance()
            if ch == quote:
                break
            value_parts.append(ch)
        return "".join(value_parts), quote

    value_parts: list[str] = []
    while not state.finished():
        ch = state.peek()
        if ch == " " or ch in ('"', "'"):
            break
        next_match = FIELD_PATTERN.search(state.remaining())
        if next_match is not None and next_match.start() == 0:
            break
        value_parts.append(ch)
        state.advance()

    return "".join(value_parts).rstrip(), ""


def _escape_like_literal(raw_value: str) -> str:
    return raw_value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _like_value(raw_value: str) -> str:
    if raw_value.endswith("*") and not raw_value.endswith("\\*"):
        base = raw_value[:-1]
        return f"{_escape_like_literal(base)}%"
    escaped = _escape_like_literal(raw_value)
    if "*" not in raw_value:
        return escaped
    return escaped.replace("*", "%")


TEXT_LIKE_FIELDS: set[str] = {
    "prompt",
    "negative",
    "name",
    "tool",
    "sampler",
    "scheduler",
    "model",
    "lora",
    "resource_hash",
    "vae",
    "date",
    "generation_time",
}

OR_VALUE_FIELDS: set[str] = {"model", "sampler", "seed", "path"}

COLUMN_MAP: dict[str, str] = {
    "prompt": "prompt",
    "negative": "negative_prompt",
    "date": "date",
    "generation_time": "generation_time",
    "tool": "tool",
    "seed": "seed",
    "steps": "steps",
    "cfg_scale": "cfg_scale",
    "sampler": "sampler",
    "scheduler": "scheduler",
    "width": "width",
    "height": "height",
    "aspect_ratio": "aspect_ratio",
    "model": "model",
    "model_hash": "model_hash",
    "clip_skip": "clip_skip",
    "hires_upscale": "hires_upscale",
    "hires_steps": "hires_steps",
    "denoising_strength": "denoising_strength",
    "vae": "vae",
    "ensd": "ensd",
    "aesthetic_score": "aesthetic_score",
    "path": "path",
    "name": "name",
}


def _escape_fts_token(token: str) -> str:
    return '"' + token.replace('"', '""') + '"'


def _unicode_match_query(query: str) -> str:
    tokens = re.findall(r"[\w.-]+", query, flags=re.UNICODE)
    if not tokens:
        return _escape_fts_token(query)
    return " AND ".join(_escape_fts_token(token) for token in tokens)


def _split_unquoted(value: str, delimiter: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    quote = ""
    escaped = False
    for ch in value:
        if escaped:
            current.append(ch)
            escaped = False
            continue
        if ch == "\\":
            current.append(ch)
            escaped = True
            continue
        if quote:
            if ch == quote:
                quote = ""
            current.append(ch)
            continue
        if ch in ('"', "'"):
            quote = ch
            current.append(ch)
            continue
        if ch == delimiter:
            part = "".join(current).strip()
            if part:
                parts.append(part)
            current = []
            continue
        current.append(ch)
    part = "".join(current).strip()
    if part:
        parts.append(part)
    return parts


def _or_values(ft: FieldToken) -> list[str]:
    if ft.field not in OR_VALUE_FIELDS or ft.operator != "=" or ft.quote_char or "|" not in ft.value:
        return []
    return _split_unquoted(ft.value, "|")


@dataclass
class _ConditionBuilder:
    conditions: list[str] = field(default_factory=list)
    params: dict[str, Any] = field(default_factory=dict)
    param_idx: int = 0

    def next_param(self, value: Any) -> str:
        name = f"p{self.param_idx}"
        self.param_idx += 1
        self.params[name] = value
        return f":{name}"


def _append_residual_condition(builder: _ConditionBuilder, residual_text: str) -> None:
    try:
        fts_query = _unicode_match_query(residual_text)
        builder.conditions.append(
            "m.id IN (SELECT rowid FROM image_metadata_fts WHERE image_metadata_fts MATCH "
            + builder.next_param(fts_query)
            + ")"
        )
    except Exception:  # noqa: BLE001
        pattern = f"%{residual_text}%"
        builder.conditions.append(
            "("
            + " OR ".join(
                f"m.{col} LIKE {builder.next_param(pattern)} ESCAPE '\\'"
                for col in ("name", "prompt", "negative_prompt", "model", "sampler", "raw_metadata_text")
            )
            + ")"
        )


def _handle_raw(builder: _ConditionBuilder, ft: FieldToken) -> None:
    like_val = _like_value(ft.value)
    builder.conditions.append(f"m.raw_metadata_text LIKE {builder.next_param(f'%{like_val}%')} ESCAPE '\\'")


def _handle_json_field(builder: _ConditionBuilder, ft: FieldToken) -> None:
    if ft.key:
        json_path = json.dumps(ft.key)
        path_param = builder.next_param(f"$.{json_path}")
        comparison = f") = {builder.next_param(ft.value)}" if ft.value else ") IS NOT NULL"
        builder.conditions.append(
            "json_valid(m.metadata_json) AND json_extract(m.metadata_json, " + path_param + comparison
        )
        return
    like_val = f'%"{ft.value}%'
    builder.conditions.append(f"m.metadata_json LIKE {builder.next_param(like_val)} ESCAPE '\\\\'")


def _handle_model_or_hash(builder: _ConditionBuilder, ft: FieldToken) -> None:
    if "=" in ft.value:
        builder.conditions.append(
            f"(m.model = {builder.next_param(ft.value)} OR m.model_hash = {builder.next_param(ft.value)})"
        )
        return
    escaped = _escape_like_literal(ft.value)
    builder.conditions.append(
        f"(m.model LIKE {builder.next_param(f'%{escaped}%')} ESCAPE '\\' "
        f"OR m.model_hash LIKE {builder.next_param(f'%{escaped}%')} ESCAPE '\\')"
    )


def _handle_size(builder: _ConditionBuilder, ft: FieldToken) -> None:
    size_match = re.match(r"(\d+)\s*x\s*(\d+)", ft.value, re.IGNORECASE)
    if size_match:
        width, height = (int(size_match.group(index)) for index in (1, 2))
        builder.conditions.append(f"m.width = {builder.next_param(width)} AND m.height = {builder.next_param(height)}")


def _handle_path(builder: _ConditionBuilder, ft: FieldToken) -> None:
    likes = [
        f"m.path LIKE {builder.next_param(f'%{_like_value(value)}%')} ESCAPE '\\'"
        for value in (_or_values(ft) or [ft.value])
    ]
    builder.conditions.append("(" + " OR ".join(likes) + ")")


def _handle_resource_hash(builder: _ConditionBuilder, ft: FieldToken) -> None:
    pattern = f"%{_escape_like_literal(ft.value)}%"
    builder.conditions.append(
        "EXISTS (SELECT 1 FROM image_resources ir WHERE ir.path = m.path AND ("
        f"ir.resource_hash LIKE {builder.next_param(pattern)} ESCAPE '\\' OR "
        f"ir.hash LIKE {builder.next_param(pattern)} ESCAPE '\\'))"
    )


def _handle_lora(builder: _ConditionBuilder, ft: FieldToken) -> None:
    pattern = f"%{_escape_like_literal(ft.value)}%"
    builder.conditions.append(
        "EXISTS (SELECT 1 FROM image_resources ir WHERE ir.path = m.path AND ir.kind = 'lora' AND ("
        f"ir.name LIKE {builder.next_param(pattern)} ESCAPE '\\' OR "
        f"ir.resource_hash LIKE {builder.next_param(pattern)} ESCAPE '\\' OR "
        f"ir.hash LIKE {builder.next_param(pattern)} ESCAPE '\\'))"
    )


def _numeric_value(value: str) -> int | float | None:
    try:
        return int(value)
    except ValueError:
        with suppress(ValueError):
            return float(value)
    return None


def _handle_standard_field(builder: _ConditionBuilder, ft: FieldToken) -> None:
    col = COLUMN_MAP.get(ft.field, "raw_metadata_text")
    if ft.operator in (">", ">=", "<", "<="):
        numeric_value = _numeric_value(ft.value)
        if numeric_value is not None:
            builder.conditions.append(
                f"m.{col} IS NOT NULL AND m.{col} {ft.operator} {builder.next_param(numeric_value)}"
            )
        return
    if ft.field in TEXT_LIKE_FIELDS:
        values = (
            [term.strip() for term in ft.value.split(",") if term.strip()]
            if ft.quote_char and "," in ft.value
            else (_or_values(ft) or [ft.value])
        )
        joiner = " AND " if ft.quote_char and "," in ft.value else " OR "
        likes = [
            f"m.{col} LIKE {builder.next_param(f'%{_escape_like_literal(value)}%')} ESCAPE '\\'" for value in values
        ]
        builder.conditions.append("(" + joiner.join(likes) + ")")
        return
    if _like_value(ft.value) != ft.value or "*" in ft.value:
        builder.conditions.append(f"m.{col} LIKE {builder.next_param(_like_value(ft.value))} ESCAPE '\\'")
        return
    equals = [f"m.{col} = {builder.next_param(value)}" for value in (_or_values(ft) or [ft.value])]
    builder.conditions.append("(" + " OR ".join(equals) + ")")


FieldHandler = Callable[[_ConditionBuilder, FieldToken], None]
_FIELD_HANDLERS: dict[str, FieldHandler] = {
    "raw": _handle_raw,
    "param": _handle_json_field,
    "advanced": _handle_json_field,
    "model_or_hash": _handle_model_or_hash,
    "size": _handle_size,
    "path": _handle_path,
    "resource_hash": _handle_resource_hash,
    "lora": _handle_lora,
}


def build_fielded_conditions(parsed: ParsedQuery) -> tuple[list[str], dict[str, Any]]:
    """Build WHERE conditions and params from a parsed field-handler table."""
    builder = _ConditionBuilder()
    if parsed.residual_text:
        _append_residual_condition(builder, parsed.residual_text)
    for token in parsed.fields:
        _FIELD_HANDLERS.get(token.field, _handle_standard_field)(builder, token)
    return builder.conditions, builder.params


def build_fielded_search_sql(parsed: ParsedQuery, limit: int = 50, offset: int = 0) -> tuple[str, dict[str, Any]]:
    """Build the image metadata SQL query and named parameters for parsed filters."""
    conditions, params = build_fielded_conditions(parsed)

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    sql = f"""
        SELECT m.*, fi.parent_path, fi.type AS file_type
        FROM image_metadata m
        JOIN file_index fi ON fi.path = m.path
        {where_clause}
        ORDER BY m.mtime DESC, m.name ASC
        LIMIT {int(limit)} OFFSET {int(offset)}
    """
    return sql, params
