from __future__ import annotations

from typing import Any

import streamlit as st

from analyzer.columns import OUTLIER_FIELDS_COLUMN, OUTLIER_FLAG_COLUMN
from ui.charts import build_chart_bundle
from ui.data_handler import CleaningOptions, clean_dataframe


def init_session_state() -> None:
    """Initializes Streamlit session keys once."""

    defaults: dict[str, Any] = {
        "file_signature": "",
        "file_name": "",
        "raw_df": None,
        "cleaned_df": None,
        "cleaning_report": {},
        "cleaning_options": default_cleaning_options(),
        "cleaning_applied": False,
        "query_result": None,
        "chart_bundle": {},
        "analysis_report": "",
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def default_cleaning_options() -> dict[str, Any]:
    """Returns the default interactive cleaning configuration."""

    return {
        # 基础整理：推荐默认开启（基本不会动坏数据）
        "strip_text": True,
        "convert_datetime": True,
        "convert_numeric_text": True,
        # 按需处理：默认关闭，需用户主动选择
        "remove_duplicates": False,
        "fill_missing": False,
        "mark_outliers": False,
        "missing_numeric_strategy": "median",
        "missing_text_strategy": "mode",
        "missing_datetime_strategy": "ffill_bfill",
    }


def apply_cleaning() -> None:
    """Applies the currently selected cleaning options to the raw dataframe."""

    if st.session_state.raw_df is None:
        return

    option_payload = {
        key: value
        for key, value in (st.session_state.cleaning_options or default_cleaning_options()).items()
        if key != "applied"
    }
    options = CleaningOptions(**option_payload)
    cleaned_df, cleaning_report = clean_dataframe(st.session_state.raw_df, options=options)
    default_chart_bundle = build_chart_bundle(cleaned_df) if not cleaned_df.empty else {}

    st.session_state.cleaned_df = cleaned_df
    st.session_state.cleaning_report = cleaning_report.to_dict()
    st.session_state.query_result = None
    st.session_state.analysis_report = ""
    st.session_state.chart_bundle = default_chart_bundle


def reset_cleaning_to_raw_state() -> None:
    """Resets the cleaned dataframe back to the raw uploaded data."""

    if st.session_state.raw_df is None:
        return

    raw_df = st.session_state.raw_df.copy()
    raw_df[OUTLIER_FLAG_COLUMN] = False
    raw_df[OUTLIER_FIELDS_COLUMN] = ""

    st.session_state.cleaned_df = raw_df
    st.session_state.cleaning_report = {
        "original_rows": int(raw_df.shape[0]),
        "cleaned_rows": int(raw_df.shape[0]),
        "duplicate_rows_removed": 0,
        "duplicate_row_indices": [],
        "missing_values_filled": {column: 0 for column in raw_df.columns if column not in {OUTLIER_FLAG_COLUMN, OUTLIER_FIELDS_COLUMN}},
        "missing_fill_strategies": {column: "未处理" for column in raw_df.columns if column not in {OUTLIER_FLAG_COLUMN, OUTLIER_FIELDS_COLUMN}},
        "converted_datetime_columns": [],
        "converted_numeric_columns": [],
        "outlier_counts": {},
        "total_outlier_rows": 0,
        "outlier_row_indices": [],
        "skipped_outlier_columns": [],
        "option_summary": {**default_cleaning_options()},
        "total_missing_filled": 0,
    }
    st.session_state.query_result = None
    st.session_state.analysis_report = ""
    st.session_state.chart_bundle = {}
