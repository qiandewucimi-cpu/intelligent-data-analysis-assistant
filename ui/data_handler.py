"""UI-shell data loading and the interactive cleaning pipeline.

Pure engine concerns (prompt profiles, whole-table statistics, column
semantics) live in :mod:`analyzer.profile` / :mod:`analyzer.columns`; this
module keeps what the demo shell owns: reading files and cleaning them."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from io import BytesIO
from typing import Any, Literal

import numpy as np
import pandas as pd

from analyzer.columns import (
    HELPER_COLUMNS,
    OUTLIER_FIELDS_COLUMN,
    OUTLIER_FLAG_COLUMN,
    is_identifier_column,
)

__all__ = [
    "HELPER_COLUMNS",
    "OUTLIER_FIELDS_COLUMN",
    "OUTLIER_FLAG_COLUMN",
    "CleaningOptions",
    "CleaningReport",
    "clean_dataframe",
    "list_excel_sheets",
    "load_dataframe",
    "looks_like_messy_header",
]

MissingNumericStrategy = Literal["median", "mean", "zero", "skip"]
MissingTextStrategy = Literal["mode", "unknown", "empty", "skip"]
MissingDatetimeStrategy = Literal["ffill_bfill", "epoch", "skip"]


@dataclass(frozen=True)
class CleaningOptions:
    """User-configurable cleaning options."""

    strip_text: bool = True
    convert_datetime: bool = True
    convert_numeric_text: bool = True
    remove_duplicates: bool = True
    fill_missing: bool = True
    mark_outliers: bool = True
    missing_numeric_strategy: MissingNumericStrategy = "median"
    missing_text_strategy: MissingTextStrategy = "mode"
    missing_datetime_strategy: MissingDatetimeStrategy = "ffill_bfill"


@dataclass
class CleaningReport:
    """Captures what happened during cleaning."""

    original_rows: int
    cleaned_rows: int
    duplicate_rows_removed: int
    duplicate_row_indices: list[int]
    missing_values_filled: dict[str, int]
    missing_fill_strategies: dict[str, str]
    converted_datetime_columns: list[str]
    converted_numeric_columns: list[str]
    outlier_counts: dict[str, int]
    total_outlier_rows: int
    outlier_row_indices: list[int]
    skipped_outlier_columns: list[str]
    option_summary: dict[str, Any]

    @property
    def total_missing_filled(self) -> int:
        return int(sum(self.missing_values_filled.values()))

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["total_missing_filled"] = self.total_missing_filled
        return payload


def list_excel_sheets(file_bytes: bytes) -> list[str]:
    """Returns sheet names from an uploaded Excel file."""

    workbook = pd.ExcelFile(BytesIO(file_bytes))
    return workbook.sheet_names


def load_dataframe(
    file_bytes: bytes,
    file_name: str,
    sheet_name: str | None = None,
    header_row: int = 0,
) -> pd.DataFrame:
    """Loads CSV or Excel content into a DataFrame.

    header_row is the 0-based row index that holds the real column names; rows
    above it (titles, blank lines from Excel exports) are skipped.
    """

    suffix = file_name.lower()
    buffer = BytesIO(file_bytes)
    header = header_row if header_row and header_row > 0 else 0

    if suffix.endswith(".csv"):
        frame = _read_csv_with_encoding_fallback(file_bytes, header)
    elif suffix.endswith(".xlsx") or suffix.endswith(".xls"):
        # sheet_name=None would return a dict of every sheet; default to the first one.
        sheet = sheet_name if sheet_name is not None else 0
        frame = pd.read_excel(buffer, sheet_name=sheet, header=header)
    else:
        raise ValueError("仅支持上传 CSV、XLS、XLSX 文件。")

    # Excel/CSV reports often carry fully-empty leading/trailing rows and columns.
    frame = frame.dropna(axis=0, how="all").dropna(axis=1, how="all").reset_index(drop=True)
    return frame


def _read_csv_with_encoding_fallback(file_bytes: bytes, header: int) -> pd.DataFrame:
    """Reads a CSV trying several encodings.

    Excel on Chinese Windows saves CSV as GBK/GB2312 by default, so a plain
    utf-8 read raises UnicodeDecodeError. We try the common encodings in order
    and fall back to a lenient utf-8 read that never crashes.
    """

    encodings = ["utf-8-sig", "utf-8", "gb18030", "gbk", "big5"]
    last_error: Exception | None = None
    for encoding in encodings:
        try:
            return pd.read_csv(BytesIO(file_bytes), header=header, encoding=encoding)
        except (UnicodeDecodeError, UnicodeError) as exc:
            last_error = exc
            continue
    # Last resort: decode loosely so the user at least gets their data in.
    try:
        return pd.read_csv(BytesIO(file_bytes), header=header, encoding="utf-8", encoding_errors="replace")
    except Exception as exc:  # pragma: no cover - defensive
        raise last_error or exc


def looks_like_messy_header(df: pd.DataFrame) -> bool:
    """True when many columns are auto-named (Unnamed: N), i.e. the header row is wrong."""

    if df.shape[1] == 0:
        return False
    unnamed = sum(1 for column in df.columns if str(column).startswith("Unnamed"))
    return unnamed / df.shape[1] >= 0.5


def clean_dataframe(
    df: pd.DataFrame,
    options: CleaningOptions | None = None,
) -> tuple[pd.DataFrame, CleaningReport]:
    """Cleans a DataFrame using user-configurable options."""

    config = options or CleaningOptions()
    working_df = df.copy()
    original_rows = int(working_df.shape[0])

    converted_datetime_columns: list[str] = []
    converted_numeric_columns: list[str] = []

    if config.strip_text:
        working_df = _strip_text_columns(working_df)

    if config.convert_datetime:
        working_df, converted_datetime_columns = _convert_possible_datetime_columns(working_df)

    if config.convert_numeric_text:
        working_df, converted_numeric_columns = _convert_possible_numeric_columns(working_df)

    duplicate_row_indices: list[int] = []
    duplicates_removed = 0
    if config.remove_duplicates:
        duplicate_mask = working_df.duplicated()
        duplicate_row_indices = duplicate_mask[duplicate_mask].index.tolist()
        duplicates_removed = int(duplicate_mask.sum())
        working_df = working_df.drop_duplicates().reset_index(drop=True)

    if config.fill_missing:
        missing_filled, missing_fill_strategies = _fill_missing_values(working_df, config)
    else:
        missing_filled = {column: 0 for column in working_df.columns}
        missing_fill_strategies = {column: "未处理" for column in working_df.columns}

    if config.mark_outliers:
        outlier_counts, total_outlier_rows, outlier_row_indices, skipped_outlier_columns = _mark_outliers(working_df)
    else:
        working_df[OUTLIER_FLAG_COLUMN] = False
        working_df[OUTLIER_FIELDS_COLUMN] = ""
        outlier_counts = {}
        total_outlier_rows = 0
        outlier_row_indices = []
        skipped_outlier_columns = []

    report = CleaningReport(
        original_rows=original_rows,
        cleaned_rows=int(working_df.shape[0]),
        duplicate_rows_removed=duplicates_removed,
        duplicate_row_indices=duplicate_row_indices,
        missing_values_filled=missing_filled,
        missing_fill_strategies=missing_fill_strategies,
        converted_datetime_columns=converted_datetime_columns,
        converted_numeric_columns=converted_numeric_columns,
        outlier_counts=outlier_counts,
        total_outlier_rows=total_outlier_rows,
        outlier_row_indices=outlier_row_indices,
        skipped_outlier_columns=skipped_outlier_columns,
        option_summary=asdict(config),
    )

    return working_df, report


def _strip_text_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Trims leading/trailing whitespace from text cells (keeps non-text values intact)."""

    working_df = df.copy()
    for column in working_df.columns:
        if _is_textual_dtype(working_df[column]):
            working_df[column] = working_df[column].map(
                lambda value: value.strip() if isinstance(value, str) else value
            )
    return working_df


