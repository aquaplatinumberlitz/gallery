"""Tests for the fielded search query parser and SQL builder."""

import pytest
from backend.fielded_search_parser import (
    parse_fielded_query,
    build_fielded_search_sql,
    FieldToken,
    ParsedQuery,
)


class TestParseFieldedQuery:
    def test_plain_text_passthrough(self):
        """Plain text with no fields remains unchanged."""
        result = parse_fielded_query("rain portrait")
        assert result.residual_text == "rain portrait"
        assert len(result.fields) == 0

    def test_plain_text_empty(self):
        result = parse_fielded_query("")
        assert result.residual_text == ""
        assert len(result.fields) == 0

    def test_seed_field(self):
        result = parse_fielded_query("seed:123")
        assert result.residual_text == ""
        assert len(result.fields) == 1
        assert result.fields[0].field == "seed"
        assert result.fields[0].value == "123"

    def test_residual_text_with_field(self):
        result = parse_fielded_query("rain seed:123")
        assert result.residual_text == "rain"
        assert len(result.fields) == 1
        assert result.fields[0].field == "seed"
        assert result.fields[0].value == "123"

    def test_quoted_field_value(self):
        result = parse_fielded_query('prompt:"girl, rain"')
        assert result.residual_text == ""
        assert len(result.fields) == 1
        assert result.fields[0].field == "prompt"
        assert result.fields[0].value == "girl, rain"
        assert result.fields[0].quote_char == '"'

    def test_multiple_fields(self):
        result = parse_fielded_query('rain prompt:"girl, rain" seed:123 model:"realistic*" negative:"watermark"')
        assert result.residual_text == "rain"
        assert len(result.fields) == 4

    def test_alias_positive(self):
        result = parse_fielded_query("positive:test")
        assert len(result.fields) == 1
        assert result.fields[0].field == "prompt"  # normalized

    def test_alias_gen_time(self):
        result = parse_fielded_query("gen_time:1234567890")
        assert result.fields[0].field == "generation_time"

    def test_alias_source(self):
        result = parse_fielded_query("source:comfyui")
        assert result.fields[0].field == "tool"

    def test_alias_cfg(self):
        result = parse_fielded_query("cfg:7.5")
        assert result.fields[0].field == "cfg_scale"

    def test_numeric_comparison_operator(self):
        result = parse_fielded_query("steps:>=20")
        assert result.fields[0].operator == ">="
        assert result.fields[0].value == "20"

    def test_generic_param(self):
        result = parse_fielded_query('param:some_key:"value"')
        assert result.fields[0].field == "param"
        assert result.fields[0].value == "some_key:"  # includes the trailing colon before quoted value

    def test_generic_param_without_quote(self):
        result = parse_fielded_query("param:some_key:value")
        assert result.fields[0].field == "param"
        assert result.fields[0].value == "some_key:value"

    def test_generic_raw(self):
        result = parse_fielded_query('raw:"some raw text"')
        assert result.fields[0].field == "raw"

    def test_path_field(self):
        result = parse_fielded_query('path:"/images/test"')
        assert result.fields[0].field == "path"

    def test_size_field(self):
        result = parse_fielded_query("size:1920x1080")
        assert result.fields[0].field == "size"

    def test_model_or_hash(self):
        result = parse_fielded_query('model_or_hash:"sd_xl"')
        assert result.fields[0].field == "model"  # normalized from alias


class TestBuildFieldedSearchSql:
    def test_plain_text_sql_contains_fts(self):
        parsed = ParsedQuery(residual_text="rain")
        sql, params = build_fielded_search_sql(parsed, limit=10)
        assert "image_metadata_fts" in sql
        assert "MATCH" in sql
        assert "LIMIT 10" in sql

    def test_empty_query_sql_has_no_where(self):
        parsed = ParsedQuery(residual_text="", fields=[])
        sql, params = build_fielded_search_sql(parsed, limit=10)
        assert "WHERE" not in sql

    def test_seed_field_sql(self):
        parsed = ParsedQuery(residual_text="", fields=[FieldToken(field="seed", value="123")])
        sql, params = build_fielded_search_sql(parsed, limit=10)
        assert "m.seed" in sql
        assert "= " in sql  # exact match

    def test_numeric_comparison_sql(self):
        parsed = ParsedQuery(residual_text="", fields=[FieldToken(field="steps", value="20", operator=">=")])
        sql, params = build_fielded_search_sql(parsed, limit=10)
        assert "m.steps" in sql
        assert ">=" in sql

    def test_wildcard_model_sql(self):
        parsed = ParsedQuery(residual_text="", fields=[FieldToken(field="model", value="realistic*")])
        sql, params = build_fielded_search_sql(parsed, limit=10)
        assert "LIKE" in sql

    def test_raw_field_sql(self):
        parsed = ParsedQuery(residual_text="", fields=[FieldToken(field="raw", value="test text")])
        sql, params = build_fielded_search_sql(parsed, limit=10)
        assert "raw_metadata_text" in sql
        assert "LIKE" in sql

    def test_combined_residual_and_fields(self):
        parsed = ParsedQuery(
            residual_text="rain",
            fields=[
                FieldToken(field="seed", value="123"),
                FieldToken(field="model", value="realistic*"),
            ],
        )
        sql, params = build_fielded_search_sql(parsed, limit=10)
        assert "MATCH" in sql  # residual uses FTS
        assert "m.seed" in sql
        assert "m.model" in sql
        assert "LIKE" in sql
