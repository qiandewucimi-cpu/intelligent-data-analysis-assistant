"""Pure DataFrame column semantics shared by the engine and the UI shell."""

from __future__ import annotations

import re

import pandas as pd


OUTLIER_FLAG_COLUMN = "是否异常值"
OUTLIER_FIELDS_COLUMN = "异常值字段"
HELPER_COLUMNS = (OUTLIER_FLAG_COLUMN, OUTLIER_FIELDS_COLUMN)

IDENTIFIER_KEYWORDS = (
    "id",
    "jobid",
    "userid",
    "candidateid",
    "resumeid",
    "postid",
    "reqid",
    "uuid",
    "guid",
    "编号",
    "编码",
    "序号",
    "卡号",
    "账号",
    "账户",
    "订单号",
    "流水号",
    "工号",
    "学号",
    "身份证",
    "手机号",
    "手机",
    "电话",
    "phone",
    "mobile",
    "tel",
    "zip",
    "邮编",
    "邮政编码",
)


def is_identifier_column(column: str) -> bool:
    """Returns True when a column name looks like an identifier rather than a measure.

    Identifier-like columns (ids, phone numbers, postal codes) must never be
    converted to numbers, charted as values, or treated as anomalies.
    """

    normalized_name = re.sub(r"[^a-z0-9一-鿿]+", "", str(column).lower())
    if not normalized_name:
        return False
    return any(keyword in normalized_name for keyword in IDENTIFIER_KEYWORDS)


def drop_helper_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Returns a view without the cleaning helper columns used only for display."""

    return df.drop(columns=[column for column in HELPER_COLUMNS if column in df.columns])