def _convert_possible_datetime_columns(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Converts text columns to datetime if most values look parseable."""

    working_df = df.copy()
    converted_columns: list[str] = []

    for column in working_df.columns:
        series = working_df[column]
        if not _is_textual_dtype(series):
            continue

        non_null_series = series.dropna()
        non_null_count = int(non_null_series.shape[0])
        if non_null_count == 0:
            continue

        sample = non_null_series.astype(str).head(min(non_null_count, 50)).str.strip()
        if not _looks_like_datetime_sample(sample):
            continue

        converted = pd.to_datetime(series, errors="coerce", format="mixed")
        parse_ratio = float(converted.notna().sum()) / float(non_null_count)
        if parse_ratio >= 0.8:
            working_df[column] = converted
            converted_columns.append(column)

    return working_df, converted_columns


def _convert_possible_numeric_columns(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Converts numeric-like text columns such as currency and percentages."""

    working_df = df.copy()
    converted_columns: list[str] = []

    for column in working_df.columns:
        series = working_df[column]
        if not _is_textual_dtype(series):
            continue

        # Never turn identifiers (ids, phone numbers, postal codes) into numbers:
        # doing so loses precision and shows them in scientific notation.
        if is_identifier_column(column):
            continue

        non_null_series = series.dropna()
        if non_null_series.empty:
            continue

        sample = non_null_series.astype(str).head(min(non_null_series.shape[0], 50)).str.strip()
        if not _looks_like_numeric_sample(sample):
            continue

        text = series.astype(str).str.strip()
        # Accounting notation: a value fully wrapped in parentheses is negative, e.g. "(100)" -> -100.
        paren_negative_mask = text.str.match(r"^\(.*\)$").fillna(False)

        cleaned_text = (
            text.replace({"": np.nan, "nan": np.nan, "None": np.nan, "null": np.nan})
            .str.replace(",", "", regex=False)
            .str.replace("%", "", regex=False)
            .str.replace(r"[￥¥$€£]", "", regex=True)
            .str.replace(r"\s+", "", regex=True)
            .str.replace(r"[()]", "", regex=True)
        )
        converted = pd.to_numeric(cleaned_text, errors="coerce")
        converted = converted.where(~paren_negative_mask, -converted.abs())
        parse_ratio = float(converted.notna().sum()) / float(non_null_series.shape[0])

        if parse_ratio >= 0.8:
            if sample.str.contains("%", regex=False).sum() / float(sample.shape[0]) >= 0.6:
                converted = converted / 100.0
            working_df[column] = converted
            converted_columns.append(column)

    return working_df, converted_columns


def _looks_like_datetime_sample(sample: pd.Series) -> bool:
    """Skips obviously non-datetime text columns before expensive parsing."""

    if sample.empty:
        return False

    datetime_hint_count = sample.str.contains(
        r"\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}:\d{2}|年|月|日",
        regex=True,
    ).sum()
    return float(datetime_hint_count) / float(sample.shape[0]) >= 0.6


def _looks_like_numeric_sample(sample: pd.Series) -> bool:
    """Checks whether a text sample mostly behaves like numeric content."""

    if sample.empty:
        return False

    normalized = (
        sample.str.replace(",", "", regex=False)
        .str.replace("%", "", regex=False)
        .str.replace(r"[￥¥$€£]", "", regex=True)
        .str.replace(r"\s+", "", regex=True)
        .str.replace(r"[()]", "", regex=True)
    )
    numeric_like_count = normalized.str.match(r"^-?\d+(\.\d+)?$").sum()
    return float(numeric_like_count) / float(sample.shape[0]) >= 0.8


def _is_textual_dtype(series: pd.Series) -> bool:
    """Treats pandas string dtype the same as object text columns."""

    return pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series)


