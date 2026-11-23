"""
Load data-source catalog entries from Excel workbooks (.xlsx) in
data/catalog/. Each workbook has two sheets:

    "Summary"      - key/value metadata table (Source Name, Source ID,
                     Owner / Department, Approval Contact, Access Level,
                     Update Frequency, Format, Keywords, Description)
    "Sample Data"  - header row of field names + realistic synthetic rows

The loader extracts the Summary metadata plus the field list and a small
sample-row preview from Sample Data, and builds one Chunk per workbook
(catalog entries are short enough that they never need splitting).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from . import config
from .excel_parser import format_file_size

# Maps the human-readable labels used in the "Summary" sheet's Field column
# to the internal metadata keys used throughout the rest of the app.
_SUMMARY_KEY_MAP = {
    "Source Name": "source_name",
    "Source ID": "source_id",
    "Owner / Department": "owner",
    "Approval Contact": "approval_contact",
    "Access Level": "access_level",
    "Update Frequency": "update_frequency",
    "Format": "format",
    "Keywords": "keywords",
    "Description": "description",
}

SAMPLE_PREVIEW_ROWS = 5


@dataclass
class Chunk:
    id: str
    text: str
    source: str  # filename this chunk came from
    metadata: dict = field(default_factory=dict)  # extracted catalog metadata


def _infer_column_type(series: pd.Series) -> str:
    """
    Lightweight dtype classifier for a sample-data column: used to enrich
    the embedding text (so queries mentioning "numeric price data" or
    "date field" match better) and later for feature/target suggestions
    and data-quality checks.
    """
    non_null = series.dropna()
    non_null = non_null[non_null.astype(str).str.strip() != ""]
    if non_null.empty:
        return "unknown"

    name = str(series.name).lower()
    sample = non_null.astype(str)

    # ID-like columns: name hints + mostly unique short alphanumeric codes
    if any(tok in name for tok in ("_id", "id", "vin")) and sample.nunique() / max(len(sample), 1) > 0.6:
        return "identifier"

    # Boolean-like
    lowered = set(sample.str.lower().unique())
    if lowered <= {"true", "false", "1", "0", "yes", "no"}:
        return "boolean"

    # Numeric
    numeric_coerced = pd.to_numeric(non_null, errors="coerce")
    if numeric_coerced.notna().mean() > 0.9:
        return "numeric"

    # Date-like
    if "date" in name or "month" in name:
        parsed = pd.to_datetime(sample, errors="coerce")
        if parsed.notna().mean() > 0.7:
            return "date"

    # Low-cardinality text -> categorical, else free text
    if sample.nunique() <= max(10, len(sample) // 2):
        return "categorical"

    return "text"


def _parse_workbook(path: Path) -> tuple[dict, list[str], list[dict], dict]:
    """
    Returns (metadata, field_names, sample_rows, field_types) for one
    catalog workbook. sample_rows is a list of dicts (as strings) for the
    first few rows, used to build a richer embedding text and for optional
    display. field_types maps column name -> inferred type label.
    """
    xl = pd.ExcelFile(path)

    metadata: dict = {}
    if "Summary" in xl.sheet_names:
        summary_df = pd.read_excel(xl, sheet_name="Summary")
        for _, row in summary_df.iterrows():
            label = str(row.get("Field", "")).strip()
            value = str(row.get("Value", "")).strip()
            key = _SUMMARY_KEY_MAP.get(label)
            if key:
                metadata[key] = value

    field_names: list[str] = []
    sample_rows: list[dict] = []
    field_types: dict = {}
    if "Sample Data" in xl.sheet_names:
        sample_df = pd.read_excel(xl, sheet_name="Sample Data")
        field_names = [str(c).strip() for c in sample_df.columns]
        field_types = {col: _infer_column_type(sample_df[col]) for col in sample_df.columns}
        preview_df = sample_df.head(SAMPLE_PREVIEW_ROWS).astype(object).fillna("").astype(str)
        sample_rows = preview_df.to_dict(orient="records")

    metadata["fields"] = ", ".join(field_names)
    metadata["field_types"] = ", ".join(f"{k}:{v}" for k, v in field_types.items())
    return metadata, field_names, sample_rows, field_types


def _build_document_text(
    metadata: dict, field_names: list[str], sample_rows: list[dict], field_types: dict
) -> str:
    """Combined text used both for embedding, BM25 keyword search, and as
    the LLM's source excerpt — includes description, fields with inferred
    types, business keywords/tags, and a couple of sample rows so retrieval
    can match on realistic data values and data types, not just high-level
    summary text."""
    typed_fields = [f"{name} ({field_types.get(name, 'unknown')})" for name in field_names]
    lines = [
        f"Source: {metadata.get('source_name', 'Unknown')}",
        f"Source ID: {metadata.get('source_id', '')}",
        f"Business description: {metadata.get('description', '')}",
        f"Table tags / keywords: {metadata.get('keywords', '')}",
        f"Owner: {metadata.get('owner', '')}",
        f"Fields (name and inferred data type): {', '.join(typed_fields)}",
    ]
    if sample_rows:
        lines.append("Sample rows:")
        for row in sample_rows[:3]:
            row_str = ", ".join(f"{k}={v}" for k, v in row.items())
            lines.append(f"  - {row_str}")
    return "\n".join(lines)


def load_catalog_workbooks(data_dir: Path = config.DATA_DIR) -> list[tuple[str, dict, list[str], list[dict], dict]]:
    """Return (filename, metadata, field_names, sample_rows, field_types)
    for every .xlsx workbook found in data_dir."""
    results = []
    if not data_dir.exists():
        return results

    for path in sorted(data_dir.glob("*.xlsx")):
        try:
            metadata, field_names, sample_rows, field_types = _parse_workbook(path)
        except Exception as exc:  # noqa: BLE001 - surface but don't crash ingest
            print(f"[loaders] Skipping {path.name}: {exc}")
            continue
        results.append((path.name, metadata, field_names, sample_rows, field_types))

    return results


def load_catalog_preview(filename: str, data_dir: Path = config.DATA_DIR, n_preview_rows: int = 10) -> dict | None:
    """
    Read a catalog workbook's "Sample Data" sheet for display, returning the
    same shape as excel_parser.parse_uploaded_file() so the catalog preview
    (sidebar, result cards) can reuse the exact same UI as the uploaded-file
    preview. Returns None if the file or sheet doesn't exist.
    """
    path = data_dir / filename
    if not path.exists():
        return None
    try:
        xl = pd.ExcelFile(path)
        if "Sample Data" not in xl.sheet_names:
            return None
        df = pd.read_excel(xl, sheet_name="Sample Data")
    except Exception:  # noqa: BLE001
        return None

    return {
        "columns": [str(c).strip() for c in df.columns],
        "n_rows": len(df),
        "n_columns": len(df.columns),
        "preview": df.head(n_preview_rows),
        "file_size_display": format_file_size(path.stat().st_size),
    }


def build_chunks(data_dir: Path = config.DATA_DIR) -> list[Chunk]:
    """Load every catalog workbook and build one Chunk per source."""
    all_chunks: list[Chunk] = []

    for filename, metadata, field_names, sample_rows, field_types in load_catalog_workbooks(data_dir):
        text = _build_document_text(metadata, field_names, sample_rows, field_types)
        chunk_id = hashlib.sha256(filename.encode()).hexdigest()[:16]
        all_chunks.append(Chunk(id=chunk_id, text=text, source=filename, metadata=metadata))

    return all_chunks


def get_field_types(filename: str, data_dir: Path = config.DATA_DIR) -> dict:
    """Return {column_name: inferred_type} for one catalog workbook, read
    fresh from its Sample Data sheet (used by data-quality checks and
    target/predictor feature suggestions)."""
    path = data_dir / filename
    if not path.exists():
        return {}
    try:
        xl = pd.ExcelFile(path)
        if "Sample Data" not in xl.sheet_names:
            return {}
        sample_df = pd.read_excel(xl, sheet_name="Sample Data")
        return {col: _infer_column_type(sample_df[col]) for col in sample_df.columns}
    except Exception:  # noqa: BLE001
        return {}