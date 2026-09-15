from __future__ import annotations

from typing import Any

import pandas as pd

from analyzer.columns import OUTLIER_FLAG_COLUMN, drop_helper_columns


_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _escape_formula_value(value: Any) -> Any:
    """Keeps untrusted cell text from becoming a spreadsheet formula."""

    if not isinstance(value, str):
        return value
    if value.lstrip().startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value


def escape_spreadsheet_formulas(df: pd.DataFrame) -> pd.DataFrame:
    """Returns an export-safe copy for CSV and Excel downloads."""

    safe = df.copy()
    for column in safe.columns:
        if pd.api.types.is_object_dtype(safe[column].dtype) or isinstance(
            safe[column].dtype, pd.StringDtype
        ):
            safe[column] = safe[column].map(_escape_formula_value)
    return safe


def prepare_cleaned_export_dataframe(cleaned_df: pd.DataFrame) -> pd.DataFrame:
    """Removes cleaning-only marker columns when no row is marked as an outlier."""

    if OUTLIER_FLAG_COLUMN not in cleaned_df.columns:
        return cleaned_df
    if bool(cleaned_df[OUTLIER_FLAG_COLUMN].fillna(False).any()):
        return cleaned_df
    return drop_helper_columns(cleaned_df)
