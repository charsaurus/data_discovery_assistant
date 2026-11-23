"""
Two-stage retrieval-augmented data-source recommendation:

  Stage 1 (fast, cheap): hybrid_query() pulls a wide pool of candidates
      (config.RERANK_POOL_SIZE) using dense vector search + BM25 keyword
      search fused via reciprocal rank fusion.

  Stage 2 (careful, expensive): the LLM re-ranks that pool down to the
      final top_k, scoring relevance, explaining why each source matches,
      suggesting target vs predictor columns, and flagging data gaps —
      all in one structured JSON response (no separate cross-encoder
      dependency needed beyond the LLM call already in use).

If the user uploaded a file, it's scored and merged into the candidate
pool as a real competing candidate (see rag/user_data.py), not just
background context — it can be re-ranked in or out like any other source.

Supports multiple LLM providers (Anthropic, Groq, Gemini, OpenRouter,
Ollama) via config.LLM_PROVIDER.
"""

from __future__ import annotations

import json
import re

from . import config
from .retrieval import hybrid_query


class NotConfiguredError(RuntimeError):
    """Raised when required setup (API key, index) is missing."""


_PROVIDER_ENV_HINT = {
    "anthropic": "ANTHROPIC_API_KEY",
    "groq": "GROQ_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}


def _require_key():
    if config.LLM_PROVIDER != "ollama" and not config.LLM_API_KEY:
        env_var = _PROVIDER_ENV_HINT.get(config.LLM_PROVIDER, "API_KEY")
        raise NotConfiguredError(
            f"{env_var} is not set for provider '{config.LLM_PROVIDER}'. "
            "Add it to your .env file or environment."
        )


def retrieve(query_text: str, pool_size: int = config.RERANK_POOL_SIZE) -> list[dict]:
    """Stage 1: hybrid (dense + sparse) retrieval, wide pool."""
    return hybrid_query(query_text, pool_size=pool_size)


def build_context_block(hits: list[dict]) -> str:
    if not hits:
        return "(no matching data sources found in the catalog)"

    blocks = []
    for hit in hits:
        uploaded_tag = " (Your Uploaded Data)" if hit.get("source_id") == "USER-UPLOAD" else ""
        blocks.append(
            f"FILENAME: {hit.get('source', 'unknown')}\n"
            f"Name: {hit.get('source_name', hit.get('source', 'Unknown source'))}{uploaded_tag}\n"
            f"Keywords: {hit.get('keywords', 'unknown')}\n"
            f"Fields: {hit.get('fields', 'unknown')}\n"
            f"Field types: {hit.get('field_types', 'unknown')}\n"
            f"Description: {hit.get('description', hit.get('text', ''))[:400]}"
        )
    return "\n\n".join(blocks)


def _call_anthropic(system_prompt: str, messages: list[dict]) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=config.LLM_API_KEY)
    # Current Claude models reject `temperature` and always think, so depth
    # is steered with `effort` instead, with headroom for thinking tokens on
    # top of the JSON answer. On a safety refusal the API re-runs the
    # request on a fallback model ("default" routing).
    response = client.beta.messages.create(
        model=config.LLM_MODEL,
        max_tokens=16000,
        output_config={"effort": "low"},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        system=system_prompt,
        messages=messages,
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("Claude declined this request (refusal). Try rephrasing your goal.")
    return "".join(block.text for block in response.content if block.type == "text")


def _call_openai_compatible(system_prompt: str, messages: list[dict]) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=config.LLM_API_KEY, base_url=config.LLM_BASE_URL)
    full_messages = [{"role": "system", "content": system_prompt}, *messages]
    response = client.chat.completions.create(
        model=config.LLM_MODEL,
        max_tokens=config.MAX_TOKENS,
        temperature=config.TEMPERATURE,
        messages=full_messages,
    )
    return response.choices[0].message.content or ""


def _strip_json_fences(text: str) -> str:
    """Some models wrap JSON in ```json ... ``` even when told not to."""
    text = text.strip()
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    return match.group(1).strip() if match else text


def _extract_first_json_object(text: str) -> str | None:
    """
    Find the first balanced {...} object in text by brace-matching (aware
    of quoted strings, so braces inside string values don't throw off the
    count). Needed because some models — especially smaller/free-tier ones
    — ignore "respond with ONLY JSON" and instead prepend their own
    self-talk/verification narration ("Let's check there are no commas
    in...", "All looks clean, proceed") before or around the actual JSON.
    Rather than fail outright, we scan for the real object wherever it is.
    """
    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
        else:
            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]
    return None  # unbalanced — likely truncated mid-object


