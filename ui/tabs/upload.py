"""Upload tab: file picker, header detection, raw preview."""

from __future__ import annotations

import streamlit as st

from ui.data_handler import list_excel_sheets, load_dataframe, looks_like_messy_header
from ui.display import build_file_signature, prepare_dataframe_for_display
from ui.state import default_cleaning_options, reset_cleaning_to_raw_state


def render_upload_tab() -> None:
    """Renders file upload and raw data preview."""

    st.subheader("上传 Excel / CSV 文件")
    uploaded_file = st.file_uploader(
        "选择一个数据文件",
        type=["csv", "xlsx", "xls"],
        help="上传后会先展示原始数据，你再决定怎么清洗。",
    )

    if not uploaded_file:
        st.info("📂 还没有数据。点上方「选择一个数据文件」上传 Excel 或 CSV 就能开始。")
        return

    file_bytes = uploaded_file.getvalue()
    sheet_name = None

    if uploaded_file.name.lower().endswith((".xlsx", ".xls")):
        try:
            sheet_names = list_excel_sheets(file_bytes)
            sheet_name = st.selectbox("选择工作表", options=sheet_names, index=0)
        except Exception as exc:
            st.error(f"读取工作表失败：{exc}")
            st.caption("建议：确认是正常的 Excel 文件；若文件加密或损坏，用 Excel 打开后另存一份再上传。")
            return

    if "header_line_value" not in st.session_state:
        st.session_state["header_line_value"] = 1
    if st.button("🔍 自动找表头（列名出现 Unnamed 时点我）"):
        best_row, best_score = 0, -1.0
        for _cand in range(0, 8):
            try:
                _probe = load_dataframe(file_bytes, uploaded_file.name, sheet_name=sheet_name, header_row=_cand)
            except Exception:
                continue
            _cols = [str(c) for c in _probe.columns]
            _named = sum(1 for c in _cols if c and not c.startswith("Unnamed") and not c.strip().isdigit())
            _sc = _named - 0.1 * len(_cols)
            if _sc > best_score:
                best_score, best_row = _sc, _cand
        st.session_state["header_line_value"] = best_row + 1
        st.rerun()
    header_line = st.number_input(
        "表头在第几行（列名所在的那一行，从 1 开始数）",
        min_value=1,
        max_value=50,
        step=1,
        key="header_line_value",
        help="不确定就点上面的『自动找表头』。像 Excel 透视表那样上面有标题行/空行时，把它改成真正列名所在的行号；列名出现 Unnamed 多半就是这里设小了。",
    )
    header_row = int(header_line) - 1

    signature = build_file_signature(uploaded_file.name, file_bytes, sheet_name) + f":h{header_row}"
    if st.session_state.file_signature != signature:
        try:
            raw_df = load_dataframe(file_bytes, uploaded_file.name, sheet_name=sheet_name, header_row=header_row)
            st.session_state.file_signature = signature
            st.session_state.file_name = uploaded_file.name
            st.session_state.raw_df = raw_df
            st.session_state.cleaning_options = default_cleaning_options()
            reset_cleaning_to_raw_state()
        except Exception as exc:
            st.error(f"文件解析失败：{exc}")
            st.caption("建议：换成 .xlsx 或 .csv 再试；若 CSV 打开是乱码，用 Excel『另存为 CSV UTF-8』后再上传。")
            return

    if looks_like_messy_header(st.session_state.raw_df):
        st.warning("检测到很多列名是 Unnamed（没读到真正的列名）。点上面的「🔍 自动找表头」让系统帮你找，或手动把「表头在第几行」往后调（比如 2、3），直到列名正常。")

    raw_df = st.session_state.raw_df
    st.success(f"已加载文件：{st.session_state.file_name}")

    metric_columns = st.columns(3)
    metric_columns[0].metric("原始行数", raw_df.shape[0])
    metric_columns[1].metric("原始列数", raw_df.shape[1])
    metric_columns[2].metric("缺失值总数", int(raw_df.isna().sum().sum()))

    preview_limit = st.selectbox(
        "原始数据预览行数",
        options=[20, 50, 100, 200],
        index=1,
        key="upload_preview_limit",
    )
    st.markdown("**原始数据预览**")
    st.dataframe(prepare_dataframe_for_display(raw_df.head(preview_limit)), width="stretch")
