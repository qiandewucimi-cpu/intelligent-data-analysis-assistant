from __future__ import annotations

import hashlib
from typing import Any

import pandas as pd


def build_file_signature(file_name: str, file_bytes: bytes, sheet_name: str | None) -> str:
    """Creates a stable signature so Streamlit only reloads changed files."""

    digest = hashlib.md5(file_bytes).hexdigest()
    return f"{file_name}:{sheet_name or ''}:{digest}"


def format_dataframe_preview(df: pd.DataFrame) -> str:
    """Formats small result previews without requiring optional markdown deps."""

    try:
        return df.to_markdown(index=False)
    except Exception:
        return df.to_string(index=False)


def prepare_dataframe_for_display(df: pd.DataFrame) -> pd.DataFrame:
    """Converts mixed object columns into Arrow-safe strings for Streamlit."""

    display_df = df.copy()
    display_df.columns = [str(column) for column in display_df.columns]

    for column in display_df.columns:
        series = display_df[column]

        # Dates without a real time-of-day shouldn't show a noisy "00:00:00".
        if pd.api.types.is_datetime64_any_dtype(series):
            non_null = series.dropna()
            if not non_null.empty and bool((non_null.dt.normalize() == non_null).all()):
                display_df[column] = series.dt.strftime("%Y-%m-%d")
            else:
                display_df[column] = series.dt.strftime("%Y-%m-%d %H:%M:%S")
            continue

        if not (pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series)):
            continue

        sample_types = {type(value) for value in series.dropna().head(50)}
        has_mixed_types = len(sample_types) > 1
        has_bytes = any(value_type in {bytes, bytearray} for value_type in sample_types)

        if has_mixed_types or has_bytes:
            display_df[column] = series.map(_stringify_display_value)

    return display_df


def _stringify_display_value(value: Any) -> Any:
    """Formats non-null values as strings so Streamlit can render them reliably."""

    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    if isinstance(value, (bytes, bytearray)):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return value.hex()
    return str(value)