def _load_json_with_fallbacks(raw_text: str) -> dict:
    """Try increasingly permissive strategies to find valid JSON in a raw
    LLM response, since not every provider/model follows "output ONLY
    JSON" instructions reliably. Raises json.JSONDecodeError if nothing
    works, matching json.loads()'s own failure signature so callers don't
    need a separate except clause."""
    cleaned = _strip_json_fences(raw_text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    extracted = _extract_first_json_object(raw_text)
    if extracted is not None:
        return json.loads(extracted)  # let this raise if still invalid

    # Nothing resembling a JSON object at all — surface the original error.
    return json.loads(cleaned)


def _parse_llm_json(raw_text: str, pool: list[dict], top_k: int = config.TOP_K) -> dict:
    """
    Parse the LLM's structured JSON response and merge each ranked entry's
    reasoning back onto its full candidate metadata (owner, contact, access
    level, etc. — the LLM only echoes back the filename + its own analysis,
    not metadata it didn't need to repeat).

    Returns {"ranked_sources": [...], "data_gaps": {...},
             "order_of_operations": [...], "parse_error": str | None}
    On parse failure, falls back to the raw hybrid-ranked pool (no LLM
    reasoning fields) so the UI still has something usable to show.
    """
    pool_by_source = {hit.get("source"): hit for hit in pool}

    try:
        data = _load_json_with_fallbacks(raw_text)

        ranked_sources = []
        for entry in data.get("ranked_sources", []):
            source = entry.get("source", "")
            base = dict(pool_by_source.get(source, {"source": source}))
            base.update({
                "relevance_score": entry.get("relevance_score", 0),
                "why_it_matches": entry.get("why_it_matches", ""),
                "target_variable_columns": entry.get("target_variable_columns", []),
                "predictor_feature_columns": entry.get("predictor_feature_columns", []),
                "fields_to_request": entry.get("fields_to_request", []),
                "overlap_with_existing": entry.get("overlap_with_existing", ""),
                "join_key_suggestion": entry.get("join_key_suggestion", ""),
            })
            ranked_sources.append(base)

        return {
            "ranked_sources": ranked_sources,
            "data_gaps": data.get("data_gaps", {}),
            "order_of_operations": data.get("order_of_operations", []),
            "parse_error": None,
        }
    except (json.JSONDecodeError, AttributeError, TypeError) as exc:
        # Fallback: show the hybrid-ranked pool as-is, no LLM reasoning.
        fallback_sources = []
        for hit in pool[:top_k]:
            base = dict(hit)
            base.setdefault("relevance_score", round(hit.get("hybrid_score", 0) * 1000))
            base.setdefault("why_it_matches", "")
            base.setdefault("target_variable_columns", [])
            base.setdefault("predictor_feature_columns", [])
            base.setdefault("fields_to_request", [])
            base.setdefault("overlap_with_existing", "")
            base.setdefault("join_key_suggestion", "")
            fallback_sources.append(base)

        return {
            "ranked_sources": fallback_sources,
            "data_gaps": {},
            "order_of_operations": [],
            "parse_error": str(exc),
        }


def find_data_sources(
    query_text: str,
    existing_columns: list[str] | None = None,
    uploaded_source: dict | None = None,
    chat_history: list[dict] | None = None,
    top_k: int = config.TOP_K,
    pool_size: int = config.RERANK_POOL_SIZE,
) -> dict:
    """
    Given a user's description of what they're trying to build:
      1. Retrieve a wide candidate pool via hybrid (dense + sparse) search.
      2. Merge in the uploaded file (if any) as a real competing candidate.
      3. Ask the LLM to re-rank the pool down to top_k, with per-source
         relevance scoring, target/predictor column suggestions, and a
         data-gap analysis, returned as structured JSON.

    Returns:
        {
          "ranked_sources": list[dict],   # each hit's full metadata + LLM reasoning fields
          "data_gaps": dict,              # {"missing_info": ..., "suggested_additional_sources": ...}
          "order_of_operations": list[str],
          "pool": list[dict],             # the full stage-1 candidate pool (for debugging/filters)
          "parse_error": str | None,      # set if the LLM's JSON couldn't be parsed
          "raw_response": str,
        }
    """
    _require_key()

    retrieval_query = query_text
    if existing_columns:
        retrieval_query = f"{query_text} Related data columns: {', '.join(existing_columns)}"

    pool = retrieve(retrieval_query, pool_size=pool_size)

    if uploaded_source is not None:
        pool = [uploaded_source] + pool

    context = build_context_block(pool)
    system_prompt = config.SYSTEM_PROMPT.format(
        org_name=config.ORG_NAME, context=context, pool_size=len(pool), top_k=top_k
    )

    if existing_columns:
        user_message = (
            f"GOAL: {query_text}\n\n"
            f"MY EXISTING DATA — I already have a dataset with these columns: "
            f"{', '.join(existing_columns)}"
        )
    else:
        user_message = f"GOAL: {query_text}"

    messages = list(chat_history or [])
    messages.append({"role": "user", "content": user_message})

    try:
        if config.LLM_PROVIDER == "anthropic":
            raw_response = _call_anthropic(system_prompt, messages)
        else:
            raw_response = _call_openai_compatible(system_prompt, messages)
    except Exception as exc:  # noqa: BLE001
        provider = config.LLM_PROVIDER
        hint = ""
        if provider == "ollama":
            hint = " Is Ollama running locally (`ollama serve`) with the model pulled?"
        raise RuntimeError(f"Error calling {provider} ({config.LLM_MODEL}): {exc}.{hint}") from exc

    parsed = _parse_llm_json(raw_response, pool, top_k=top_k)
    parsed["pool"] = pool
    parsed["raw_response"] = raw_response
    return parsed