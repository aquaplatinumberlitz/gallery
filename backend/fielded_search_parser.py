from __future__ import annotations

import json
import re
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
    field: str
    value: str
    operator: str = "="
    quote_char: str = ""
    key: str | None = None


@dataclass
class ParsedQuery:
    residual_text: str
    fields: list[FieldToken] = field(default_factory=list)


@dataclass
class ParserState:
    buf: list[str]
    pos: int = 0

    def peek(self, offset: int = 0) -> str:
        idx = self.pos + offset
        return self.buf[idx] if 0 <= idx < len(self.buf) else ""

    def advance(self, n: int = 1) -> None:
        self.pos += n

    def remaining(self) -> str:
        return "".join(self.buf[self.pos :])

    def finished(self) -> bool:
        return self.pos >= len(self.buf)


def parse_fielded_query(raw: str) -> ParsedQuery:
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


def _like_value(raw_value: str) -> str:
    if raw_value.endswith("*") and not raw_value.endswith("\\*"):
        base = raw_value[:-1]
        escaped = base.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        return f"{escaped}%"
    escaped = raw_value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
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


def build_fielded_conditions(parsed: ParsedQuery) -> tuple[list[str], dict[str, Any]]:
    """Build WHERE conditions and params from ParsedQuery.

    Returns (conditions_list, params_dict) suitable for AND'ing into a WHERE clause.
    """
    conditions: list[str] = []
    params: dict[str, Any] = {}
    param_idx = 0

    def next_param(value: Any) -> str:
        nonlocal param_idx
        name = f"p{param_idx}"
        param_idx += 1
        params[name] = value
        return f":{name}"

    if parsed.residual_text:
        try:
            fts_query = _unicode_match_query(parsed.residual_text)
            conditions.append(
                "m.id IN (SELECT rowid FROM image_metadata_fts WHERE image_metadata_fts MATCH "
                + next_param(fts_query)
                + ")"
            )
        except Exception:  # noqa: BLE001
            pattern = f"%{parsed.residual_text}%"
            conditions.append(
                "("
                + " OR ".join(
                    f"m.{col} LIKE {next_param(pattern)} ESCAPE '\\'"
                    for col in ("name", "prompt", "negative_prompt", "model", "sampler", "raw_metadata_text")
                )
                + ")"
            )

    for ft in parsed.fields:
        if ft.field == "raw":
            like_val = _like_value(ft.value)
            conditions.append(f"m.raw_metadata_text LIKE {next_param(f'%{like_val}%')} ESCAPE '\\'")
            continue

        if ft.field == "param" or ft.field == "advanced":
            if ft.key:
                json_path = json.dumps(ft.key)
                if ft.value:
                    conditions.append(
                        "json_valid(m.metadata_json) AND json_extract(m.metadata_json, "
                        + next_param(f"$.{json_path}")
                        + ") = "
                        + next_param(ft.value)
                    )
                else:
                    conditions.append(
                        "json_valid(m.metadata_json) AND json_extract(m.metadata_json, "
                        + next_param(f"$.{json_path}")
                        + ") IS NOT NULL"
                    )
            else:
                like_val = f'%"{ft.value}%'
                conditions.append(f"m.metadata_json LIKE {next_param(like_val)} ESCAPE '\\\\'")
            continue

        if ft.field == "model_or_hash":
            like_val = _like_value(ft.value)
            # Contains search on both model and model_hash, unless exact-match chars present
            if "=" in ft.value:
                # Exact match
                conditions.append(f"(m.model = {next_param(ft.value)} OR m.model_hash = {next_param(ft.value)})")
            else:
                # Contains search
                escaped = ft.value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                conditions.append(
                    f"(m.model LIKE {next_param(f'%{escaped}%')} ESCAPE '\\' "
                    f"OR m.model_hash LIKE {next_param(f'%{escaped}%')} ESCAPE '\\')"
                )
            continue

        if ft.field == "size":
            size_match = re.match(r"(\d+)\s*x\s*(\d+)", ft.value, re.IGNORECASE)
            if size_match:
                w = int(size_match.group(1))
                h = int(size_match.group(2))
                conditions.append(f"m.width = {next_param(w)} AND m.height = {next_param(h)}")
            continue

        if ft.field == "path":
            like_val = _like_value(ft.value)
            conditions.append(f"m.path LIKE {next_param(f'%{like_val}%')} ESCAPE '\\'")
            continue

        if ft.field == "resource_hash":
            escaped = ft.value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            pattern = f"%{escaped}%"
            conditions.append(
                "EXISTS ("
                "SELECT 1 FROM image_resources ir "
                "WHERE ir.path = m.path AND ("
                f"ir.resource_hash LIKE {next_param(pattern)} ESCAPE '\\' OR "
                f"ir.hash LIKE {next_param(pattern)} ESCAPE '\\'"
                ")"
                ")"
            )
            continue

        if ft.field == "lora":
            escaped = ft.value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            pattern = f"%{escaped}%"
            conditions.append(
                "EXISTS ("
                "SELECT 1 FROM image_resources ir "
                "WHERE ir.path = m.path AND ir.kind = 'lora' AND ("
                f"ir.name LIKE {next_param(pattern)} ESCAPE '\\' OR "
                f"ir.resource_hash LIKE {next_param(pattern)} ESCAPE '\\' OR "
                f"ir.hash LIKE {next_param(pattern)} ESCAPE '\\'"
                ")"
                ")"
            )
            continue

        col = COLUMN_MAP.get(ft.field)
        if col is None:
            col = "raw_metadata_text"

        if ft.operator in (">", ">=", "<", "<="):
            numeric_value = None
            try:
                numeric_value = int(ft.value)
            except ValueError:
                try:
                    numeric_value = float(ft.value)
                except ValueError:
                    pass
            if numeric_value is not None:
                conditions.append(f"m.{col} IS NOT NULL AND m.{col} {ft.operator} {next_param(numeric_value)}")
        elif ft.field in TEXT_LIKE_FIELDS:
            # Contains semantics: always wrap with % for substring match
            if ft.quote_char and "," in ft.value:
                terms = [t.strip() for t in ft.value.split(",") if t.strip()]
                likes = []
                for term in terms:
                    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                    likes.append(f"m.{col} LIKE {next_param(f'%{escaped}%')} ESCAPE '\\'")
                conditions.append("(" + " AND ".join(likes) + ")")
            else:
                escaped = ft.value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                conditions.append(f"m.{col} LIKE {next_param(f'%{escaped}%')} ESCAPE '\\'")
        elif _like_value(ft.value) != ft.value or "*" in ft.value:
            like_val = _like_value(ft.value)
            conditions.append(f"m.{col} LIKE {next_param(like_val)} ESCAPE '\\'")
        else:
            conditions.append(f"m.{col} = {next_param(ft.value)}")

    return conditions, params


def build_fielded_search_sql(parsed: ParsedQuery, limit: int = 50, offset: int = 0) -> tuple[str, dict[str, Any]]:
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
