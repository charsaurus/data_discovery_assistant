"""
Streamlit UI for the Data Source Discovery Assistant.

Layout:
    Sidebar   -> status + catalog browser + upload your data
    Main area -> catalog/upload preview, query box, then results:
                 data-gap analysis, filter controls, ranked source cards
                 (relevance score, target/predictor columns, data quality),
                 and a selection panel with SQL/pandas code generation.

Retrieval is two-stage: a wide hybrid (dense + BM25) pool is pulled fast,
then the LLM re-ranks it down to the final top_k with structured reasoning
(rag/generate.py). The uploaded file competes as a real candidate in that
pool, not just background context (rag/user_data.py).

Run with:
    streamlit run app.py
"""

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from rag import config
from rag.generate import find_data_sources, NotConfiguredError
from rag.vectorstore import collection_stats, list_ingested_sources
from rag.loaders import load_catalog_preview
from rag.excel_parser import parse_uploaded_file, FileParseError
from rag.user_data import score_uploaded_file, UPLOADED_SOURCE_ID
from rag.data_quality import inspect_quality
from rag.codegen import generate_sql, generate_pandas, detect_shared_keys
from rag.facets import classify_access_tier, sort_tiers

st.set_page_config(page_title="Data Discovery Assistant", page_icon="🗂️", layout="wide")

st.title("🗂️ Data Discovery Assistant")
st.caption(
    f"Demo catalog for {config.ORG_NAME}. Upload data you already have from the sidebar, "
    "preview it below, then describe what you're trying to build to find which internal "
    "data sources you should request."
)

# --- Main area: preview a catalog source selected from the sidebar -----------
selected_source = st.session_state.get("selected_catalog_source")
if selected_source:
    src_meta = next(
        (s for s in list_ingested_sources() if s.get("source") == selected_source), None
    )
    if src_meta:
        st.subheader(f"📊 Preview: {selected_source}")
        description = src_meta.get("description", "")
        if description and description != "unknown":
            st.caption(description)

        preview = load_catalog_preview(selected_source)
        if preview is not None:
            m1, m2, m3 = st.columns(3)
            m1.metric("Rows", preview["n_rows"])
            m2.metric("Columns", preview["n_columns"])
            m3.metric("File size", preview["file_size_display"])

            st.markdown("**Column names:** " + ", ".join(preview["columns"]))

            if preview["preview"] is not None:
                st.dataframe(preview["preview"], use_container_width=True)
        else:
            st.caption("No sample data available for this source.")

        with st.expander("Summary / access details"):
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"**Owner / Department:** {src_meta.get('owner', 'unknown')}")
                st.markdown(f"**Approval Contact:** {src_meta.get('approval_contact', 'unknown')}")
                st.markdown(f"**Access Level:** {src_meta.get('access_level', 'unknown')}")
            with col2:
                st.markdown(f"**Update Frequency:** {src_meta.get('update_frequency', 'unknown')}")
                st.markdown(f"**Format:** {src_meta.get('format', 'unknown')}")
                st.markdown(f"**Source ID:** {src_meta.get('source_id', 'unknown')}")
            st.markdown(f"**Keywords:** {src_meta.get('keywords', 'unknown')}")

        dl_col, close_col = st.columns([1, 1])
        with dl_col:
            xlsx_path = config.DATA_DIR / selected_source
            if xlsx_path.exists():
                st.download_button(
                    "⬇️ Download workbook",
                    data=xlsx_path.read_bytes(),
                    file_name=xlsx_path.name,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="dl_main_preview",
                )
        with close_col:
            if st.button("✕ Close preview"):
                st.session_state.pop("selected_catalog_source", None)
                st.rerun()

    st.divider()

