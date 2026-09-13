from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from analyzer.columns import OUTLIER_FIELDS_COLUMN, OUTLIER_FLAG_COLUMN


def build_cleaning_action_summary(cleaning_report: dict[str, Any]) -> list[str]:
    """Builds human-readable cleaning steps for non-technical users."""

    actions: list[str] = []
    option_summary = cleaning_report.get("option_summary", {})

    if not st.session_state.get("cleaning_applied", False):
        return ["当前还是原始数据，系统还没有对你的数据做任何清洗。"]

    if option_summary:
        enabled_actions = []
        if option_summary.get("strip_text"):
            enabled_actions.append("去除文本首尾空格")
        if option_summary.get("convert_datetime"):
            enabled_actions.append("识别日期")
        if option_summary.get("convert_numeric_text"):
            enabled_actions.append("识别数字文本")
        if option_summary.get("remove_duplicates"):
            enabled_actions.append("删除重复行")
        if option_summary.get("fill_missing"):
            enabled_actions.append("填充缺失值")
        if option_summary.get("mark_outliers"):
            enabled_actions.append("标记异常值")
        actions.append(f"这次启用了这些清洗动作：{'、'.join(enabled_actions) if enabled_actions else '未启用任何动作'}。")

    duplicate_count = int(cleaning_report.get("duplicate_rows_removed", 0))
    actions.append(f"删除重复行：{duplicate_count} 行。")

    datetime_columns = cleaning_report.get("converted_datetime_columns", [])
    if datetime_columns:
        actions.append(f"识别成日期的字段：{', '.join(datetime_columns)}。")

    numeric_columns = cleaning_report.get("converted_numeric_columns", [])
    if numeric_columns:
        actions.append(f"识别成数值的字段：{', '.join(numeric_columns)}。")

    total_missing_filled = int(cleaning_report.get("total_missing_filled", 0))
    actions.append(f"填充缺失值：{total_missing_filled} 个。")

    total_outlier_rows = int(cleaning_report.get("total_outlier_rows", 0))
    if option_summary.get("mark_outliers", True):
        actions.append(f"标记异常值：{total_outlier_rows} 行。")

    skipped_outlier_columns = cleaning_report.get("skipped_outlier_columns", [])
    if skipped_outlier_columns:
        actions.append(f"这些更像编号的字段没有参与异常值判断：{', '.join(skipped_outlier_columns)}。")

    return actions


def build_cleaning_column_summary(cleaning_report: dict[str, Any]) -> pd.DataFrame:
    """Builds a field-level summary of what the cleaning step changed."""

    missing_values_filled = cleaning_report.get("missing_values_filled", {})
    missing_fill_strategies = cleaning_report.get("missing_fill_strategies", {})
    outlier_counts = cleaning_report.get("outlier_counts", {})
    datetime_columns = set(cleaning_report.get("converted_datetime_columns", []))
    numeric_columns = set(cleaning_report.get("converted_numeric_columns", []))

    all_columns = sorted(
        set(missing_values_filled)
        | set(missing_fill_strategies)
        | set(outlier_counts)
        | datetime_columns
        | numeric_columns
    )

    rows: list[dict[str, Any]] = []
    for column in all_columns:
        converted_labels: list[str] = []
        if column in datetime_columns:
            converted_labels.append("转成日期")
        if column in numeric_columns:
            converted_labels.append("转成数值")

        rows.append(
            {
                "字段": column,
                "字段转换": "、".join(converted_labels) if converted_labels else "未转换",
                "填充缺失值数量": int(missing_values_filled.get(column, 0)),
                "缺失值处理方式": missing_fill_strategies.get(column, "未处理"),
                "异常值命中数量": int(outlier_counts.get(column, 0)),
            }
        )

    return pd.DataFrame(rows)


def build_duplicate_preview(raw_df: pd.DataFrame | None, duplicate_row_indices: list[int], limit: int = 20) -> pd.DataFrame:
    """Shows a small preview of rows removed as duplicates."""

    if raw_df is None or not duplicate_row_indices:
        return pd.DataFrame()

    preview = raw_df.iloc[duplicate_row_indices].copy().head(limit)
    preview.insert(0, "原始行号", duplicate_row_indices[: len(preview)])
    return preview