# Filling a column that is mostly empty just fabricates data, so we refuse to.
HIGH_MISSING_RATIO = 0.6


def _fill_missing_values(
    df: pd.DataFrame,
    options: CleaningOptions,
) -> tuple[dict[str, int], dict[str, str]]:
    """Fills null values by column type, skipping mostly-empty columns to avoid faking data."""

    filled_counts: dict[str, int] = {}
    strategies: dict[str, str] = {}
    total_rows = int(df.shape[0])

    for column in df.columns:
        series = df[column]
        missing_count = int(series.isna().sum())
        missing_ratio = (missing_count / total_rows) if total_rows else 0.0
        filled_counts[column] = 0

        if pd.api.types.is_datetime64_any_dtype(series):
            strategy = options.missing_datetime_strategy
            base_text = _get_datetime_strategy_text(strategy)
        elif pd.api.types.is_numeric_dtype(series):
            strategy = options.missing_numeric_strategy
            base_text = _get_numeric_strategy_text(strategy)
        else:
            strategy = options.missing_text_strategy
            base_text = _get_text_strategy_text(strategy)

        strategies[column] = base_text

        if missing_count == 0 or strategy == "skip":
            continue

        if missing_ratio > HIGH_MISSING_RATIO:
            strategies[column] = f"缺失高达 {missing_ratio:.0%}，未填充（避免整列编造数据）"
            continue

        if pd.api.types.is_datetime64_any_dtype(series):
            df[column] = _fill_datetime_series(series, strategy)
        elif pd.api.types.is_numeric_dtype(series):
            df[column] = _fill_numeric_series(series, strategy)
        else:
            df[column] = _fill_text_series(series, strategy)
        filled_counts[column] = missing_count

    return filled_counts, strategies


