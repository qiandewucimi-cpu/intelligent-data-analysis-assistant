from __future__ import annotations

import re
from typing import Any

import pandas as pd
import plotly.express as px

from utils.data_handler import drop_helper_columns, is_identifier_column


# Columns whose name implies a rate/average/unit-price — summing these is wrong,
# so we aggregate them with mean instead of sum.
_MEAN_KEYWORDS = (
    "率", "比例", "占比", "百分比", "rate", "ratio", "percent", "pct",
    "评分", "得分", "score", "均", "平均", "单价", "均价", "price", "avg", "mean",
    "利率", "汇率", "温度", "满意度", "正确率", "通过率", "转化",
)

# Columns whose name implies an additive measure — good for sum-based bars/pies.
_SUM_KEYWORDS = (
    "金额", "销售", "销量", "收入", "营收", "成交", "数量", "总数", "总额",
    "次数", "量", "额", "count", "amount", "total", "sum", "gmv", "pv", "uv",
    "曝光", "点击", "订单", "人数", "库存", "费用", "成本", "利润",
)


def build_chart_bundle(df: pd.DataFrame) -> dict[str, dict[str, Any]]:
    """Builds bar, line, and pie charts automatically when possible."""

    source_df = _prepare_dataframe(df)
    measures = _rank_measure_columns(source_df)
    categories = _rank_category_columns(source_df)
    datetimes = source_df.select_dtypes(include=["datetime", "datetimetz"]).columns.tolist()

    return {
        "bar": _build_bar_chart(source_df, measures, categories),
        "line": _build_line_chart(source_df, measures, categories, datetimes),
        "pie": _build_pie_chart(source_df, measures, categories),
    }


def build_chart_summary(chart_bundle: dict[str, dict[str, Any]]) -> str:
    """Converts chart metadata into prompt-friendly text."""

    segments: list[str] = []
    for chart_name, payload in chart_bundle.items():
        if not payload.get("available"):
            segments.append(f"{chart_name} 图：{payload.get('reason', '未生成')}")
            continue

        chart_data = _format_chart_preview(payload["data"].head(8))
        segments.append(
            f"{chart_name} 图：{payload['context']}\n数据预览：\n{chart_data}"
        )

    return "\n\n".join(segments)


