"""
Parse a user-uploaded Excel/CSV file to extract its column headers and a
small preview. Used to auto-detect what data the user already has, so the
retrieval query can be enriched with those column names (helping surface
sources that fill in the *gaps*, not just sources matching the typed
question).
"""

from __future__ import annotations

import io

import pandas as pd


class FileParseError(RuntimeError):
    pass


def format_file_size(num_bytes: int) -> str:
    """Human-readable file size, e.g. '48.2 KB' or '1.3 MB'."""
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def parse_uploaded_file(file_bytes: bytes, filename: str) -> dict:
    """
    Parse an uploaded .xlsx/.xls/.csv file.

    Returns:
        {
            "columns": [...],          # column headers, as strings
            "n_rows": int,               # number of data rows found
            "n_columns": int,            # number of columns found
            "preview": list[dict],       # up to 10 sample rows for display
            "sheet_name": str | None,    # sheet used, for Excel files
            "file_size_bytes": int,      # raw size of the uploaded file
            "file_size_display": str,    # human-readable size, e.g. "48.2 KB"
        }
    """
    lower_name = filename.lower()
    try:
        if lower_name.endswith((".xlsx", ".xls")):
            excel_file = pd.ExcelFile(io.BytesIO(file_bytes))
            sheet_name = excel_file.sheet_names[0]
            df = excel_file.parse(sheet_name)
        elif lower_name.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(file_bytes))
            sheet_name = None
        else:
            raise FileParseError(
                f"Unsupported file type: '{filename}'. Please upload .xlsx, .xls, or .csv."
            )
    except FileParseError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise FileParseError(f"Could not read '{filename}': {exc}") from exc

    df.columns = [str(c).strip() for c in df.columns]

    return {
        "columns": list(df.columns),
        "n_rows": len(df),
        "n_columns": len(df.columns),
        "preview": df.head(10).astype(object).fillna("").astype(str).to_dict(orient="records"),
        "sheet_name": sheet_name,
        "file_size_bytes": len(file_bytes),
        "file_size_display": format_file_size(len(file_bytes)),
    }


def columns_to_query_fragment(columns: list[str]) -> str:
    """Turn a list of column headers into a short natural-language fragment
    that can be appended to a user's typed question, so the retrieval query
    reflects data they already have."""
    if not columns:
        return ""
    return f"I already have a dataset with these columns: {', '.join(columns)}."