"""Builds the grounding data (schema profile / whole-table statistics) that
engine prompts consume.  Everything here is computed from the real DataFrame
so the model reasons about actual numbers instead of guessing."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from analyzer.columns import drop_helper_columns, is_identifier_column


def build_dataframe_profile(
    df: pd.DataFrame, sample_rows: int = 5, desensitize: bool = False
) -> dict[str, Any]:
    """Builds a schema + sample + value-hint profile for LLM prompts.

    The value hints (real category spellings, numeric ranges, date ranges) let
    the model write code that matches the data instead of guessing column values.

    When ``desensitize`` is True, real row samples and real categorical values
    (which may contain names / client identities) are withheld; only column
    names, types and numeric/date ranges are kept so nothing identifiable leaves
    the machine.
    """

    source = drop_helper_columns(df)
    numeric_columns = source.select_dtypes(include=["number"]).columns.tolist()
    datetime_columns = source.select_dtypes(include=["datetime", "datetimetz"]).columns.tolist()
    categorical_columns = [
        column
        for column in source.columns
        if column not in set(numeric_columns + datetime_columns)
    ]

    column_value_hints: dict[str, Any] = {}
    for column in categorical_columns:
        series = source[column].dropna().astype(str).str.strip()
        series = series[series != ""]
        unique_values = series.unique().tolist()
        column_value_hints[column] = {
            "type": "类别",
            "unique_count": int(len(unique_values)),
            "examples": [] if desensitize else unique_values[:12],
        }
    for column in numeric_columns:
        series = source[column].dropna()
        if series.empty:
            continue
        column_value_hints[column] = {
            "type": "数值",
            "min": _to_native(series.min()),
            "max": _to_native(series.max()),
            "mean": _to_native(series.mean()),
        }
    for column in datetime_columns:
        series = source[column].dropna()
        if series.empty:
            continue
        column_value_hints[column] = {
            "type": "日期",
            "earliest": _to_native(series.min()),
            "latest": _to_native(series.max()),
        }

    return {
        "row_count": int(source.shape[0]),
        "column_count": int(source.shape[1]),
        "columns": source.columns.tolist(),
        "dtypes": {column: str(dtype) for column, dtype in source.dtypes.items()},
        "missing_values": {column: int(value) for column, value in source.isna().sum().items()},
        "numeric_columns": numeric_columns,
        "datetime_columns": datetime_columns,
        "categorical_columns": categorical_columns,
        "column_value_hints": column_value_hints,
        "sample_rows": []
        if desensitize
        else source.head(sample_rows).replace({np.nan: None}).to_dict(orient="records"),
    }


def build_analysis_statistics(
    df: pd.DataFrame, top_n: int = 8, desensitize: bool = False
) -> dict[str, Any]:
    """Computes real whole-table statistics used to ground AI answers and reports.

    Unlike the lightweight profile (schema + a few sample rows), this looks at
    every row so the model can reason about actual numbers instead of guessing.

    When ``desensitize`` is True, the real names of categorical top values
    (e.g. client / region names) are replaced by neutral labels like "取值1",
    so the distribution (counts / proportions) is preserved but identities are
    not sent to the model.
    """

    source = drop_helper_columns(df)
    numeric_columns = [
        column
        for column in source.select_dtypes(include=["number"]).columns.tolist()
        if not is_identifier_column(column)
    ]
    datetime_columns = source.select_dtypes(include=["datetime", "datetimetz"]).columns.tolist()
    categorical_columns = [
        column
        for column in source.columns
        if column not in set(numeric_columns + datetime_columns)
    ]

    numeric_stats: dict[str, Any] = {}
    for column in numeric_columns:
        series = source[column].dropna()
        if series.empty:
            continue
        numeric_stats[column] = {
            "count": int(series.shape[0]),
            "missing": int(source[column].isna().sum()),
            "min": _to_native(series.min()),
            "max": _to_native(series.max()),
            "mean": _to_native(series.mean()),
            "median": _to_native(series.median()),
            "std": _to_native(series.std()),
            "sum": _to_native(series.sum()),
        }

    categorical_stats: dict[str, Any] = {}
    for column in categorical_columns:
        series = source[column].dropna().astype(str).str.strip()
        series = series[series != ""]
        if series.empty:
            continue
        counts = series.value_counts()
        total = int(counts.sum())
        top_values = [
            {
                "value": f"取值{rank}" if desensitize else str(value),
                "count": int(count),
                "pct": round(float(count) / float(total) * 100.0, 2) if total else 0.0,
            }
            for rank, (value, count) in enumerate(counts.head(top_n).items(), start=1)
        ]
        categorical_stats[column] = {
            "unique": int(counts.shape[0]),
            "missing": int(source[column].isna().sum()),
            "top_values": top_values,
        }

    datetime_stats: dict[str, Any] = {}
    for column in datetime_columns:
        series = source[column].dropna()
        if series.empty:
            continue
        try:
            span_days = int((series.max() - series.min()).days)
        except (TypeError, ValueError, AttributeError):
            span_days = None
        datetime_stats[column] = {
            "earliest": _to_native(series.min()),
            "latest": _to_native(series.max()),
            "span_days": span_days,
            "missing": int(source[column].isna().sum()),
        }

    correlations: list[dict[str, Any]] = []
    measure_columns = [column for column in numeric_columns if source[column].nunique(dropna=True) > 1]
    if len(measure_columns) >= 2:
        corr_matrix = source[measure_columns].corr(numeric_only=True)
        seen_pairs: set[frozenset[str]] = set()
        for first in measure_columns:
            for second in measure_columns:
                if first == second:
                    continue
                pair = frozenset((first, second))
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                value = corr_matrix.loc[first, second]
                if pd.isna(value):
                    continue
                if abs(float(value)) >= 0.5:
                    correlations.append(
                        {"columns": [first, second], "correlation": round(float(value), 3)}
                    )
        correlations.sort(key=lambda item: abs(item["correlation"]), reverse=True)
        correlations = correlations[:10]

    return {
        "row_count": int(source.shape[0]),
        "column_count": int(source.shape[1]),
        "numeric_stats": numeric_stats,
        "categorical_stats": categorical_stats,
        "datetime_stats": datetime_stats,
        "correlations": correlations,
    }


def _to_native(value: Any) -> Any:
    """Casts numpy/pandas scalars to JSON-friendly Python values."""

    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return round(float(value), 4)
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    return value
