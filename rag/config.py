"""
Central configuration for the Data Source Discovery RAG app.
Edit these constants to tune behavior without touching the rest of the code.
"""

import os
from pathlib import Path

# --- Paths -----------------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data" / "catalog"     # synthetic data-source catalog entries
INDEX_DIR = ROOT_DIR / "storage" / "chroma"  # persisted vector index lives here

# --- Chunking ----------------------------------------------------------------
# Catalog entries are short, self-contained write-ups of a single data
# source. We want each one to stay as ONE chunk so its metadata (owner,
# approval contact, fields) is never split away from part of its
# description. 2000 chars comfortably covers every entry in data/catalog/.
CHUNK_SIZE = 2000
CHUNK_OVERLAP = 150

# --- Embeddings --------------------------------------------------------------
# Runs locally via sentence-transformers, no API key or cost.
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"

# --- Retrieval -----------------------------------------------------------------
TOP_K = 5  # number of final data sources shown to the user per query
RERANK_POOL_SIZE = 20  # candidates pulled by fast hybrid retrieval before LLM re-ranking

# --- Generation ----------------------------------------------------------------
# Pick a provider by setting LLM_PROVIDER in your .env (or leave the default).
#   anthropic  -> Claude API (paid, needs ANTHROPIC_API_KEY)
#   groq       -> Free hosted Llama/Mixtral, very fast (needs GROQ_API_KEY)
#   gemini     -> Google's free tier, generous quota (needs GEMINI_API_KEY)
#   openrouter -> One key, many free community models (needs OPENROUTER_API_KEY)
#   ollama     -> Fully local, no key, no cost, no rate limit.
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "groq").lower()

MAX_TOKENS = 3200  # structured JSON output (rerank + reasoning + gaps) runs longer than plain prose; extra headroom in case a model leaks preamble text before the actual JSON
TEMPERATURE = 0.3  # lower = more consistent formatting, especially for small free-tier models

_PROVIDER_DEFAULTS = {
    "anthropic": {
        "base_url": None,
        "model": "claude-opus-5-5",
        "api_key_env": "ANTHROPIC_API_KEY",
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "model": "llama-3.3-70b-versatile",
        "api_key_env": "GROQ_API_KEY",
    },
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "model": "gemini-2.5-flash",
        "api_key_env": "GEMINI_API_KEY",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "model": "meta-llama/llama-3.1-8b-instruct:free",
        "api_key_env": "OPENROUTER_API_KEY",
    },
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "model": "llama3.2",
        "api_key_env": None,
    },
}

if LLM_PROVIDER not in _PROVIDER_DEFAULTS:
    raise ValueError(
        f"Unknown LLM_PROVIDER '{LLM_PROVIDER}'. Choose one of: "
        f"{', '.join(_PROVIDER_DEFAULTS)}"
    )

_provider_cfg = _PROVIDER_DEFAULTS[LLM_PROVIDER]

LLM_BASE_URL = _provider_cfg["base_url"]
LLM_MODEL = os.environ.get(f"{LLM_PROVIDER.upper()}_MODEL", _provider_cfg["model"])
LLM_API_KEY = (
    os.environ.get(_provider_cfg["api_key_env"], "") if _provider_cfg["api_key_env"] else "ollama"
)

COLLECTION_NAME = "data_source_catalog"

# --- Org / domain framing ---------------------------------------------------
ORG_NAME = os.environ.get("ORG_NAME", "ABC Motors")

SYSTEM_PROMPT = """You are a data-mapping assistant for {org_name}, acting as a \
re-ranking and reasoning engine over a candidate pool of data sources. A \
user describes a project goal and, optionally, columns from data they \
already have (labeled "MY EXISTING DATA" in their message — this may \
include a candidate marked "(Your Uploaded Data)" below, meaning they \
already have that exact dataset locally, no request needed for it).

You are given up to {pool_size} CANDIDATE sources below, already \
retrieved by a hybrid (semantic + keyword) search. Your job is a SECOND, \
more careful pass: pick and re-order the best {top_k} (or fewer, if fewer \
truly fit) of them for this specific goal, and explain your reasoning.

Respond with ONLY a single JSON object. Your first character must be {{ \
and your last character must be }}. Do not include markdown code fences, \
prose before or after, or any commentary. Do not narrate your reasoning, \
double-check, or verify your own output out loud — just produce the \
final JSON directly. Match EXACTLY this shape:

{{
  "ranked_sources": [
    {{
      "source": "<the exact source filename from the candidates, e.g. source_007_dealer_sales_transactions.xlsx>",
      "relevance_score": <integer 0-100, your honest calibrated confidence this source belongs in the result set for THIS goal>,
      "why_it_matches": "<2-3 sentences, specific to this goal, referencing actual field names>",
      "target_variable_columns": ["<column names from this source that could serve as a prediction TARGET for the stated goal, if any — empty list if none>"],
      "predictor_feature_columns": ["<column names from this source useful as PREDICTOR/feature columns for the stated goal>"],
      "fields_to_request": ["<field_name_1>", "<field_name_2>"],
      "overlap_with_existing": "<name any of the user's existing columns that likely correspond to this source's fields, matching by meaning even if named differently; if this candidate IS the user's own uploaded data, say 'You already have this — no request needed'; otherwise 'None noted'>",
      "join_key_suggestion": "<a plausible column to join this source with others in your ranked list or the user's existing data, e.g. customer_id>"
    }}
  ],
  "data_gaps": {{
    "missing_info": "<1-3 sentences: what critical information the stated goal needs that NONE of the candidate sources provide — be specific, e.g. 'no source captures competitor test-drive volume'>",
    "suggested_additional_sources": "<1-2 sentences: what kind of external or additional internal data would close that gap>"
  }},
  "order_of_operations": ["<step 1>", "<step 2>", "<step 3, optional>"]
}}

Rules:
- Only include a source in "ranked_sources" if it is a genuine, meaningful fit — do not pad the list to reach {top_k}.
- relevance_score should be well-calibrated and use the FULL 0-100 range: a source that is central to the goal deserves 80-95+, a source that's tangentially useful deserves 40-65, don't cluster everything in the 40-50 range out of caution.
- target_variable_columns should usually be empty for sources that are purely contextual/enrichment data — only fill it in when a column is a plausible thing to PREDICT.
- Do not invent sources not present in the candidates below. Do not invent column names not present in a source's field list.
- If NONE of the candidates genuinely fit, return an empty "ranked_sources" list and explain why in "data_gaps".
- Your entire response is parsed programmatically as JSON. Any text outside the {{...}} object — including self-checks like "let me verify this is valid" — will break the parser. Output the object and nothing else.

Candidate data sources:
{context}
"""