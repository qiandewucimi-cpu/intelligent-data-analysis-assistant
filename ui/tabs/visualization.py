"""Visualization tab: auto-recommended charts or fully manual chart building."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from analyzer.agent import QueryExecutionResult
from ui.charts import (
    AGG_LABELS,
    CHART_TYPE_LABELS,
    build_chart_bundle,
    build_custom_chart,
    list_chartable_columns,
    suggested_aggregation,
)
from ui.display import prepare_dataframe_for_display
from ui.exports import render_chart_download


def render_visualization_tab() -> None:
    """Renders automatically generated charts."""

    if st.session_state.cleaned_df is None:
        st.info("📂 还没有数据。请先到「数据上传」上传文件（清洗可选），就能用这个功能。")
        return

    st.subheader("智能图表")
    has_query_result = isinstance(st.session_state.query_result, QueryExecutionResult)

    source_option = st.radio(
        "选择图表数据源",
        options=["清洗后数据", "问答结果"] if has_query_result else ["清洗后数据"],
        horizontal=True,
    )

    if source_option == "问答结果" and has_query_result:
        chart_source = st.session_state.query_result.result_frame
    else:
        chart_source = st.session_state.cleaned_df

    if chart_source.empty:
        st.warning("当前数据源为空，无法生成图表。")
        return

    mode = st.radio(
        "出图方式",
        options=["自动推荐", "我自己选"],
        horizontal=True,
        help="“自动推荐”帮你挑列并出三张图；“我自己选”由你决定画哪列、怎么统计。",
    )

    if mode == "我自己选":
        _render_custom_chart(chart_source)
        return

    try:
        chart_bundle = build_chart_bundle(chart_source)
        st.session_state.chart_bundle = chart_bundle
    except Exception as exc:
        st.error(f"自动生成图表失败：{exc}")
        return

    chart_columns = st.columns(3)
    for container, key, title in zip(chart_columns, ["bar", "line", "pie"], ["柱状图", "折线图", "饼图"]):
        payload = chart_bundle[key]
        with container:
            st.markdown(f"**{title}**")
            if payload.get("available"):
                st.plotly_chart(payload["fig"], width="stretch")
                st.caption(payload["context"])
                render_chart_download(payload["fig"], f"自动{title}", key=f"dl_auto_{key}")
            else:
                st.warning(payload.get("reason", "当前无法生成该图表。"))


_COUNT_OPTION = "（不选数值，按每类的行数计数）"


def _render_custom_chart(chart_source: pd.DataFrame) -> None:
    """Lets the user pick exactly what to visualize."""

    columns = list_chartable_columns(chart_source)
    dimension_options = columns["category"] + columns["datetime"]
    measure_options = columns["numeric"]

    if not dimension_options:
        st.warning("当前数据里没有可用作“分类/时间”的列（横轴），无法自定义出图。可以先在“数据清洗”里识别日期列，或换个数据源。")
        return

    control_columns = st.columns(4)
    chart_type = control_columns[0].selectbox(
        "图表类型",
        options=["bar", "line", "pie"],
        format_func=lambda value: CHART_TYPE_LABELS[value],
        key="custom_chart_type",
    )
    dimension = control_columns[1].selectbox(
        "分类 / 时间（横轴）",
        options=dimension_options,
        key="custom_chart_dimension",
    )
    measure_pick = control_columns[2].selectbox(
        "要统计的数值（纵轴）",
        options=[_COUNT_OPTION] + measure_options,
        key="custom_chart_measure",
    )
    measure = None if measure_pick == _COUNT_OPTION else measure_pick

    if measure is None:
        aggregation = "count"
        control_columns[3].caption("统计方式：按所选分类数每一类有多少行。")
    else:
        agg_keys = ["sum", "mean", "median", "max", "min"]
        default_agg = suggested_aggregation(measure)
        default_index = agg_keys.index(default_agg) if default_agg in agg_keys else 0
        aggregation = control_columns[3].selectbox(
            "统计方式",
            options=agg_keys,
            index=default_index,
            format_func=lambda value: AGG_LABELS[value],
            key="custom_chart_agg",
        )

    is_time_dimension = pd.api.types.is_datetime64_any_dtype(chart_source[dimension])
    top_n = 15
    if not is_time_dimension:
        top_n = st.slider("最多显示多少项（按数值从高到低取）", min_value=5, max_value=50, value=15, key="custom_chart_topn")

    result = build_custom_chart(
        chart_source,
        chart_type=chart_type,
        dimension=dimension,
        measure=measure,
        aggregation=aggregation,
        top_n=top_n,
    )

    if not result.get("available"):
        st.warning(result.get("reason", "无法生成该图表。"))
        return

    st.plotly_chart(result["fig"], width="stretch")
    st.caption(result["context"])
    render_chart_download(result["fig"], "自定义图表", key="dl_custom")
    with st.expander("查看这张图背后的数据"):
        st.dataframe(prepare_dataframe_for_display(result["data"]), width="stretch")
