"""
Lightweight, dependency-free data-quality and schema inspection for a
catalog source's Sample Data sheet. Not a substitute for profiling the
real underlying table (this only ever sees the sample rows shipped in the
catalog workbook) — it's meant to surface the kind of things an analyst
would want to sanity-check before requesting access: missing values,
inferred types, and obvious schema smells like inconsistent date formats.
"""

from __future__ import annotations

import pandas as pd

from . import config
from .loaders import _infer_column_type


def inspect_quality(filename: str, data_dir=config.DATA_DIR) -> dict | None:
    """
    Returns a per-column quality report for one catalog workbook's Sample
    Data sheet:

        {
          "n_rows": int,
          "columns": {
            "<col>": {
              "dtype": "numeric" | "categorical" | "date" | "identifier" | "boolean" | "text",
              "missing_count": int,
              "missing_pct": float,
              "unique_count": int,
              "warnings": [str, ...],
            }
          },
          "overall_warnings": [str, ...],
        }

    Returns None if the file/sheet can't be read.
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

    n_rows = len(df)
    columns_report: dict = {}
    overall_warnings: list[str] = []

    for col in df.columns:
        series = df[col]
        dtype = _infer_column_type(series)

        # Missing values: real NaN, or blank/whitespace-only strings.
        as_str = series.astype(str)
        is_blank = as_str.str.strip().isin(["", "nan", "None", "none", "NaT"])
        missing_count = int((series.isna() | is_blank).sum())
        missing_pct = round(100 * missing_count / n_rows, 1) if n_rows else 0.0

        unique_count = int(series.dropna().nunique())

        warnings: list[str] = []
        if missing_pct >= 20:
            warnings.append(f"{missing_pct}% missing — check if this field is reliably populated before relying on it.")
        if dtype == "identifier" and unique_count < n_rows and missing_count == 0:
            warnings.append("Expected a unique identifier, but found duplicate values in the sample.")
        if dtype == "date":
            # Flag inconsistent date formatting: parsing with a single
            # inferred format failing on some non-null values is a good
            # proxy for "this column mixes formats".
            non_null = as_str[~(series.isna() | is_blank)]
            if len(non_null) > 0:
                parsed = pd.to_datetime(non_null, errors="coerce")
                fail_rate = parsed.isna().mean()
                if 0 < fail_rate < 1:
                    warnings.append("Some values in this date column don't parse with the majority format — possible inconsistent formatting.")
        if dtype == "categorical" and unique_count == 1 and n_rows > 1:
            warnings.append("Only one distinct value appears in the sample — may be low-signal for modeling, or the sample just isn't representative.")

        columns_report[str(col)] = {
            "dtype": dtype,
            "missing_count": missing_count,
            "missing_pct": missing_pct,
            "unique_count": unique_count,
            "warnings": warnings,
        }

    # Duplicate full rows across the sample (weak signal given small sample size, but cheap to check).
    dup_count = int(df.duplicated().sum())
    if dup_count > 0:
        overall_warnings.append(f"{dup_count} fully duplicate row(s) found in the sample data.")

    return {
        "n_rows": n_rows,
        "columns": columns_report,
        "overall_warnings": overall_warnings,
    }