from __future__ import annotations

import streamlit as st


def inject_custom_css() -> None:
    st.markdown(
        """
        <style>
        /* ---- 隐藏 Streamlit 默认装饰 ---- */
        div[data-testid="stToolbar"] { visibility: hidden; height: 0; position: fixed; }
        div[data-testid="stDecoration"] { visibility: hidden; height: 0; }
        div[data-testid="stStatusWidget"] { visibility: hidden; height: 0; }
        #MainMenu { visibility: hidden; }
        header[data-testid="stHeader"] { background: transparent; }
        button[kind="header"], [data-testid="stBaseButton-headerNoPadding"] { visibility: hidden; }
        .stAppDeployButton { visibility: hidden; height: 0; }
        footer { visibility: hidden; }

        /* ---- 全局字体（让中文更干净） ---- */
        html, body, [class*="css"] {
            font-family: "Source Sans Pro", "Microsoft YaHei", "PingFang SC", "Segoe UI", sans-serif;
        }

        /* ---- 主区域留白与宽度 ---- */
        [data-testid="stMainBlockContainer"], .block-container {
            padding-top: 2rem;
            padding-bottom: 3rem;
            max-width: 1280px;
        }

        /* ---- 顶部渐变标题横幅 ---- */
        .hero {
            background: linear-gradient(135deg, #2563EB 0%, #1E40AF 100%);
            padding: 22px 28px;
            border-radius: 16px;
            margin-bottom: 18px;
            box-shadow: 0 8px 24px rgba(37, 99, 235, 0.25);
        }
        .hero-title {
            color: #FFFFFF;
            font-size: 1.7rem;
            font-weight: 800;
            letter-spacing: -0.01em;
            margin: 0;
        }
        .hero-sub {
            color: #DCE6FF;
            font-size: 0.95rem;
            margin-top: 6px;
        }

        /* ---- 标签页：药丸式，选中蓝色高亮 ---- */
        .stTabs [data-baseweb="tab-list"] {
            gap: 6px;
            border-bottom: 1px solid #E6EBF3;
        }
        .stTabs [data-baseweb="tab"] {
            height: 46px;
            padding: 0 20px;
            border-radius: 10px 10px 0 0;
            font-weight: 600;
            color: #64748B;
        }
        .stTabs [aria-selected="true"] {
            color: #2563EB !important;
            background: #EEF3FE;
        }

        /* ---- 指标卡片化 ---- */
        [data-testid="stMetric"] {
            background: #FFFFFF;
            border: 1px solid #E6EBF3;
            border-radius: 14px;
            padding: 14px 18px;
            box-shadow: 0 1px 3px rgba(16, 24, 40, 0.06);
        }
        [data-testid="stMetricValue"] { color: #2563EB; font-weight: 700; }
        [data-testid="stMetricLabel"] { color: #64748B; font-weight: 600; }

        /* ---- 按钮：圆角 + 悬停微动效 ---- */
        .stButton > button, .stDownloadButton > button, .stFormSubmitButton > button {
            border-radius: 10px;
            font-weight: 600;
            transition: transform 0.12s ease, box-shadow 0.12s ease;
        }
        .stButton > button:hover, .stDownloadButton > button:hover, .stFormSubmitButton > button:hover {
            transform: translateY(-1px);
            box-shadow: 0 4px 12px rgba(37, 99, 235, 0.18);
        }

        /* ---- 输入框 / 下拉 / 表格 / 展开框：统一圆角与描边 ---- */
        .stTextInput input, .stNumberInput input { border-radius: 8px; }
        [data-testid="stDataFrame"] {
            border: 1px solid #E6EBF3;
            border-radius: 12px;
            overflow: hidden;
        }
        [data-testid="stExpander"] {
            border: 1px solid #E6EBF3;
            border-radius: 12px;
        }
        [data-testid="stAlert"] { border-radius: 10px; }

        /* ---- 侧边栏：白底 + 右侧分隔线 ---- */
        [data-testid="stSidebar"] {
            background: #FFFFFF;
            border-right: 1px solid #E6EBF3;
        }

        /* ---- 标题层级微调 ---- */
        h1, h2, h3 { letter-spacing: -0.01em; }
        h3 { color: #1E293B; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_hero() -> None:
    st.markdown(
        """
        <div class="hero">
            <p class="hero-title">📊 智能数据分析助手</p>
            <p class="hero-sub">上传数据 → 数据清洗 → 智能问答 → 智能图表 → AI 分析报告</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
