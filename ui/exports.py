from __future__ import annotations

import io
import os
from typing import Any

import pandas as pd
import streamlit as st

from ui.display import prepare_dataframe_for_display
from ui.export_security import escape_spreadsheet_formulas, prepare_cleaned_export_dataframe


def render_dataframe_export(df: pd.DataFrame, base_name: str, key_prefix: str, sheet_name: str = "数据") -> None:
    """Generic Excel/CSV download buttons for any dataframe (formatted like the screen view)."""

    if df is None or df.empty:
        st.info("当前没有可导出的数据。")
        return

    export_df = escape_spreadsheet_formulas(prepare_dataframe_for_display(df))
    download_columns = st.columns(2)

    excel_buffer = io.BytesIO()
    try:
        with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
            export_df.to_excel(writer, index=False, sheet_name=sheet_name[:31])
        download_columns[0].download_button(
            "下载 Excel（.xlsx）",
            data=excel_buffer.getvalue(),
            file_name=f"{base_name}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width="stretch",
            key=f"{key_prefix}_xlsx",
        )
    except Exception as exc:
        download_columns[0].warning(f"Excel 导出失败：{exc}")

    csv_bytes = export_df.to_csv(index=False).encode("utf-8-sig")
    download_columns[1].download_button(
        "下载 CSV（.csv，Excel 可直接打开）",
        data=csv_bytes,
        file_name=f"{base_name}.csv",
        mime="text/csv",
        width="stretch",
        key=f"{key_prefix}_csv",
    )


def render_cleaned_data_export(cleaned_df: pd.DataFrame) -> None:
    """Offers Excel/CSV download buttons for the cleaned data."""

    export_source = prepare_cleaned_export_dataframe(cleaned_df)

    base_name = "清洗后数据"
    file_label = st.session_state.get("file_name", "")
    if file_label:
        base_name = f"清洗后_{os.path.splitext(file_label)[0]}"

    st.markdown("**导出清洗后的数据**")
    render_dataframe_export(export_source, base_name=base_name, key_prefix="dl_cleaned", sheet_name="清洗后数据")


def render_chart_download(fig: Any, base_name: str, key: str) -> None:
    """Adds a download button for a chart (PNG first, HTML as a no-dependency fallback)."""

    try:
        png_bytes = fig.to_image(format="png", width=1100, height=650, scale=2)
        st.download_button(
            "下载图片（PNG）",
            data=png_bytes,
            file_name=f"{base_name}.png",
            mime="image/png",
            key=key,
        )
        return
    except Exception:
        pass

    try:
        html = fig.to_html(include_plotlyjs="cdn")
        st.download_button(
            "下载图片（网页版，可在浏览器打开后另存）",
            data=html.encode("utf-8"),
            file_name=f"{base_name}.html",
            mime="text/html",
            key=key,
        )
    except Exception:
        st.caption("如需保存：把鼠标移到图右上角，点相机图标即可下载 PNG。")