def build_change_summary(
    raw_df: pd.DataFrame,
    cleaned_df: pd.DataFrame,
    cleaning_report: dict[str, Any],
    limit: int = 100,
    performance_mode: str = "full",
) -> dict[str, list[dict[str, Any]]]:
    """Builds a compact list of visible changes instead of showing two full tables only."""

    changed_cells: list[dict[str, Any]] = []
    removed_rows: list[dict[str, Any]] = []
    flagged_rows: list[dict[str, Any]] = []

    duplicate_row_indices = cleaning_report.get("duplicate_row_indices", [])
    if duplicate_row_indices:
        removed_preview = raw_df.iloc[duplicate_row_indices].copy()
        removed_preview.insert(0, "原始行号", duplicate_row_indices[: len(removed_preview)])
        removed_rows = removed_preview.head(limit).to_dict(orient="records")

    comparable_raw = raw_df.drop(index=duplicate_row_indices, errors="ignore").reset_index(drop=True)
    comparable_cleaned = cleaned_df.drop(columns=[OUTLIER_FLAG_COLUMN, OUTLIER_FIELDS_COLUMN], errors="ignore").reset_index(drop=True)

    shared_columns = [column for column in comparable_raw.columns if column in comparable_cleaned.columns]
    shared_row_count = min(len(comparable_raw), len(comparable_cleaned))
    if performance_mode == "light":
        shared_row_count = min(shared_row_count, 200)
    elif performance_mode == "medium":
        shared_row_count = min(shared_row_count, 1000)

    candidate_columns = _pick_change_candidate_columns(cleaning_report, shared_columns)

    for row_index in range(shared_row_count):
        for column in candidate_columns:
            before_value = comparable_raw.iloc[row_index][column]
            after_value = comparable_cleaned.iloc[row_index][column]
            if _values_equal(before_value, after_value):
                continue

            changed_cells.append(
                {
                    "行号": row_index,
                    "字段": column,
                    "清洗前": _display_value(before_value),
                    "清洗后": _display_value(after_value),
                }
            )

    if OUTLIER_FLAG_COLUMN in cleaned_df.columns:
        flagged_preview = cleaned_df[cleaned_df[OUTLIER_FLAG_COLUMN]].copy().head(limit)
        if not flagged_preview.empty:
            flagged_preview.insert(0, "清洗后行号", flagged_preview.index.tolist())
            flagged_rows = flagged_preview.to_dict(orient="records")

    return {
        "changed_cells": changed_cells[: max(limit * 20, 200)],
        "removed_rows": removed_rows,
        "flagged_rows": flagged_rows,
    }


def _pick_change_candidate_columns(cleaning_report: dict[str, Any], shared_columns: list[str]) -> list[str]:
    """Limits expensive comparisons to columns that are likely to have changed."""

    preferred_columns = (
        list(cleaning_report.get("converted_datetime_columns", []))
        + list(cleaning_report.get("converted_numeric_columns", []))
        + [
            column
            for column, count in cleaning_report.get("missing_values_filled", {}).items()
            if int(count) > 0
        ]
    )
    filtered = [column for column in dict.fromkeys(preferred_columns) if column in shared_columns]
    return filtered or shared_columns[: min(10, len(shared_columns))]


def get_cleaning_performance_mode(raw_df: pd.DataFrame) -> str:
    """Chooses a lighter comparison mode for large datasets."""

    cell_count = int(raw_df.shape[0] * raw_df.shape[1])
    if cell_count >= 200000:
        return "light"
    if cell_count >= 50000:
        return "medium"
    return "full"


def _values_equal(before_value: Any, after_value: Any) -> bool:
    """Compares values safely across strings, numbers, datetimes, and missing values."""

    if pd.isna(before_value) and pd.isna(after_value):
        return True
    return before_value == after_value


def _display_value(value: Any) -> Any:
    """Formats values for the visible change list."""

    if pd.isna(value):
        return "空值"
    return str(value)
