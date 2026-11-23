"""
Generate starter SQL / pandas code to join a set of user-selected data
sources on shared key columns, so finding the right sources turns
immediately into a usable starting point for actually combining them.

Join-key detection is intentionally simple and transparent: it looks for
column names shared across two or more selected sources (case-insensitive
exact match — e.g. "customer_id" appearing in both). This is a reasonable
heuristic for a demo catalog with consistent naming; real-world schemas
with inconsistent naming would need the LLM's `join_key_suggestion` field
(from generate.py) as a supplementary hint, which the UI surfaces
alongside this.
"""

from __future__ import annotations

from collections import defaultdict


def _fields_list(hit: dict) -> list[str]:
    raw = hit.get("fields", "")
    return [f.strip() for f in raw.split(",") if f.strip()]


def _table_alias(source_name: str, index: int) -> str:
    """Short, readable SQL alias, e.g. 'dealer_sales_transactions' -> 't1_dealer_sales'."""
    slug = "".join(ch if ch.isalnum() else "_" for ch in source_name.lower())
    slug = "_".join(part for part in slug.split("_") if part)[:24]
    return f"t{index}_{slug}" if slug else f"t{index}"


# Preferred join keys, most row-level/specific first — e.g. joining on
# customer_id preserves one row per customer, while a generic key like
# branch_id would fan out into a many-to-many join. Checked in order;
# first match present in the shared keys wins.
_PREFERRED_JOIN_KEYS = ["customer_id", "vin", "sale_id", "booking_id"]


def _pick_join_key(shared_keys: dict) -> str | None:
    if not shared_keys:
        return None
    for preferred in _PREFERRED_JOIN_KEYS:
        if preferred in shared_keys:
            return preferred
    # Otherwise prefer any other "_id"-suffixed key (deterministic: shortest, then alphabetical).
    id_like = sorted([k for k in shared_keys if k.endswith("_id")], key=lambda k: (len(k), k))
    if id_like:
        return id_like[0]
    return next(iter(shared_keys))


def detect_shared_keys(selected: list[dict]) -> dict[str, list[str]]:
    """
    Returns {column_name: [source filenames that contain it]} for every
    column that appears (case-insensitive) in 2 or more selected sources —
    i.e. plausible join keys.
    """
    column_to_sources: dict[str, list[str]] = defaultdict(list)
    for hit in selected:
        source = hit.get("source", hit.get("source_name", "unknown"))
        for field_name in _fields_list(hit):
            column_to_sources[field_name.lower()].append(source)

    return {col: sources for col, sources in column_to_sources.items() if len(sources) >= 2}


def generate_sql(selected: list[dict]) -> str:
    """Starter SQL joining selected sources on any shared key columns
    (falls back to a commented note if no shared keys are found)."""
    if not selected:
        return "-- Select at least one data source to generate a query."
    if len(selected) == 1:
        hit = selected[0]
        table = hit.get("source_id", hit.get("source", "table")).lower().replace("-", "_")
        fields = _fields_list(hit)
        cols = ",\n    ".join(fields) if fields else "*"
        return f"SELECT\n    {cols}\nFROM {table};"

    shared_keys = detect_shared_keys(selected)

    aliases = {
        hit.get("source", hit.get("source_name", f"source_{i}")): _table_alias(
            hit.get("source_name", hit.get("source", f"source_{i}")), i
        )
        for i, hit in enumerate(selected, start=1)
    }

    select_lines = []
    for hit in selected:
        source = hit.get("source", hit.get("source_name"))
        alias = aliases[source]
        for f in _fields_list(hit):
            select_lines.append(f"{alias}.{f} AS {alias}_{f}")

    lines = ["SELECT"]
    lines.append("    " + ",\n    ".join(select_lines) if select_lines else "    *")
    lines.append(f"FROM {selected[0].get('source_id', selected[0].get('source', 'table1')).lower().replace('-', '_')} AS {aliases[selected[0].get('source', selected[0].get('source_name'))]}")

    used_key = _pick_join_key(shared_keys)

    for hit in selected[1:]:
        source = hit.get("source", hit.get("source_name"))
        alias = aliases[source]
        first_alias = aliases[selected[0].get("source", selected[0].get("source_name"))]
        table_name = hit.get("source_id", source).lower().replace("-", "_")
        if used_key and used_key in [f.lower() for f in _fields_list(hit)] and used_key in [
            f.lower() for f in _fields_list(selected[0])
        ]:
            lines.append(f"JOIN {table_name} AS {alias}\n    ON {alias}.{used_key} = {first_alias}.{used_key}")
        else:
            lines.append(f"-- JOIN {table_name} AS {alias}  -- no obvious shared key detected; verify manually")

    lines.append(";")
    sql = "\n".join(lines)

    if not shared_keys:
        sql = (
            "-- No shared column names were detected across your selected sources.\n"
            "-- Check each source's 'join_key_suggestion' from the recommendation for a likely (differently-named) key.\n\n"
            + sql
        )
    return sql


def generate_pandas(selected: list[dict]) -> str:
    """Starter pandas code reading + merging selected sources on any
    shared key columns."""
    if not selected:
        return "# Select at least one data source to generate code."

    lines = ["import pandas as pd", ""]
    var_names = []
    for i, hit in enumerate(selected, start=1):
        source = hit.get("source", "")
        var = f"df_{i}"
        var_names.append((var, hit))
        path = source if hit.get("source_id") == "USER-UPLOAD" else f"data/catalog/{source}"
        lines.append(f"{var} = pd.read_excel('{path}', sheet_name='Sample Data')  # {hit.get('source_name', source)}")

    lines.append("")

    if len(selected) == 1:
        lines.append(f"df = {var_names[0][0]}")
        return "\n".join(lines)

    shared_keys = detect_shared_keys(selected)
    used_key = _pick_join_key(shared_keys)

    first_fields = [f.lower() for f in _fields_list(var_names[0][1])]
    if used_key and used_key not in first_fields:
        # The shared key only links later sources; merging it onto df_1
        # would raise a KeyError, so fall back to the manual-merge hint.
        used_key = None

    if used_key:
        lines.append(f"# Merging on shared key: '{used_key}'")
        merged_var = var_names[0][0]
        for var, hit in var_names[1:]:
            fields = [f.lower() for f in _fields_list(hit)]
            if used_key in fields:
                lines.append(f"{merged_var} = {merged_var}.merge({var}, on='{used_key}', how='left', suffixes=('', '_{var}'))")
            else:
                lines.append(f"# {var} ({hit.get('source_name', '')}) doesn't contain '{used_key}' — verify the right join key before merging")
        lines.append("")
        lines.append(f"df = {merged_var}")
    else:
        lines.append("# No shared column names detected across your selected sources.")
        lines.append("# Check each source's 'join_key_suggestion' from the recommendation for a likely (differently-named) key,")
        lines.append("# then merge manually, e.g.:")
        lines.append(f"# df = {var_names[0][0]}.merge({var_names[1][0]}, left_on='...', right_on='...', how='left')")

    return "\n".join(lines)