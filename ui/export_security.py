from __future__ import annotations

from typing import Any

import pandas as pd


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