def _prepare_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Ensures the chart source is compact, index-safe, and free of helper columns."""

    if df.empty:
        return df.copy()

    source_df = drop_helper_columns(df)
    if isinstance(source_df.index, pd.MultiIndex) or not isinstance(source_df.index, pd.RangeIndex):
        source_df = source_df.reset_index(drop=False)
    return source_df


def _aggregation_for(column: str) -> str:
    """Decides whether a measure should be summed or averaged based on its name."""

    name = re.sub(r"[^a-z0-9一-鿿]+", "", str(column).lower())
    if any(keyword in name for keyword in _MEAN_KEYWORDS):
        return "mean"
    return "sum"


def _aggregation_label(func: str) -> str:
    return "求平均" if func == "mean" else "求和"


def _rank_measure_columns(df: pd.DataFrame) -> list[str]:
    """Returns numeric measure columns ordered by how chartable they are.

    Identifier-like and constant columns are excluded; columns whose name reads
    like a real measure are preferred, then those with more spread.
    """

    candidates: list[str] = []
    for column in df.select_dtypes(include=["number"]).columns.tolist():
        if is_identifier_column(column):
            continue
        if df[column].nunique(dropna=True) <= 1:
            continue
        candidates.append(column)

    def score(column: str) -> tuple[int, float]:
        name = re.sub(r"[^a-z0-9一-鿿]+", "", str(column).lower())
        name_hit = 1 if any(keyword in name for keyword in _SUM_KEYWORDS + _MEAN_KEYWORDS) else 0
        series = df[column].dropna()
        mean = series.mean()
        spread = float(series.std() / abs(mean)) if mean not in (0, None) and pd.notna(mean) and mean != 0 else 0.0
        return (name_hit, spread)

    return sorted(candidates, key=score, reverse=True)


def _rank_category_columns(df: pd.DataFrame) -> list[str]:
    """Returns grouping columns ordered by suitability (moderate cardinality first)."""

    numeric_columns = set(df.select_dtypes(include=["number"]).columns.tolist())
    datetime_columns = set(df.select_dtypes(include=["datetime", "datetimetz"]).columns.tolist())
    row_count = max(int(df.shape[0]), 1)

    candidates: list[tuple[str, int, float]] = []
    for column in df.columns:
        if column in numeric_columns or column in datetime_columns:
            continue
        if is_identifier_column(column):
            continue
        unique = int(df[column].nunique(dropna=True))
        if unique < 2:
            continue
        # Drop near-unique text columns (names, free text) that can't form a chart.
        if unique > 50 and unique / row_count > 0.5:
            continue
        missing_ratio = float(df[column].isna().mean())
        candidates.append((column, unique, missing_ratio))

    # A mostly-empty column (e.g. an optional tag filled on a few rows) makes a poor
    # default dimension, so push sparse columns to the back; otherwise prefer 2..30
    # distinct values with lighter columns first.
    def score(item: tuple[str, int, float]) -> tuple[int, int, int]:
        _, unique, missing_ratio = item
        too_sparse = 1 if missing_ratio > 0.5 else 0
        in_sweet_spot = 0 if 2 <= unique <= 30 else 1
        return (too_sparse, in_sweet_spot, unique)

    return [column for column, _, _ in sorted(candidates, key=score)]


def _build_bar_chart(df: pd.DataFrame, measures: list[str], categories: list[str]) -> dict[str, Any]:
    if categories and measures:
        x_col = categories[0]
        y_col = measures[0]
        func = _aggregation_for(y_col)
        chart_df = (
            df[[x_col, y_col]]
            .dropna()
            .groupby(x_col, as_index=False)[y_col]
            .agg(func)
            .sort_values(y_col, ascending=False)
            .head(15)
        )
        context = f"柱状图：按「{x_col}」对「{y_col}」{_aggregation_label(func)}，取前 15 名。"
    elif measures:
        y_col = measures[0]
        chart_df = df[[y_col]].dropna().head(20).reset_index(names="样本序号")
        x_col = "样本序号"
        context = f"柱状图展示前 20 个样本的「{y_col}」数值分布。"
    elif categories:
        x_col = categories[0]
        chart_df = _build_frequency_frame(df, x_col).head(15)
        y_col = "频次"
        context = f"柱状图展示「{x_col}」的出现频次（行数）。"
    else:
        return {"available": False, "reason": "缺少可用于柱状图的字段（没有合适的分类或数值列）。"}

    figure = px.bar(
        chart_df,
        x=x_col,
        y=y_col,
        title="自动生成柱状图",
        template="plotly_white",
        text_auto=True,
    )
    figure.update_layout(xaxis_title=x_col, yaxis_title=y_col)
    return {"available": True, "fig": figure, "data": chart_df, "context": context}


def _build_line_chart(
    df: pd.DataFrame,
    measures: list[str],
    categories: list[str],
    datetimes: list[str],
) -> dict[str, Any]:
    if datetimes and measures:
        x_col = datetimes[0]
        y_col = measures[0]
        func = _aggregation_for(y_col)
        chart_df = (
            df[[x_col, y_col]]
            .dropna()
            .groupby(x_col, as_index=False)[y_col]
            .agg(func)
            .sort_values(x_col)
        )
        context = f"折线图：「{y_col}」随「{x_col}」的时间趋势（按时间{_aggregation_label(func)}）。"
    elif categories and measures:
        x_col = categories[0]
        y_col = measures[0]
        func = _aggregation_for(y_col)
        chart_df = (
            df[[x_col, y_col]]
            .dropna()
            .groupby(x_col, as_index=False)[y_col]
            .agg(func)
            .sort_values(y_col, ascending=False)
            .head(30)
        )
        context = f"折线图：按「{x_col}」对「{y_col}」{_aggregation_label(func)}。"
    elif measures:
        y_col = measures[0]
        chart_df = df[[y_col]].dropna().head(30).reset_index(names="样本序号")
        x_col = "样本序号"
        context = f"折线图展示前 30 个样本的「{y_col}」变化趋势。"
    elif categories:
        x_col = categories[0]
        chart_df = _build_frequency_frame(df, x_col).head(20)
        y_col = "频次"
        context = f"折线图展示「{x_col}」各类别的频次变化。"
    else:
        return {"available": False, "reason": "缺少可用于折线图的字段。"}

    figure = px.line(
        chart_df,
        x=x_col,
        y=y_col,
        title="自动生成折线图",
        template="plotly_white",
        markers=True,
    )
    figure.update_layout(xaxis_title=x_col, yaxis_title=y_col)
    return {"available": True, "fig": figure, "data": chart_df, "context": context}


def _build_pie_chart(df: pd.DataFrame, measures: list[str], categories: list[str]) -> dict[str, Any]:
    # A pie shows composition, so it only makes sense for additive (sum-able) measures.
    additive_measures = [column for column in measures if _aggregation_for(column) == "sum"]

    if categories and additive_measures:
        label_col = categories[0]
        value_col = additive_measures[0]
        grouped = (
            df[[label_col, value_col]]
            .dropna()
            .groupby(label_col, as_index=False)[value_col]
            .sum()
            .sort_values(value_col, ascending=False)
        )
        chart_df = _collapse_minor_categories(grouped, label_col, value_col)
        context = f"饼图：按「{label_col}」展示「{value_col}」的总量占比结构。"
    elif categories:
        # No additive measure (or only rates): fall back to record-count composition.
        label_col = categories[0]
        chart_df = _collapse_minor_categories(_build_frequency_frame(df, label_col), label_col, "频次")
        value_col = "频次"
        context = f"饼图：按「{label_col}」展示各类别的行数占比（无可加总指标，改用出现次数）。"
    elif len(additive_measures) == 1:
        value_col = additive_measures[0]
        binned = pd.cut(df[value_col], bins=5).astype(str).value_counts().sort_index()
        chart_df = pd.DataFrame({"区间": binned.index, "样本数": binned.values})
        label_col = "区间"
        value_col = "样本数"
        context = f"饼图展示「{additive_measures[0]}」的区间分布占比。"
    else:
        return {"available": False, "reason": "缺少可用于饼图的字段（需要一个分类列或一个可加总的数值列）。"}

    figure = px.pie(
        chart_df,
        names=label_col,
        values=value_col,
        title="自动生成饼图",
        template="plotly_white",
    )
    return {"available": True, "fig": figure, "data": chart_df, "context": context}


def _build_frequency_frame(df: pd.DataFrame, column: str) -> pd.DataFrame:
    """Builds a compact frequency table for text-like columns."""

    return (
        df[[column]]
        .dropna()
        .astype(str)
        .assign(**{column: lambda frame: frame[column].str.strip()})
        .query(f"`{column}` != ''")
        .groupby(column, as_index=False)
        .size()
        .rename(columns={"size": "频次"})
        .sort_values("频次", ascending=False)
    )


def _collapse_minor_categories(df: pd.DataFrame, label_col: str, value_col: str) -> pd.DataFrame:
    """Keeps the pie chart readable by merging small segments into '其他'."""

    top_df = df.head(8).copy()
    if df.shape[0] <= 8:
        return top_df

    remaining_value = df.iloc[8:][value_col].sum()
    extra_row = pd.DataFrame([{label_col: "其他", value_col: remaining_value}])
    return pd.concat([top_df, extra_row], ignore_index=True)


def _format_chart_preview(df: pd.DataFrame) -> str:
    """Formats compact chart data previews without optional markdown deps."""

    try:
        return df.to_markdown(index=False)
    except Exception:
        return df.to_string(index=False)


# ---- Manual chart building (user picks the columns and aggregation) ----

AGG_LABELS = {
    "sum": "求和",
    "mean": "求平均",
    "median": "中位数",
    "max": "最大值",
    "min": "最小值",
    "count": "计数（行数）",
}

CHART_TYPE_LABELS = {
    "bar": "柱状图",
    "line": "折线图",
    "pie": "饼图",
}


def list_chartable_columns(df: pd.DataFrame) -> dict[str, list[str]]:
    """Splits columns into the roles the manual chart picker exposes."""

    source = drop_helper_columns(df)
    numeric = [
        column
        for column in source.select_dtypes(include=["number"]).columns.tolist()
        if not is_identifier_column(column)
    ]
    datetimes = source.select_dtypes(include=["datetime", "datetimetz"]).columns.tolist()
    category = [
        column
        for column in source.columns
        if column not in set(numeric) | set(datetimes) and not is_identifier_column(column)
    ]
    return {"numeric": numeric, "datetime": datetimes, "category": category}


def suggested_aggregation(column: str | None) -> str:
    """Default aggregation for a chosen measure (mean for rates, else sum)."""

    if not column:
        return "count"
    return _aggregation_for(column)


def build_custom_chart(
    df: pd.DataFrame,
    chart_type: str,
    dimension: str,
    measure: str | None = None,
    aggregation: str = "sum",
    top_n: int = 15,
) -> dict[str, Any]:
    """Builds a single chart exactly as the user specified.

    dimension: the grouping column (category or datetime).
    measure: the numeric column to aggregate; ignored when aggregation == "count".
    """

    source = drop_helper_columns(df)
    if source.empty:
        return {"available": False, "reason": "当前数据源为空，无法生成图表。"}
    if dimension not in source.columns:
        return {"available": False, "reason": f"找不到列「{dimension}」。"}

    use_count = aggregation == "count" or not measure
    is_time = pd.api.types.is_datetime64_any_dtype(source[dimension])

    if use_count:
        frame = source[[dimension]].dropna()
        if not is_time:
            frame = frame.astype({dimension: str})
            frame[dimension] = frame[dimension].str.strip()
            frame = frame[frame[dimension] != ""]
        chart_df = (
            frame.groupby(dimension, as_index=False)
            .size()
            .rename(columns={"size": "行数"})
        )
        value_col = "行数"
        agg_label = "计数（行数）"
    else:
        if measure not in source.columns:
            return {"available": False, "reason": f"找不到数值列「{measure}」。"}
        frame = source[[dimension, measure]].dropna()
        if not is_time:
            frame[dimension] = frame[dimension].astype(str).str.strip()
            frame = frame[frame[dimension] != ""]
        if frame.empty:
            return {"available": False, "reason": "所选列在去掉空值后没有可用数据。"}
        chart_df = frame.groupby(dimension, as_index=False)[measure].agg(aggregation)
        value_col = measure
        agg_label = AGG_LABELS.get(aggregation, aggregation)

    if chart_df.empty:
        return {"available": False, "reason": "所选列没有可用于绘图的数据。"}

    # Time series stays in chronological order; everything else shows the biggest first.
    if is_time:
        chart_df = chart_df.sort_values(dimension)
    else:
        chart_df = chart_df.sort_values(value_col, ascending=False).head(top_n)

    title = f"{CHART_TYPE_LABELS.get(chart_type, chart_type)}：{dimension} × {value_col}（{agg_label}）"

    try:
        if chart_type == "line":
            figure = px.line(
                chart_df, x=dimension, y=value_col, title=title,
                template="plotly_white", markers=True,
            )
            figure.update_layout(xaxis_title=dimension, yaxis_title=value_col)
        elif chart_type == "pie":
            pie_df = chart_df.copy()
            negative_note = ""
            if (pie_df[value_col] < 0).any():
                pie_df = pie_df[pie_df[value_col] >= 0]
                negative_note = "（已忽略负值，饼图只展示非负部分）"
            if pie_df.empty:
                return {"available": False, "reason": "所选数值全为负数，无法画饼图。"}
            pie_df = _collapse_minor_categories(pie_df, dimension, value_col)
            figure = px.pie(pie_df, names=dimension, values=value_col, title=title, template="plotly_white")
            chart_df = pie_df
            title += negative_note
        else:  # bar (default)
            figure = px.bar(
                chart_df, x=dimension, y=value_col, title=title,
                template="plotly_white", text_auto=True,
            )
            figure.update_layout(xaxis_title=dimension, yaxis_title=value_col)
    except Exception as exc:  # defensive: surface a readable message instead of crashing the page
        return {"available": False, "reason": f"绘图失败：{exc}"}

    context = f"按「{dimension}」对「{value_col}」{agg_label}。"
    return {"available": True, "fig": figure, "data": chart_df, "context": context}
