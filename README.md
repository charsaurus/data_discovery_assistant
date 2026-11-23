# Data Source Discovery Assistant

A RAG tool for **data mapping / data discovery**: describe a project you
want to build (a model, a dashboard, an analysis), optionally upload data
you already have, and it searches a catalog of internal data sources to
tell you which ones to request access to — including who owns each source,
what fields it has, and how to combine it with what you've got.

The demo domain is a fictional car dealer group ("ABC Motors Group")
with an 18-source synthetic data catalog spanning customer behaviour,
market pricing, sales, marketing, and more. Each source is an actual Excel
workbook (`.xlsx`) with a "Summary" tab (description, owner, keywords,
etc.) and a "Sample Data" tab (realistic synthetic rows), so you can open
any source and see exactly what it would look like — not just read a
description of it. Swap in your own organization's real sources by
following the same two-tab template.

**Stack:** Streamlit (UI) · ChromaDB (vector store, local) ·
sentence-transformers (embeddings, local & free) · pandas/openpyxl (Excel
parsing) · Groq / Gemini / OpenRouter / Anthropic / Ollama (LLM, pick one)

## Features

- **Two-stage retrieval:** hybrid semantic + BM25 keyword search pulls a
  wide candidate pool, then the LLM re-ranks it with a 0-100 relevance
  score and a short reason for each source.
- **Feature mapping:** suggests target vs. predictor columns per source.
- **Data gap analysis:** what the goal needs that no source provides.
- **Bring your own data:** an uploaded Excel/CSV competes as a real
  candidate, and its columns steer the search toward what's missing.
- **Filters:** by access tier, owner/department and update frequency.
- **Data quality check:** missing values, types and flags per source.
- **Code generation:** select sources to get starter SQL / pandas join
  code and a JSON export of owners and approval contacts.

## Example use case

> "I want to build a decision tree to determine the best strategy to sell
> cars, so I need data on customer behaviour and market prices."

The app retrieves the catalog entries whose descriptions/keywords/fields
best match that goal (e.g. *Customer Purchase History*, *Website
Clickstream*, *Test Drive Booking Logs*, *Regional Market Price Index*,
*Competitor Pricing Feed*), then explains why each is relevant, which
fields to pull, how to join them (e.g. on `customer_id` or `model`), and
who to contact for approval.

If you upload an Excel/CSV of data you already have, its column headers
are automatically folded into the search so the assistant can point you
toward sources that fill in what's *missing*, not just sources that sound
generically relevant.

## How it works

```
data/catalog/*.xlsx  --parse Summary + Sample Data--> embed locally --store--> ChromaDB
  (owner, contact,                                                                |
   access level,                                                                  |
   fields, sample rows)                                                           |
                                                                                    |
user's goal + (optional) uploaded file  --embed-->  similarity search <-----------+
  (uploaded file also scored and competes                |
   as a real candidate, not just context)          candidate data sources
                                        |
                            LLM (Groq/Gemini/etc.)
                                        |
                    relevance explanation + join suggestions
                       (+ structured source cards: owner,
                        approval contact, access level, fields)
```

## Setup

1. **Install dependencies** (Python 3.10+ recommended):

   ```bash
   python -m venv .venv
   source .venv/bin/activate   # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Pick an LLM provider and add its key:**

   ```bash
   cp .env.example .env
   ```

   Edit `.env` and set `LLM_PROVIDER` to one of:

   | Provider | Cost | Get a key |
   |---|---|---|
   | `groq` *(default)* | Free, no card | https://console.groq.com/keys |
   | `gemini` | Free, no card | https://aistudio.google.com/apikey |
   | `openrouter` | Free tier | https://openrouter.ai/keys |
   | `anthropic` | Paid | https://console.anthropic.com/settings/keys |
   | `ollama` | Free, local, no key | Install [Ollama](https://ollama.com), `ollama pull llama3.2`, `ollama serve` |

3. **Build the catalog index:**

   ```bash
   python -m rag.ingest
   ```

4. **Run the app:**

   ```bash
   streamlit run app.py
   ```

5. **Try it:** type a goal like the example above, optionally upload
   `sample_user_data/my_existing_sales_data.xlsx` (included) to see the
   gap-filling behavior, and click **Find data sources**.

## Project layout

```
app.py                          Streamlit UI: upload + query + results
build_catalog_excel.py          One-off script that generated the 18
                                   synthetic catalog workbooks (re-run to
                                   regenerate, or use as a template for
                                   scripting your own real catalog)
