"""智能数据分析助手 — Streamlit 演示壳入口。

真正的引擎在 ``analyzer/``（沙箱执行、Agent 循环、LLM 客户端、prompt
数据概况）；本文件与 ``ui/`` 只负责交互。也可以完全跳过界面：

    python -m analyzer sales.csv -q "各地区销售额Top5"     # CLI 无界面入口
"""

from __future__ import annotations

import streamlit as st
from dotenv import load_dotenv

from ui.credentials import get_config_value  # noqa: F401 - re-exported for tab modules
from ui.sidebar import render_sidebar
from ui.state import init_session_state
from ui.styles import inject_custom_css, render_hero
from ui.tabs.cleaning import render_cleaning_tab
from ui.tabs.qa import render_qa_tab
from ui.tabs.report import render_report_tab
from ui.tabs.upload import render_upload_tab
from ui.tabs.visualization import render_visualization_tab


load_dotenv()

st.set_page_config(page_title="智能数据分析助手", layout="wide")


def main() -> None:
    """Renders the Streamlit application."""

    init_session_state()
    render_hero()

    llm_config = render_sidebar()

    tabs = st.tabs(["数据上传", "数据清洗", "智能问答", "智能图表", "AI 分析报告"])

    with tabs[0]:
        render_upload_tab()

    with tabs[1]:
        render_cleaning_tab()

    with tabs[2]:
        render_qa_tab(llm_config=llm_config)

    with tabs[3]:
        render_visualization_tab()

    with tabs[4]:
        render_report_tab(llm_config=llm_config)


inject_custom_css()

if __name__ == "__main__":
    main()