def _fill_datetime_series(series: pd.Series, strategy: MissingDatetimeStrategy) -> pd.Series:
    if strategy == "skip":
        return series
    if strategy == "epoch":
        return series.fillna(pd.Timestamp("1970-01-01"))

    filled = series.ffill().bfill()
    if filled.isna().any():
        filled = filled.fillna(pd.Timestamp("1970-01-01"))
    return filled


def _fill_numeric_series(series: pd.Series, strategy: MissingNumericStrategy) -> pd.Series:
    if strategy == "skip":
        return series
    if strategy == "zero":
        return series.fillna(0)
    if strategy == "mean":
        fill_value = series.mean()
        if pd.isna(fill_value):
            fill_value = 0
        return series.fillna(fill_value)

    fill_value = series.median()
    if pd.isna(fill_value):
        fill_value = 0
    return series.fillna(fill_value)


def _fill_text_series(series: pd.Series, strategy: MissingTextStrategy) -> pd.Series:
    if strategy == "skip":
        return series
    if strategy == "unknown":
        return series.fillna("未知")
    if strategy == "empty":
        return series.fillna("")

    mode_series = series.mode(dropna=True)
    fill_value = mode_series.iloc[0] if not mode_series.empty else "未知"
    return series.fillna(fill_value)


def _get_datetime_strategy_text(strategy: MissingDatetimeStrategy) -> str:
    mapping = {
        "ffill_bfill": "前后相邻值补齐，补不齐再填 1970-01-01",
        "epoch": "直接填 1970-01-01",
        "skip": "不处理",
    }
    return mapping[strategy]


def _get_numeric_strategy_text(strategy: MissingNumericStrategy) -> str:
    mapping = {
        "median": "用中位数填充",
        "mean": "用平均数填充",
        "zero": "直接填 0",
        "skip": "不处理",
    }
    return mapping[strategy]


def _get_text_strategy_text(strategy: MissingTextStrategy) -> str:
    mapping = {
        "mode": "用最常见的值填充",
        "unknown": "直接填“未知”",
        "empty": "直接填空字符串",
        "skip": "不处理",
    }
    return mapping[strategy]


def _mark_outliers(df: pd.DataFrame) -> tuple[dict[str, int], int, list[int], list[str]]:
    """Flags outliers using the IQR rule and appends marker columns."""

    numeric_columns = df.select_dtypes(include=["number"]).columns.tolist()
    outlier_columns: list[pd.Series] = []
    outlier_counts: dict[str, int] = {}
    skipped_columns: list[str] = []

    for column in numeric_columns:
        series = df[column]
        if _should_skip_outlier_detection(column, series):
            skipped_columns.append(column)
            outlier_counts[column] = 0
            continue

        if series.nunique(dropna=True) < 4:
            outlier_mask = pd.Series(False, index=df.index)
        else:
            q1 = series.quantile(0.25)
            q3 = series.quantile(0.75)
            iqr = q3 - q1

            if iqr == 0 or pd.isna(iqr):
                outlier_mask = pd.Series(False, index=df.index)
            else:
                lower_bound = q1 - 1.5 * iqr
                upper_bound = q3 + 1.5 * iqr
                outlier_mask = (series < lower_bound) | (series > upper_bound)

        outlier_mask.name = column
        outlier_columns.append(outlier_mask)
        outlier_counts[column] = int(outlier_mask.sum())

    if outlier_columns:
        outlier_matrix = pd.concat(outlier_columns, axis=1)
        df[OUTLIER_FLAG_COLUMN] = outlier_matrix.any(axis=1)
        df[OUTLIER_FIELDS_COLUMN] = outlier_matrix.apply(
            lambda row: ", ".join(row.index[row].tolist()) if row.any() else "",
            axis=1,
        )
    else:
        df[OUTLIER_FLAG_COLUMN] = False
        df[OUTLIER_FIELDS_COLUMN] = ""

    outlier_row_indices = df.index[df[OUTLIER_FLAG_COLUMN]].tolist()
    total_outlier_rows = int(df[OUTLIER_FLAG_COLUMN].sum())
    return outlier_counts, total_outlier_rows, outlier_row_indices, skipped_columns


def _should_skip_outlier_detection(column: str, series: pd.Series) -> bool:
    """Skips identifier-like numeric fields from anomaly detection."""

    if is_identifier_column(column):
        return True

    non_null_series = series.dropna()
    if non_null_series.empty:
        return False

    unique_ratio = float(non_null_series.nunique()) / float(non_null_series.shape[0])
    looks_like_integer_codes = pd.api.types.is_integer_dtype(series) or (
        (non_null_series % 1 == 0).all()
    )

    if looks_like_integer_codes and unique_ratio >= 0.95:
        return True

    return False