rag/
  config.py                      Settings: LLM provider, system prompt
  loaders.py                     Reads catalog .xlsx workbooks (Summary +
                                   Sample Data tabs), extracts structured
                                   metadata and builds one chunk per source
  vectorstore.py                 ChromaDB wrapper: index + similarity search,
                                   carries metadata through to query results
  excel_parser.py                Parses uploaded .xlsx/.xls/.csv, extracts
                                   column headers/preview for the UI
  user_data.py                   Scores the uploaded file itself as a
                                   competing candidate source
  ingest.py                      CLI: python -m rag.ingest
  bm25_search.py                 Keyword (BM25) search over the catalog
  retrieval.py                   Hybrid retrieval: dense + BM25 fused with
                                   reciprocal rank fusion
  generate.py                    Stage-2 LLM re-ranking: relevance scores,
                                   target/predictor columns, data gaps (JSON)
  facets.py                      Normalizes access levels into filter tiers
  data_quality.py                Per-source schema / missing-value checks
  codegen.py                     Starter SQL / pandas join code for the
                                   sources you select
data/catalog/                   18 synthetic data-source workbooks (edit or
                                   add your own — see template below)
sample_user_data/                Example Excel file to test the upload flow
tests/                           Offline unit tests (no API key needed)
storage/                         Auto-created; persisted vector index (gitignored)
```

## Adding your own data sources

Each catalog entry is an `.xlsx` workbook with two sheets. The loader
reads both by exact sheet name and by the labels in the Summary sheet's
`Field` column, so keep those consistent:

**Sheet 1 — "Summary"** (two columns: `Field`, `Value`)

| Field | Value |
|---|---|
| Source Name | *e.g. Customer Purchase History (CRM)* |
| Source ID | *e.g. SRC-019* |
| Owner / Department | *who owns this data* |
| Approval Contact | *email to request access* |
| Access Level | *e.g. Internal — Requires Manager Approval* |
| Update Frequency | *e.g. Daily* |
| Format | *e.g. SQL table* |
| Keywords | *comma-separated search terms* |
| Description | *free text: what this contains, when to use it* |

**Sheet 2 — "Sample Data"** — a normal data table: header row = field
names, followed by a handful of realistic sample rows (5-15 is plenty).
This is what makes each source feel like real data rather than just a
description — retrieval also matches against these sample values.

The easiest way to build one is to copy the pattern in
`build_catalog_excel.py` (add a new entry to `SOURCES` + a `gen_0NN()`
row generator) and re-run it, or just build the `.xlsx` by hand in Excel
following the two sheets above. Either way, drop the file into
`data/catalog/`, re-run `python -m rag.ingest`, and it's searchable.

## Running tests

```bash
pip install pytest
python -m pytest tests
```

## Customizing

- **Recommendation instructions:** edit `SYSTEM_PROMPT` in `rag/config.py`.
- **How many sources retrieved per query:** `TOP_K` in `rag/config.py`
  (also adjustable live via the sidebar slider in the app).
- **How many sample rows per source:** `N_SAMPLE_ROWS` in
  `build_catalog_excel.py` (only affects regeneration of the synthetic
  catalog — irrelevant if you're building your own `.xlsx` sources by hand).
- **LLM provider/model:** set `LLM_PROVIDER` in `.env`, and optionally
  `GROQ_MODEL` / `GEMINI_MODEL` / `OPENROUTER_MODEL` / `OLLAMA_MODEL`.
- **Response consistency:** `TEMPERATURE` in `rag/config.py` (lower = more
  consistent formatting, useful for smaller free-tier models).
- **Organization name:** `ORG_NAME` in `.env`.

## Troubleshooting

- **"X_API_KEY is not set for provider 'x'"** — check `.env` has a real
  key for your chosen `LLM_PROVIDER`, and you're running from the project
  root so `.env` is found.
- **Ollama connection errors** — make sure `ollama serve` is running and
  you've pulled the model.
- **"Catalog index is empty"** — run `python -m rag.ingest`.
- **First ingest run is slow** — downloading the embedding model (~90MB)
  once; subsequent runs are fast.
- **Upload errors** — only `.xlsx`, `.xls`, and `.csv` are supported;
  the file needs a normal header row in the first row of the first sheet.
