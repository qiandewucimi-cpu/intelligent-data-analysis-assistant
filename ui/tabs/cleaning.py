"""Cleaning tab: interactive rules, before/after comparison, change details."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from analyzer.columns import OUTLIER_FLAG_COLUMN, drop_helper_columns
from ui.cleaning_summary import (
    build_change_summary,
    build_cleaning_action_summary,
    build_cleaning_column_summary,
    build_duplicate_preview,
    get_cleaning_performance_mode,
)
from ui.display import prepare_dataframe_for_display
from ui.exports import render_cleaned_data_export
from ui.state import apply_cleaning, default_cleaning_options, reset_cleaning_to_raw_state


def render_cleaning_tab() -> None:
    """Renders interactive cleaning configuration and before/after comparison."""

    if st.session_state.raw_df is None:
        st.info("📂 还没有数据。请先到「数据上传」标签页上传文件，再回来这一步。")
        return

    st.subheader("自定义数据清洗")
    st.warning("默认不会自动修改你的数据。只有你勾选规则并点击“应用清洗规则”后，系统才会真正改动数据。")
    st.write("先选规则，再手动应用。你也可以随时恢复成原始数据。")

    _render_cleaning_controls()

    cleaned_df = st.session_state.cleaned_df
    cleaning_report = st.session_state.cleaning_report
    raw_df = st.session_state.raw_df

    metric_columns = st.columns(4)
    metric_columns[0].metric("删除重复行", cleaning_report["duplicate_rows_removed"])
    metric_columns[1].metric("填充缺失值", cleaning_report["total_missing_filled"])
    metric_columns[2].metric("异常值行数", cleaning_report["total_outlier_rows"])
    metric_columns[3].metric("清洗后行数", cleaning_report["cleaned_rows"])

    render_cleaned_data_export(cleaned_df)

    compare_limit = st.selectbox(
        "对比展示行数",
        options=[20, 50, 100, 200],
        index=1,
        key="cleaning_compare_limit",
    )
    _render_cleaning_comparison(raw_df, cleaned_df, cleaning_report, compare_limit)

    st.markdown("**具体改了哪里**")
    performance_mode = get_cleaning_performance_mode(raw_df)
    if performance_mode != "full":
        st.info("当前数据量较大，页面已切换为轻量模式，只展示重点变化，避免长时间无响应。")

    change_summary = build_change_summary(
        raw_df,
        cleaned_df,
        cleaning_report,
        limit=compare_limit,
        performance_mode=performance_mode,
    )
    summary_metrics = st.columns(3)
    summary_metrics[0].metric("被修改的单元格", len(change_summary["changed_cells"]))
    summary_metrics[1].metric("被删除的重复行", len(change_summary["removed_rows"]))
    summary_metrics[2].metric("新增的异常标记行", len(change_summary["flagged_rows"]))

    if change_summary["changed_cells"]:
        st.markdown("**字段修改明细（逐格列出改了什么）**")
        st.dataframe(
            prepare_dataframe_for_display(pd.DataFrame(change_summary["changed_cells"])),
            width="stretch",
        )
    else:
        st.info("这次没有发现单元格内容被改动。")

    if change_summary["removed_rows"]:
        with st.expander(f"被删除的重复行（{len(change_summary['removed_rows'])} 行）"):
            st.dataframe(
                prepare_dataframe_for_display(pd.DataFrame(change_summary["removed_rows"]).head(50)),
                width="stretch",
            )

    if change_summary["flagged_rows"]:
        with st.expander(f"被标记为异常的行（{len(change_summary['flagged_rows'])} 行）"):
            st.dataframe(
                prepare_dataframe_for_display(pd.DataFrame(change_summary["flagged_rows"]).head(50)),
                width="stretch",
            )

    st.markdown("**本次清洗做了什么**")
    for action_text in build_cleaning_action_summary(cleaning_report):
        st.write(f"- {action_text}")

    # Field-level detail and samples are useful but secondary — keep them tucked away
    # so the page is not a wall of tables on first glance.
    with st.expander("字段处理清单 / 重复行样例 / 异常值样例"):
        diff_columns = st.columns(2)
        with diff_columns[0]:
            st.markdown("**字段处理清单**")
            column_summary = build_cleaning_column_summary(cleaning_report)
            if not column_summary.empty:
                st.dataframe(prepare_dataframe_for_display(column_summary), width="stretch")
            else:
                st.info("当前没有字段级处理明细。")

        with diff_columns[1]:
            st.markdown("**重复行样例**")
            duplicate_preview = build_duplicate_preview(
                raw_df=raw_df,
                duplicate_row_indices=cleaning_report.get("duplicate_row_indices", []),
                limit=compare_limit,
            )
            if not duplicate_preview.empty:
                st.dataframe(prepare_dataframe_for_display(duplicate_preview), width="stretch")
            else:
                st.success("这次没有发现重复行。")

        flagged_rows = cleaned_df[cleaned_df[OUTLIER_FLAG_COLUMN]].head(compare_limit)
        st.markdown("**异常值样例**")
        if not flagged_rows.empty:
            st.caption("“异常值字段”这一列会告诉你，每一行是被哪些字段判定为异常。")
            st.dataframe(prepare_dataframe_for_display(flagged_rows), width="stretch")
        else:
            st.success("当前未检测到明显异常值。")

    with st.expander("查看完整清洗明细（原始 JSON）"):
        st.json(cleaning_report)


def _render_cleaning_comparison(
    raw_df: pd.DataFrame,
    cleaned_df: pd.DataFrame,
    cleaning_report: dict[str, Any],
    compare_limit: int,
) -> None:
    """Shows an aligned before/after view that highlights exactly which cells changed."""

    st.markdown("**清洗前后对比**")

    duplicate_row_indices = cleaning_report.get("duplicate_row_indices", [])
    comparable_raw = raw_df.drop(index=duplicate_row_indices, errors="ignore").reset_index(drop=True)
    comparable_cleaned = drop_helper_columns(cleaned_df).reset_index(drop=True)

    shared_columns = [column for column in comparable_raw.columns if column in comparable_cleaned.columns]
    row_count = min(len(comparable_raw), len(comparable_cleaned))
    if not shared_columns or row_count == 0:
        st.info("没有可对齐比较的列。")
        return

    raw_aligned = comparable_raw[shared_columns].iloc[:row_count].reset_index(drop=True)
    cleaned_aligned = comparable_cleaned[shared_columns].iloc[:row_count].reset_index(drop=True)

    # Compare what the user actually SEES (after display formatting), so e.g. a date
    # parsed from "2025-07-25" to a timestamp shown as "2025-07-25" is not flagged.
    raw_shown = prepare_dataframe_for_display(raw_aligned)
    cleaned_shown = prepare_dataframe_for_display(cleaned_aligned)
    differs = raw_shown.ne(cleaned_shown)
    both_missing = raw_shown.isna() & cleaned_shown.isna()
    change_mask = differs & ~both_missing

    changed_rows_total = int(change_mask.any(axis=1).sum())
    changed_cells_total = int(change_mask.to_numpy().sum())
    removed_duplicates = int(cleaning_report.get("duplicate_rows_removed", 0))

    show_only_changed = st.checkbox(
        "只看发生变化的行（黄色格子 = 被改过的内容）",
        value=True,
        key="cleaning_only_changed",
        help="关掉它可以查看全部行，包括没有变化的行。",
    )

    if changed_cells_total == 0:
        if removed_duplicates > 0:
            st.success(f"单元格内容没有被改动；但删除了 {removed_duplicates} 行重复行（见下方“被删除的行”）。")
        else:
            st.success("清洗前后没有任何单元格变化——可能你还没点“应用清洗规则”，或所选规则没命中数据。")
        if show_only_changed:
            return

    if show_only_changed:
        row_positions = change_mask.index[change_mask.any(axis=1)].tolist()[:compare_limit]
    else:
        row_positions = list(range(min(row_count, compare_limit)))

    if not row_positions:
        return

    changed_columns = [str(column) for column in change_mask.columns if bool(change_mask[column].any())]
    st.caption(
        f"共 {changed_rows_total} 行、{changed_cells_total} 个单元格发生变化，下面显示其中 {len(row_positions)} 行。"
    )
    if changed_columns:
        st.caption(f"📍 发生变化的列：{'、'.join(changed_columns)}（这些列里被改的格子是黄色，往右拉可以看到）")

    sub_mask = change_mask.loc[row_positions].reset_index(drop=True)
    row_labels = [str(position) for position in row_positions]

    compare_columns = st.columns(2)
    with compare_columns[0]:
        st.markdown("清洗前")
        st.dataframe(_style_changed_cells(raw_aligned.loc[row_positions], sub_mask, row_labels), width="stretch")
    with compare_columns[1]:
        st.markdown("清洗后")
        st.dataframe(_style_changed_cells(cleaned_aligned.loc[row_positions], sub_mask, row_labels), width="stretch")


def _style_changed_cells(view: pd.DataFrame, change_mask: pd.DataFrame, row_labels: list[str]) -> Any:
    """Returns a Styler that paints changed cells yellow on an Arrow-safe frame."""

    display_df = prepare_dataframe_for_display(view).reset_index(drop=True)
    display_df.insert(0, "行号", row_labels)
    mask = change_mask.reset_index(drop=True)

    def _paint(data: pd.DataFrame) -> pd.DataFrame:
        css = pd.DataFrame("", index=data.index, columns=data.columns)
        for column in data.columns:
            if column in mask.columns:
                css.loc[mask[column].to_numpy(), column] = "background-color: #ffe08a; color: #000000"
        return css

    styler = display_df.style.apply(_paint, axis=None)
    try:
        styler = styler.hide(axis="index")
    except Exception:
        pass
    return styler


def _render_cleaning_controls() -> None:
    """Renders configurable cleaning options and applies them on demand."""

    stored_options = st.session_state.cleaning_options or default_cleaning_options()

    def _stored(key: str, default: Any = False) -> Any:
        return stored_options.get(key, default)

    with st.form("cleaning_options_form", clear_on_submit=False):
        st.markdown("**第一步 · 基础整理**（建议保持勾选，基本不会动坏数据）")
        base_columns = st.columns(3)
        strip_text = base_columns[0].checkbox(
            "去除文本首尾空格",
            value=_stored("strip_text", True),
            help="把“ 携程 ”这种两端多余空格去掉，避免同一类被算成两类。",
        )
        convert_datetime = base_columns[1].checkbox(
            "识别日期",
            value=_stored("convert_datetime", True),
            help="把“2025-07-25”这类文本认成日期，方便按时间分析（只显示到年月日）。",
        )
        convert_numeric_text = base_columns[2].checkbox(
            "识别数字",
            value=_stored("convert_numeric_text", True),
            help="把“￥2,850”“23%”认成能计算的数字。",
        )

        st.markdown("**第二步 · 按需处理**（会真正改动或标注数据，按需勾选）")
        action_toggle_columns = st.columns(3)
        remove_duplicates = action_toggle_columns[0].checkbox(
            "删除完全重复的行",
            value=_stored("remove_duplicates", False),
        )
        fill_missing = action_toggle_columns[1].checkbox(
            "填充缺失值",
            value=_stored("fill_missing", False),
            help="空得太多的列（超过 60%）会自动跳过，避免整列被编造。",
        )
        mark_outliers = action_toggle_columns[2].checkbox(
            "标记异常值（只加标签，不改原值）",
            value=_stored("mark_outliers", False),
        )

        st.markdown("**填充缺失值时怎么补**（只有勾了“填充缺失值”才生效）")
        strategy_columns = st.columns(3)
        missing_numeric_strategy = strategy_columns[0].selectbox(
            "数值列",
            options=["median", "mean", "zero", "skip"],
            index=["median", "mean", "zero", "skip"].index(_stored("missing_numeric_strategy", "median")),
            format_func=lambda value: {
                "median": "用中位数",
                "mean": "用平均数",
                "zero": "直接填 0",
                "skip": "不处理",
            }[value],
        )
        missing_text_strategy = strategy_columns[1].selectbox(
            "文本列",
            options=["mode", "unknown", "empty", "skip"],
            index=["mode", "unknown", "empty", "skip"].index(_stored("missing_text_strategy", "mode")),
            format_func=lambda value: {
                "mode": "用最常见的值",
                "unknown": "填“未知”",
                "empty": "填空字符串",
                "skip": "不处理",
            }[value],
        )
        missing_datetime_strategy = strategy_columns[2].selectbox(
            "日期列",
            options=["ffill_bfill", "epoch", "skip"],
            index=["ffill_bfill", "epoch", "skip"].index(_stored("missing_datetime_strategy", "ffill_bfill")),
            format_func=lambda value: {
                "ffill_bfill": "用前后相邻值补",
                "epoch": "填 1970-01-01",
                "skip": "不处理",
            }[value],
        )

        apply_clicked = st.form_submit_button("应用清洗规则", type="primary")

    if apply_clicked:
        st.session_state.cleaning_options = {
            "strip_text": strip_text,
            "convert_datetime": convert_datetime,
            "convert_numeric_text": convert_numeric_text,
            "remove_duplicates": remove_duplicates,
            "fill_missing": fill_missing,
            "mark_outliers": mark_outliers,
            "missing_numeric_strategy": missing_numeric_strategy,
            "missing_text_strategy": missing_text_strategy,
            "missing_datetime_strategy": missing_datetime_strategy,
        }
        st.session_state.cleaning_applied = True
        apply_cleaning()
        st.success("新的清洗规则已应用。")

    action_columns = st.columns(2)
    with action_columns[0]:
        if st.button("恢复原始数据", width="stretch"):
            st.session_state.cleaning_options = default_cleaning_options()
            st.session_state.cleaning_applied = False
            reset_cleaning_to_raw_state()
            st.success("已经恢复为原始数据，当前没有做任何清洗。")
    with action_columns[1]:
        if st.button("按当前规则重新清洗", width="stretch"):
            apply_cleaning()
            st.success("已按当前规则重新清洗。")
