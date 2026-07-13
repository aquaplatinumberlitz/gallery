"""Shared backend/frontend search query grammar contract vectors.

Purpose:
Consume the neutral search-query grammar fixture from pytest so backend and
frontend parsing behavior cannot drift independently.

Guarantees:
Residual text, field values, operators, quote style, and normalized keys match
the shared contract vectors.

Run when:
Changing fielded-search parsing, escaping, operators, or shared grammar data.
"""

from __future__ import annotations

import json
from pathlib import Path

from backend.fielded_search_parser import parse_fielded_query

FIXTURE = Path(__file__).resolve().parents[2] / "test-data" / "search-query-grammar.json"


def test_backend_consumes_shared_search_query_grammar_fixture() -> None:
    document = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert document["contract_version"] == 1

    for case in document["cases"]:
        parsed = parse_fielded_query(case["query"])
        assert parsed.residual_text == case["residual_text"], case["name"]
        assert [
            {
                "field": token.field,
                "value": token.value,
                "operator": token.operator,
                "quote_char": token.quote_char,
                "key": token.key,
            }
            for token in parsed.fields
        ] == case["backend_fields"], case["name"]
