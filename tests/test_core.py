"""Offline tests: no LLM key or vector index needed."""

from rag.codegen import detect_shared_keys, generate_pandas, generate_sql
from rag.facets import TIER_APPROVAL, TIER_OPEN, TIER_RESTRICTED, classify_access_tier, sort_tiers
from rag.generate import _extract_first_json_object, _parse_llm_json
from rag.loaders import build_chunks
from rag import config


def _hit(source, fields, **extra):
    return {"source": source, "source_name": source, "fields": fields, **extra}


def test_catalog_loads_all_sources_with_metadata():
    chunks = build_chunks(config.DATA_DIR)
    assert len(chunks) == 18
    for c in chunks:
        assert c.metadata.get("owner") and c.metadata.get("fields")


def test_shared_keys_and_join():
    a = _hit("a.xlsx", "customer_id, price", source_id="SRC-1")
    b = _hit("b.xlsx", "customer_id, visits", source_id="SRC-2")
    assert detect_shared_keys([a, b]) == {"customer_id": ["a.xlsx", "b.xlsx"]}
    assert "ON t2_b_xlsx.customer_id = t1_a_xlsx.customer_id" in generate_sql([a, b])
    code = generate_pandas([a, b])
    assert "pd.read_excel('data/catalog/a.xlsx'" in code
    assert "df_1.merge(df_2, on='customer_id'" in code


def test_pandas_skips_key_missing_from_first_source():
    a = _hit("a.xlsx", "price")
    b = _hit("b.xlsx", "customer_id")
    c = _hit("c.xlsx", "customer_id")
    code = generate_pandas([a, b, c])
    assert ".merge(" not in code.replace("# df = df_1.merge", "")


def test_access_tiers():
    assert classify_access_tier("Internal — Requires Manager Approval") == TIER_APPROVAL
    assert classify_access_tier("Restricted — Requires Compliance Approval") == TIER_RESTRICTED
    assert classify_access_tier("Open — no approval needed") == TIER_OPEN
    assert sort_tiers([TIER_RESTRICTED, TIER_OPEN]) == [TIER_OPEN, TIER_RESTRICTED]


def test_json_parsing_tolerates_chatter_and_falls_back():
    pool = [{"source": "x.xlsx", "owner": "Sales", "hybrid_score": 0.03}]
    raw = 'Sure! {"ranked_sources": [{"source": "x.xlsx", "relevance_score": 88}]} hope this helps'
    assert _extract_first_json_object('a {"b": "}"} c') == '{"b": "}"}'
    ok = _parse_llm_json(raw, pool)
    assert ok["parse_error"] is None and ok["ranked_sources"][0]["owner"] == "Sales"
    bad = _parse_llm_json("not json at all", pool)
    assert bad["parse_error"] and bad["ranked_sources"][0]["source"] == "x.xlsx"