# --- Sidebar: status + upload -------------------------------------------------
with st.sidebar:
    st.header("Status")
    st.caption(f"Provider: **{config.LLM_PROVIDER}** · Model: `{config.LLM_MODEL}`")

    if config.LLM_PROVIDER == "ollama":
        st.info("Using local Ollama — make sure `ollama serve` is running and the model is pulled.")
    elif not config.LLM_API_KEY:
        st.error(
            f"No API key found for provider '{config.LLM_PROVIDER}'. "
            "Add it to your .env file (see .env.example)."
        )
    else:
        st.success(f"{config.LLM_PROVIDER.capitalize()} API key detected.")

    try:
        stats = collection_stats()
        if stats["count"] == 0:
            st.warning(
                "Catalog index is empty.\n\n"
                "Run `python -m rag.ingest` in your terminal, then refresh this page."
            )
        else:
            st.info(f"Catalog index: {stats['count']} data sources.")
    except Exception as exc:  # noqa: BLE001
        st.warning(f"Vector store not ready yet: {exc}")

    st.divider()
    st.subheader("📚 Catalog sources")
    st.caption("Click a source to preview it in the main area, below the title.")
    ingested = list_ingested_sources()
    if not ingested:
        st.caption("Nothing ingested yet.")
    else:
        for src in ingested:
            col1, col2 = st.columns([4, 1])
            with col1:
                if st.button(
                    src.get("source_name", src.get("source")),
                    key=f"select_{src.get('source')}",
                    use_container_width=True,
                ):
                    st.session_state["selected_catalog_source"] = src.get("source")
                    st.rerun()
            with col2:
                xlsx_path = config.DATA_DIR / src.get("source", "")
                if xlsx_path.exists():
                    st.download_button(
                        "⬇️",
                        data=xlsx_path.read_bytes(),
                        file_name=xlsx_path.name,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key=f"dl_{src.get('source')}",
                    )

    st.divider()

    # --- Upload: bring a local file into the system -----------------------
    st.subheader("📤 Upload your data")
    st.caption(
        "Bring in a local Excel/CSV file. It's scored against your search just like a "
        "catalog source, and shows up in results if it's actually relevant."
    )
    uploaded_file = st.file_uploader(
        "Choose a file",
        type=["xlsx", "xls", "csv"],
        label_visibility="collapsed",
    )

    st.divider()
    st.subheader("Search settings")
    top_k = st.slider("Sources to keep after re-ranking", min_value=2, max_value=10, value=config.TOP_K)
    pool_size = st.slider(
        "Candidate pool size (stage 1)", min_value=top_k, max_value=20, value=config.RERANK_POOL_SIZE,
        help="How many candidates hybrid search retrieves before the LLM re-ranks them down to the number above.",
    )

    if st.button("Clear everything"):
        st.session_state.pop("last_result", None)
        st.session_state.pop("selected_catalog_source", None)
        st.session_state.pop("selected_datasets", None)
        st.rerun()

# --- Main area: preview the uploaded file --------------------------------------
uploaded_columns: list[str] = []
uploaded_meta: dict | None = None

if uploaded_file is not None:
    try:
        parsed = parse_uploaded_file(uploaded_file.getvalue(), uploaded_file.name)
        uploaded_columns = parsed["columns"]
        uploaded_meta = parsed

        st.subheader(f"📊 Preview: {uploaded_file.name}")

        m1, m2, m3 = st.columns(3)
        m1.metric("Rows", parsed["n_rows"])
        m2.metric("Columns", parsed["n_columns"])
        m3.metric("File size", parsed["file_size_display"])

        st.markdown("**Column names:** " + ", ".join(uploaded_columns))

        if parsed["preview"]:
            st.dataframe(parsed["preview"], use_container_width=True)

    except FileParseError as exc:
        st.error(str(exc))
else:
    st.info("Upload an Excel or CSV file from the sidebar to preview it here — or skip straight to searching below.")

st.divider()

# --- Query input -------------------------------------------------------------
st.subheader("What are you trying to build?")
query_text = st.text_area(
    "Describe your goal",
    placeholder=(
        "e.g. I want to build a decision tree to determine the best strategy to sell cars. "
        "I need data on customer behaviour and market prices."
    ),
    height=100,
    label_visibility="collapsed",
)

search_clicked = st.button("🔍 Find data sources", type="primary")

# --- Run search -------------------------------------------------------------------
if search_clicked:
    if not query_text.strip():
        st.warning("Describe what you're trying to build first.")
    else:
        with st.spinner("Searching the data catalog (hybrid retrieval + LLM re-ranking)..."):
            try:
                uploaded_source = None
                if uploaded_meta is not None:
                    uploaded_source = score_uploaded_file(
                        query_text.strip(),
                        filename=uploaded_file.name,
                        columns=uploaded_columns,
                        n_rows=uploaded_meta["n_rows"],
                        file_size_display=uploaded_meta["file_size_display"],
                    )

                result = find_data_sources(
                    query_text.strip(),
                    existing_columns=uploaded_columns or None,
                    uploaded_source=uploaded_source,
                    top_k=top_k,
                    pool_size=pool_size,
                )
                st.session_state["last_result"] = result
                st.session_state["last_query"] = query_text.strip()
                st.session_state["selected_datasets"] = set()
            except NotConfiguredError as exc:
                st.error(str(exc))
            except Exception as exc:  # noqa: BLE001
                st.error(f"Something went wrong: {exc}")

