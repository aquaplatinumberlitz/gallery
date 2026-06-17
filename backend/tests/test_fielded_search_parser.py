"""
Purpose:
Verifies fielded search parsing and SQL construction for metadata-backed search.

Guarantees:
* field aliases, comparisons, quoted values, and residual terms parse consistently
* generated SQL keeps expected filtering behavior without crashing on supported fields

Run when:
* changing fielded_search_parser, search field aliases, or metadata search SQL
* touching advanced search UI query syntax or backend field semantics
"""

import json

from backend.fielded_search_parser import (
    parse_fielded_query,
    build_fielded_search_sql,
    FieldToken,
    ParsedQuery,
)


# ---------------------------------------------------------------------------
# Parser tests
# ---------------------------------------------------------------------------


class TestParseFieldedQuery:
    def test_plain_text_passthrough(self):
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
        assert result.fields[0].field == "prompt"

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

    # --- model_or_hash tests ---

    def test_model_or_hash_remains_distinct(self):
        result = parse_fielded_query('model_or_hash:"sd_xl"')
        assert result.fields[0].field == "model_or_hash"
        assert result.fields[0].value == "sd_xl"

    def test_model_or_hash_unquoted(self):
        result = parse_fielded_query("model_or_hash:abc123")
        assert result.fields[0].field == "model_or_hash"
        assert result.fields[0].value == "abc123"

    def test_model_is_separate_from_model_or_hash(self):
        result = parse_fielded_query('model:"pony*"')
        assert result.fields[0].field == "model"
        assert result.fields[0].value == "pony*"

    def test_model_hash_is_separate(self):
        result = parse_fielded_query("model_hash:abc123")
        assert result.fields[0].field == "model_hash"
        assert result.fields[0].value == "abc123"

    # --- generic param / advanced tests ---

    def test_param_key_only(self):
        result = parse_fielded_query("param:some_key")
        assert result.fields[0].field == "param"
        assert result.fields[0].key == "some_key"
        assert result.fields[0].value == ""

    def test_param_key_quoted_value(self):
        result = parse_fielded_query('param:some_key:"value"')
        assert result.fields[0].field == "param"
        assert result.fields[0].key == "some_key"
        assert result.fields[0].value == "value"

    def test_param_key_unquoted_value(self):
        result = parse_fielded_query("param:some_key:value")
        assert result.fields[0].field == "param"
        assert result.fields[0].key == "some_key"
        assert result.fields[0].value == "value"

    def test_advanced_key_only(self):
        result = parse_fielded_query("advanced:workflow_field")
        assert result.fields[0].field == "advanced"
        assert result.fields[0].key == "workflow_field"
        assert result.fields[0].value == ""

    def test_advanced_key_quoted_value(self):
        result = parse_fielded_query('advanced:workflow_field:"data"')
        assert result.fields[0].field == "advanced"
        assert result.fields[0].key == "workflow_field"
        assert result.fields[0].value == "data"

    def test_advanced_key_unquoted_value(self):
        result = parse_fielded_query("advanced:workflow_field:data")
        assert result.fields[0].field == "advanced"
        assert result.fields[0].key == "workflow_field"
        assert result.fields[0].value == "data"

    def test_param_and_advanced_together(self):
        result = parse_fielded_query('param:some_key:"value" advanced:wf:"data"')
        assert len(result.fields) == 2
        assert result.fields[0].field == "param"
        assert result.fields[0].key == "some_key"
        assert result.fields[0].value == "value"
        assert result.fields[1].field == "advanced"
        assert result.fields[1].key == "wf"
        assert result.fields[1].value == "data"

    def test_generic_raw(self):
        result = parse_fielded_query('raw:"some raw text"')
        assert result.fields[0].field == "raw"
        assert result.fields[0].value == "some raw text"

    def test_raw_unquoted(self):
        result = parse_fielded_query("raw:simple_text")
        assert result.fields[0].field == "raw"
        assert result.fields[0].value == "simple_text"

    # --- first-class fields ---

    def test_prompt_field(self):
        result = parse_fielded_query('prompt:"girl"')
        assert result.fields[0].field == "prompt"

    def test_negative_field(self):
        result = parse_fielded_query('negative:"watermark"')
        assert result.fields[0].field == "negative"

    def test_name_field(self):
        result = parse_fielded_query('name:"foo"')
        assert result.fields[0].field == "name"

    def test_tool_field(self):
        result = parse_fielded_query("tool:SwarmUI")
        assert result.fields[0].field == "tool"

    def test_source_alias(self):
        result = parse_fielded_query("source:ComfyUI")
        assert result.fields[0].field == "tool"

    def test_date_field(self):
        result = parse_fielded_query("date:2026-06-10")
        assert result.fields[0].field == "date"
        assert result.fields[0].value == "2026-06-10"

    def test_generation_time_field(self):
        result = parse_fielded_query('generation_time:"1234567890"')
        assert result.fields[0].field == "generation_time"

    def test_steps_field(self):
        result = parse_fielded_query("steps:30")
        assert result.fields[0].field == "steps"
        assert result.fields[0].value == "30"

    def test_steps_comparison(self):
        result = parse_fielded_query("steps:>=20")
        assert result.fields[0].operator == ">="
        assert result.fields[0].value == "20"

    def test_cfg_scale_field(self):
        result = parse_fielded_query("cfg:7")
        assert result.fields[0].field == "cfg_scale"
        assert result.fields[0].value == "7"

    def test_sampler_field(self):
        result = parse_fielded_query('sampler:"Euler a"')
        assert result.fields[0].field == "sampler"

    def test_scheduler_field(self):
        result = parse_fielded_query('scheduler:"karras"')
        assert result.fields[0].field == "scheduler"

    def test_size_field(self):
        result = parse_fielded_query("size:1024x1536")
        assert result.fields[0].field == "size"
        assert result.fields[0].value == "1024x1536"

    def test_width_field(self):
        result = parse_fielded_query("width:1024")
        assert result.fields[0].field == "width"

    def test_height_field(self):
        result = parse_fielded_query("height:1536")
        assert result.fields[0].field == "height"

    def test_aspect_ratio_field(self):
        result = parse_fielded_query("aspect_ratio:2:3")
        assert result.fields[0].field == "aspect_ratio"
        assert result.fields[0].value == "2:3"

    def test_ratio_alias(self):
        result = parse_fielded_query("ratio:2:3")
        assert result.fields[0].field == "aspect_ratio"

    def test_checkpoint_alias(self):
        result = parse_fielded_query('checkpoint:"pony*"')
        assert result.fields[0].field == "model"
        assert result.fields[0].value == "pony*"

    def test_lora_field(self):
        result = parse_fielded_query('lora:"add_detail"')
        assert result.fields[0].field == "lora"

    def test_resource_alias(self):
        result = parse_fielded_query('resource:"add_detail"')
        assert result.fields[0].field == "lora"

    def test_resource_hash(self):
        result = parse_fielded_query("resource_hash:abc123")
        assert result.fields[0].field == "resource_hash"

    def test_clip_skip_field(self):
        result = parse_fielded_query("clip_skip:2")
        assert result.fields[0].field == "clip_skip"

    def test_hires_upscale_field(self):
        result = parse_fielded_query("hires_upscale:2")
        assert result.fields[0].field == "hires_upscale"

    def test_hires_steps_field(self):
        result = parse_fielded_query("hires_steps:10")
        assert result.fields[0].field == "hires_steps"

    def test_denoising_strength_field(self):
        result = parse_fielded_query("denoising_strength:0.45")
        assert result.fields[0].field == "denoising_strength"

    def test_vae_field(self):
        result = parse_fielded_query('vae:"vae-ft-mse"')
        assert result.fields[0].field == "vae"

    def test_ensd_field(self):
        result = parse_fielded_query("ensd:31337")
        assert result.fields[0].field == "ensd"

    def test_aesthetic_score_field(self):
        result = parse_fielded_query("aesthetic_score:6.5")
        assert result.fields[0].field == "aesthetic_score"

    def test_path_field(self):
        result = parse_fielded_query('path:"/some/folder"')
        assert result.fields[0].field == "path"

    def test_folder_alias(self):
        result = parse_fielded_query('folder:"folder-name"')
        assert result.fields[0].field == "path"

    def test_location_alias(self):
        result = parse_fielded_query('location:"folder-name"')
        assert result.fields[0].field == "path"