# --- Display results ------------------------------------------------------------
if "last_result" in st.session_state:
    result = st.session_state["last_result"]
    ranked_sources = result.get("ranked_sources", [])
    selected_datasets: set = st.session_state.setdefault("selected_datasets", set())

    st.divider()

    if result.get("parse_error"):
        st.warning(
            "The model's response couldn't be parsed as structured JSON, so these results are "
            "ranked by hybrid retrieval score only (no LLM reasoning, target/predictor columns, "
            "or gap analysis for this run). Try again, or check `raw_response` in the returned "
            "result if this keeps happening with your current provider/model."
        )
        with st.expander("Raw model response (for debugging)"):
            st.code(result.get("raw_response", ""), language=None)

    # --- Data gap analysis ---------------------------------------------------
    data_gaps = result.get("data_gaps") or {}
    if data_gaps.get("missing_info") or data_gaps.get("suggested_additional_sources"):
        st.subheader("📋 Data Gap Analysis")
        if data_gaps.get("missing_info"):
            st.markdown(f"**What's missing:** {data_gaps['missing_info']}")
        if data_gaps.get("suggested_additional_sources"):
            st.markdown(f"**Consider sourcing:** {data_gaps['suggested_additional_sources']}")
        st.divider()

    st.subheader(f"Matched data sources ({len(ranked_sources)})")

    if not ranked_sources:
        st.info("No matching data sources found. Try rephrasing your goal or broadening the description.")

    # --- Filter & facet controls ---------------------------------------------
    if ranked_sources:
        all_tiers = sort_tiers([classify_access_tier(h.get("access_level", "")) for h in ranked_sources])
        all_owners = sorted({h.get("owner", "unknown") for h in ranked_sources if h.get("owner")})
        all_freqs = sorted({h.get("update_frequency", "unknown") for h in ranked_sources if h.get("update_frequency")})

        f1, f2, f3 = st.columns(3)
        with f1:
            tier_filter = st.multiselect("Access level", options=all_tiers, default=all_tiers)
        with f2:
            owner_filter = st.multiselect("Owner / Department", options=all_owners, default=all_owners)
        with f3:
            freq_filter = st.multiselect("Update frequency", options=all_freqs, default=all_freqs)

        def _passes_filters(hit: dict) -> bool:
            if hit.get("source_id") == UPLOADED_SOURCE_ID:
                return True  # your own uploaded data is never filtered out
            tier_ok = classify_access_tier(hit.get("access_level", "")) in tier_filter
            owner_ok = hit.get("owner", "unknown") in owner_filter or not owner_filter
            freq_ok = hit.get("update_frequency", "unknown") in freq_filter or not freq_filter
            return tier_ok and owner_ok and freq_ok

        filtered_sources = [h for h in ranked_sources if _passes_filters(h)]
        if len(filtered_sources) < len(ranked_sources):
            st.caption(f"Showing {len(filtered_sources)} of {len(ranked_sources)} sources after filters.")
    else:
        filtered_sources = []

    for hit in filtered_sources:
        source_key = hit.get("source", hit.get("source_name", ""))
        is_uploaded = hit.get("source_id") == UPLOADED_SOURCE_ID
        icon = "✅" if is_uploaded else "📁"
        badge = "  ·  already yours" if is_uploaded else ""
        relevance = hit.get("relevance_score")
        score_label = f"  ·  {relevance}% relevance" if relevance is not None else ""

        header = f"{icon} {hit.get('source_name', source_key)}{score_label}{badge}"
        with st.expander(header):
            sel_col, _ = st.columns([1, 5])
            with sel_col:
                checked = st.checkbox(
                    "Select",
                    value=source_key in selected_datasets,
                    key=f"chk_{source_key}",
                )
            if checked:
                selected_datasets.add(source_key)
            else:
                selected_datasets.discard(source_key)

            if is_uploaded:
                st.success("This is your uploaded data — you already have it, no approval needed.")
                st.markdown(f"**Fields:** {hit.get('fields', 'unknown')}")
                st.markdown(f"**Details:** {hit.get('format', 'unknown')}")
            else:
                why = hit.get("why_it_matches", "")
                if why:
                    st.markdown("**Why this matches your query:**")
                    st.markdown(why)

                target_cols = hit.get("target_variable_columns") or []
                predictor_cols = hit.get("predictor_feature_columns") or []
                if target_cols or predictor_cols:
                    st.markdown("**Feature & column mapping**")
                    if target_cols:
                        st.markdown("🎯 **Target variable candidate(s):** " + ", ".join(f"`{c}`" for c in target_cols))
                    if predictor_cols:
                        st.markdown("🧩 **Predictor feature(s):** " + ", ".join(f"`{c}`" for c in predictor_cols))

                join_key = hit.get("join_key_suggestion", "")
                overlap = hit.get("overlap_with_existing", "")
                if join_key or overlap:
                    st.caption(
                        (f"Join key suggestion: `{join_key}`. " if join_key else "")
                        + (f"Overlap with your existing data: {overlap}" if overlap else "")
                    )

                d_rank = hit.get("dense_rank")
                s_rank = hit.get("sparse_rank")
                if d_rank is not None or s_rank is not None:
                    st.caption(
                        f"Retrieval signals — semantic rank: {d_rank or '—'}, keyword rank: {s_rank or '—'}"
                    )

                st.markdown("---")
                st.markdown("**Summary**")
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown(f"**Owner / Department:** {hit.get('owner', 'unknown')}")
                    st.markdown(f"**Approval Contact:** {hit.get('approval_contact', 'unknown')}")
                    st.markdown(f"**Access Level:** {hit.get('access_level', 'unknown')}")
                with col2:
                    st.markdown(f"**Update Frequency:** {hit.get('update_frequency', 'unknown')}")
                    st.markdown(f"**Format:** {hit.get('format', 'unknown')}")
                    st.markdown(f"**Source ID:** {hit.get('source_id', 'unknown')}")

                description = hit.get("description", "")
                if description and description != "unknown":
                    st.markdown(f"**Description:** {description}")

                st.markdown(f"**Keywords:** {hit.get('keywords', 'unknown')}")

                st.markdown("**Sample Data**")
                preview = load_catalog_preview(source_key)
                if preview is not None and preview["preview"] is not None:
                    st.dataframe(preview["preview"], use_container_width=True)
                else:
                    st.caption("No sample data available for this source.")

                # --- Data quality / schema inspection ---------------------
                quality = inspect_quality(source_key)
                if quality is not None:
                    col_warnings = [
                        (col, w) for col, info in quality["columns"].items() for w in info["warnings"]
                    ]
                    total_warnings = len(col_warnings) + len(quality["overall_warnings"])
                    with st.expander(f"⚠️ Data quality & schema check ({total_warnings} flag(s))"):
                        if not total_warnings:
                            st.caption("No obvious issues detected in the sample data.")
                        for w in quality["overall_warnings"]:
                            st.warning(w)
                        for col, w in col_warnings:
                            st.warning(f"**{col}** — {w}")
                        st.caption("Per-column summary:")
                        quality_rows = [
                            {
                                "column": col,
                                "type": info["dtype"],
                                "missing %": info["missing_pct"],
                                "unique values": info["unique_count"],
                            }
                            for col, info in quality["columns"].items()
                        ]
                        st.dataframe(quality_rows, use_container_width=True, hide_index=True)

    # --- Order of operations ---------------------------------------------------
    order_of_operations = result.get("order_of_operations") or []
    if order_of_operations:
        st.divider()
        st.subheader("Suggested order of operations")
        for i, step in enumerate(order_of_operations, start=1):
            st.markdown(f"{i}. {step}")

    # --- Selected datasets: codegen + export -----------------------------------
    if selected_datasets:
        st.divider()
        st.subheader(f"🧰 Selected datasets ({len(selected_datasets)})")

        selected_hits = [h for h in ranked_sources if h.get("source", h.get("source_name")) in selected_datasets]
        st.markdown(", ".join(f"**{h.get('source_name', h.get('source'))}**" for h in selected_hits))

        shared_keys = detect_shared_keys(selected_hits)
        if shared_keys and len(selected_hits) > 1:
            st.caption("Shared columns detected across selection: " + ", ".join(f"`{k}`" for k in shared_keys))

        tab_sql, tab_pandas, tab_export = st.tabs(["Generate SQL", "Generate Pandas", "Export selection"])
        with tab_sql:
            st.code(generate_sql(selected_hits), language="sql")
        with tab_pandas:
            st.code(generate_pandas(selected_hits), language="python")
        with tab_export:
            import json as _json

            export_payload = _json.dumps(
                [
                    {
                        "source": h.get("source"),
                        "source_name": h.get("source_name"),
                        "source_id": h.get("source_id"),
                        "fields": h.get("fields"),
                        "owner": h.get("owner"),
                        "approval_contact": h.get("approval_contact"),
                    }
                    for h in selected_hits
                ],
                indent=2,
            )
            st.caption("Hand this off to a downstream workflow (EDA dashboard, AutoML builder, ticket system, etc.)")
            st.download_button(
                "⬇️ Download selection.json",
                data=export_payload,
                file_name="selected_datasets.json",
                mime="application/json",
            )
            st.code(export_payload, language="json")