# ---------------------------------------------------------------------------
# SQL builder tests
# ---------------------------------------------------------------------------


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
        assert "= " in sql

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
        assert "MATCH" in sql
        assert "m.seed" in sql
        assert "m.model" in sql
        assert "LIKE" in sql

    # --- model_or_hash SQL ---

    def test_model_or_hash_sql_searches_both(self):
        parsed = ParsedQuery(residual_text="", fields=[FieldToken(field="model_or_hash", value="abc123")])
        sql, params = build_fielded_search_sql(parsed, limit=10)
        assert "m.model LIKE" in sql
        assert "m.model_hash LIKE" in sql
        assert "OR" in sql

    def test_model_sql_does_not_include_model_hash(self):
        parsed = ParsedQuery(residual_text="", fields=[FieldToken(field="model", value="foo")])
        sql, params = build_fielded_search_sql(parsed, limit=10)
        assert "m.model LIKE" in sql or "m.model =" in sql
        assert "m.model_hash" not in sql

    def test_model_hash_sql_searches_only_hash(self):
        parsed = ParsedQuery(residual_text="", fields=[FieldToken(field="model_hash", value="abc123")])
        sql, params = build_fielded_search_sql(parsed, limit=10)
        assert "m.model_hash" in sql

    def test_resource_hash_sql_searches_resource_metadata(self):
        parsed = ParsedQuery(residual_text="", fields=[FieldToken(field="resource_hash", value="abc123")])
        sql, params = build_fielded_search_sql(parsed, limit=10)
        assert "image_resources ir" in sql
        assert "ir.resource_hash" in sql
        assert "ir.hash" in sql
        assert "m.model_hash" not in sql

    def test_lora_sql_searches_indexed_resources(self):
        parsed = ParsedQuery(residual_text="", fields=[FieldToken(field="lora", value="detail")])
        sql, params = build_fielded_search_sql(parsed, limit=10)
        assert "image_resources ir" in sql
        assert "ir.kind = 'lora'" in sql
        assert "ir.name" in sql

    # --- param / advanced SQL ---

    def test_param_key_only_sql(self):
        parsed = ParsedQuery(residual_text="", fields=[FieldToken(field="param", key="some_key", value="")])
        sql, params = build_fielded_search_sql(parsed, limit=10)
        assert "json_extract" in sql
        assert "IS NOT NULL" in sql
        assert "some_key" in json.dumps("some_key")

    def test_param_key_value_sql(self):
        parsed = ParsedQuery(residual_text="", fields=[FieldToken(field="param", key="some_key", value="value")])
        sql, params = build_fielded_search_sql(parsed, limit=10)
        assert "json_extract" in sql
        assert "=" in sql

    def test_advanced_key_only_sql(self):
        parsed = ParsedQuery(residual_text="", fields=[FieldToken(field="advanced", key="wf", value="")])
        sql, params = build_fielded_search_sql(parsed, limit=10)
        assert "json_extract" in sql
        assert "IS NOT NULL" in sql

    def test_advanced_key_value_sql(self):
        parsed = ParsedQuery(residual_text="", fields=[FieldToken(field="advanced", key="wf", value="data")])
        sql, params = build_fielded_search_sql(parsed, limit=10)
        assert "json_extract" in sql
        assert "=" in sql

    def test_param_sql_uses_bound_params_not_string_interpolation(self):
        parsed = ParsedQuery(residual_text="", fields=[FieldToken(field="param", key="k", value="v")])
        sql, params = build_fielded_search_sql(parsed, limit=10)
        for name, val in params.items():
            assert isinstance(val, (str, int, float))
            if isinstance(val, str):
                assert "'" not in val or "\\'" in val  # no raw values in SQL

    # --- size SQL ---

    def test_size_field_sql_parses_wxH(self):
        parsed = ParsedQuery(residual_text="", fields=[FieldToken(field="size", value="1024x768")])
        sql, params = build_fielded_search_sql(parsed, limit=10)
        assert "m.width" in sql
        assert "m.height" in sql
        assert "1024" in str(params) or 1024 in params.values()
        assert "768" in str(params) or 768 in params.values()

    # --- text contains semantics tests ---

    def test_prompt_field_sql_like(self):
        """prompt:girl should use LIKE %%girl%% not =."""
        parsed = ParsedQuery(residual_text="", fields=[FieldToken(field="prompt", value="girl")])
        sql, params = build_fielded_search_sql(parsed, limit=10)
        assert "LIKE" in sql
        assert "=" not in sql or "m.prompt =" not in sql
        assert "%girl%" in str(params)

    def test_prompt_field_sql_comma_and(self):
        """prompt:"girl, rain" should AND multiple LIKE conditions."""
        parsed = ParsedQuery(residual_text="", fields=[FieldToken(field="prompt", value="girl, rain", quote_char='"')])
        sql, params = build_fielded_search_sql(parsed, limit=10)
        assert sql.count("LIKE") == 2
        assert "AND" in sql
        assert "%girl%" in str(params)
        assert "%rain%" in str(params)

    def test_negative_field_sql_comma_and(self):
        """negative:"watermark, blurry" should AND multiple LIKE conditions."""
        parsed = ParsedQuery(
            residual_text="", fields=[FieldToken(field="negative", value="watermark, blurry", quote_char='"')]
        )
        sql, params = build_fielded_search_sql(parsed, limit=10)
        assert sql.count("LIKE") == 2
        assert "AND" in sql
        assert "%watermark%" in str(params)
        assert "%blurry%" in str(params)

    def test_single_term_quoted_prompt_uses_like(self):
        """prompt:"girl" (quoted, no comma) should use LIKE with %%."""
        parsed = ParsedQuery(residual_text="", fields=[FieldToken(field="prompt", value="girl", quote_char='"')])
        sql, params = build_fielded_search_sql(parsed, limit=10)
        assert "LIKE" in sql
        assert "%girl%" in str(params)

    def test_model_field_sql_like(self):
        """model:pony should use LIKE %%pony%%."""
        parsed = ParsedQuery(residual_text="", fields=[FieldToken(field="model", value="pony")])
        sql, params = build_fielded_search_sql(parsed, limit=10)
        assert "LIKE" in sql
        assert "%pony%" in str(params)

    def test_name_field_sql_like(self):
        """name:cat should use LIKE %%cat%%."""
        parsed = ParsedQuery(residual_text="", fields=[FieldToken(field="name", value="cat")])
        sql, params = build_fielded_search_sql(parsed, limit=10)
        assert "LIKE" in sql
        assert "%cat%" in str(params)

    def test_tool_field_sql_like(self):
        """tool:ComfyUI should use LIKE %%ComfyUI%%."""
        parsed = ParsedQuery(residual_text="", fields=[FieldToken(field="tool", value="ComfyUI")])
        sql, params = build_fielded_search_sql(parsed, limit=10)
        assert "LIKE" in sql
        assert "%ComfyUI%" in str(params)

    def test_sampler_field_sql_like(self):
        """sampler:Euler should use LIKE %%Euler%%."""
        parsed = ParsedQuery(residual_text="", fields=[FieldToken(field="sampler", value="Euler")])
        sql, params = build_fielded_search_sql(parsed, limit=10)
        assert "LIKE" in sql
        assert "%Euler%" in str(params)

    def test_scheduler_field_sql_like(self):
        """scheduler:karras should use LIKE %%karras%%."""
        parsed = ParsedQuery(residual_text="", fields=[FieldToken(field="scheduler", value="karras")])
        sql, params = build_fielded_search_sql(parsed, limit=10)
        assert "LIKE" in sql
        assert "%karras%" in str(params)

    def test_lora_field_sql_like(self):
        """lora:add_detail should use LIKE %%add_detail%%."""
        parsed = ParsedQuery(residual_text="", fields=[FieldToken(field="lora", value="add_detail:0.8")])
        sql, params = build_fielded_search_sql(parsed, limit=10)
        assert "LIKE" in sql
        # underscore is escaped in LIKE pattern
        assert "add" in str(params) and "detail" in str(params) and "0.8" in str(params)

    def test_vae_field_sql_like(self):
        """vae:vae-ft-mse should use LIKE %%vae-ft-mse%%."""
        parsed = ParsedQuery(residual_text="", fields=[FieldToken(field="vae", value="vae-ft-mse")])
        sql, params = build_fielded_search_sql(parsed, limit=10)
        assert "LIKE" in sql
        assert "%vae-ft-mse%" in str(params)

    def test_date_field_sql_like(self):
        """date:2026-06-10 should use LIKE %%2026-06-10%%."""
        parsed = ParsedQuery(residual_text="", fields=[FieldToken(field="date", value="2026-06-10")])
        sql, params = build_fielded_search_sql(parsed, limit=10)
        assert "LIKE" in sql
        assert "%2026-06-10%" in str(params)

    def test_generation_time_field_sql_like(self):
        """generation_time:12345 should use LIKE %%12345%%."""
        parsed = ParsedQuery(residual_text="", fields=[FieldToken(field="generation_time", value="12345")])
        sql, params = build_fielded_search_sql(parsed, limit=10)
        assert "LIKE" in sql
        assert "%12345%" in str(params)

    def test_seed_field_sql_exact(self):
        """seed:123 should use = for exact matching."""
        parsed = ParsedQuery(residual_text="", fields=[FieldToken(field="seed", value="123")])
        sql, params = build_fielded_search_sql(parsed, limit=10)
        assert "m.seed =" in sql or "m.seed= " in sql
        assert "123" in str(params)

    def test_model_hash_field_sql_exact(self):
        """model_hash:abc123 should use = for exact matching."""
        parsed = ParsedQuery(residual_text="", fields=[FieldToken(field="model_hash", value="abc123")])
        sql, params = build_fielded_search_sql(parsed, limit=10)
        assert "m.model_hash =" in sql
        assert "abc123" in str(params)

    def test_steps_field_sql_exact(self):
        """steps:30 should use = for exact matching."""
        parsed = ParsedQuery(residual_text="", fields=[FieldToken(field="steps", value="30")])
        sql, params = build_fielded_search_sql(parsed, limit=10)
        assert "m.steps =" in sql
        assert "30" in str(params)

    def test_cfg_scale_field_sql_exact(self):
        """cfg:7 should use = for exact matching."""
        parsed = ParsedQuery(residual_text="", fields=[FieldToken(field="cfg_scale", value="7")])
        sql, params = build_fielded_search_sql(parsed, limit=10)
        assert "m.cfg_scale =" in sql
        assert "7" in str(params)

    def test_width_height_field_sql_exact(self):
        """width:1024 height:1536 should use =."""
        parsed = ParsedQuery(
            residual_text="",
            fields=[FieldToken(field="width", value="1024"), FieldToken(field="height", value="1536")],
        )
        sql, params = build_fielded_search_sql(parsed, limit=10)
        assert "m.width =" in sql
        assert "m.height =" in sql
