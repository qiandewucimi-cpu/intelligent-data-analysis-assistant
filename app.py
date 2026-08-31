from __future__ import annotations

import hashlib
import io
import os
from typing import Any

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from utils.charting import (
    AGG_LABELS,
    CHART_TYPE_LABELS,
    build_chart_bundle,
    build_chart_summary,
    build_custom_chart,
    list_chartable_columns,
    suggested_aggregation,
)
from utils.data_handler import (
    OUTLIER_FIELDS_COLUMN,
    OUTLIER_FLAG_COLUMN,
    CleaningOptions,
    build_analysis_statistics,
    build_dataframe_profile,
    clean_dataframe,
    drop_helper_columns,
    list_excel_sheets,
    load_dataframe,
    looks_like_messy_header,
)
from utils.export_security import escape_spreadsheet_formulas
from utils.llm_service import LLMConfig, LLMService, ProviderType
from utils.pandas_agent import PandasQueryAgent, QueryExecutionResult
from utils.report_export import markdown_to_docx_bytes


load_dotenv()


def _get_config_value(key: str, default: str = "") -> str:
    """Reads Streamlit secrets when available, otherwise falls back to env vars."""

    try:
        value = st.secrets.get(key)
    except Exception:
        value = ""

    if value in (None, ""):
        return os.getenv(key, default)
    return str(value)


st.set_page_config(page_title="智能数据分析助手", layout="wide")

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


def main() -> None:
    """Renders the Streamlit application."""

    _init_session_state()
    st.markdown(
        """
        <div class="hero">
            <p class="hero-title">📊 智能数据分析助手</p>
            <p class="hero-sub">上传数据 → 数据清洗 → 智能问答 → 智能图表 → AI 分析报告</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

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


def _provider_env_keys(provider: str) -> tuple:
    return {
        "zhipu": ("ZHIPU_API_KEY", "ZHIPU_MODEL", "ZHIPU_BASE_URL"),
        "deepseek": ("DEEPSEEK_API_KEY", "DEEPSEEK_MODEL", "DEEPSEEK_BASE_URL"),
        "dashscope": ("DASHSCOPE_API_KEY", "QWEN_MODEL", "DASHSCOPE_BASE_URL"),
        "openai_compatible": ("OPENAI_API_KEY", "OPENAI_MODEL", "OPENAI_BASE_URL"),
    }.get(provider, ("OPENAI_API_KEY", "OPENAI_MODEL", "OPENAI_BASE_URL"))


def _env_file_path() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")


def _update_env(updates: dict, remove_keys=()) -> None:
    """Upserts/removes keys in the local .env, preserving other lines."""
    path = _env_file_path()
    lines = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    remove = set(remove_keys)
    done = set()
    out = []
    for ln in lines:
        stripped = ln.lstrip()
        name = None
        if "=" in stripped and not stripped.startswith("#"):
            cand = stripped.split("=", 1)[0].strip()
            if cand and (cand[0].isalpha() or cand[0] == "_") and all(c.isalnum() or c == "_" for c in cand):
                name = cand
        if name and name in remove:
            continue
        if name and name in updates:
            out.append(name + "=" + str(updates[name]))
            done.add(name)
        else:
            out.append(ln)
    for k, v in updates.items():
        if k not in done:
            out.append(k + "=" + str(v))
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out).strip("\n") + "\n")

    # 同步内存中的环境变量，避免改了 .env 文件但进程里仍是旧值，
    # 导致刷新后被删的密钥/勾选状态又被读回来。
    for k, v in updates.items():
        os.environ[k] = str(v)
    for k in remove:
        os.environ.pop(k, None)


def _save_credentials(provider: str, api_key: str, model_name: str, base_url: str) -> None:
    k_api, k_model, k_url = _provider_env_keys(provider)
    updates = {"LLM_PROVIDER": provider, "LLM_REMEMBER": "1", k_api: api_key}
    if model_name:
        updates[k_model] = model_name
    if base_url:
        updates[k_url] = base_url
    _update_env(updates)


def _forget_credentials(provider: str) -> None:
    k_api, _, _ = _provider_env_keys(provider)
    _update_env({}, remove_keys=(k_api, "LLM_REMEMBER"))


def render_sidebar() -> LLMConfig:
    """Renders model and connection settings."""

    st.sidebar.header("模型配置")
    st.sidebar.caption("👉 只想上传数据、做清洗和图表？不用填密钥，直接到右边「数据上传」开始；只有用 AI 问答 / AI 报告才需要填密钥。")

    provider_options = ["zhipu", "deepseek", "dashscope", "openai_compatible"]
    provider_labels = {
        "zhipu": "智谱 GLM（推荐，已预设地址）",
        "deepseek": "DeepSeek（已预设地址，推荐）",
        "dashscope": "通义千问 / DashScope",
        "openai_compatible": "OpenAI 兼容接口",
    }
    default_provider_value = _get_config_value("LLM_PROVIDER", "zhipu").strip().lower()
    default_provider = default_provider_value if default_provider_value in provider_options else "zhipu"

    provider: ProviderType = st.sidebar.selectbox(
        "模型服务",
        options=provider_options,
        index=provider_options.index(default_provider),
        format_func=lambda value: provider_labels[value],
        help="只有智谱 key 就选「智谱 GLM」，地址已自动填好，贴上 key、选个模型即可。",
    )

    if provider == "zhipu":
        default_api_key = _get_config_value("ZHIPU_API_KEY", "")
    elif provider == "deepseek":
        default_api_key = _get_config_value("DEEPSEEK_API_KEY", "")
    elif provider == "dashscope":
        default_api_key = _get_config_value("DASHSCOPE_API_KEY", "")
    else:
        default_api_key = _get_config_value("OPENAI_API_KEY", "")

    api_key = st.sidebar.text_input(
        "接口密钥",
        value=default_api_key,
        type="password",
        help="未填写时仍可使用上传、清洗和图表能力，问答和 AI 报告不可用。",
    )
    remember_key = st.sidebar.checkbox(
        "记住密钥（保存到本机，下次自动填）",
        value=bool(_get_config_value("LLM_REMEMBER", "").strip()),
        help="勾选后密钥保存在本机 .env 文件，下次打开自动填好；取消勾选会删除已保存的密钥。公用电脑请勿勾选。",
    )

    st.sidebar.checkbox(
        "🔒 脱敏模式：不外发原始明细（推荐开启）",
        value=True,
        key="desensitize",
        help=(
            "开启后，使用「AI 问答」「AI 报告」时只把列名、数据类型和汇总数字发给大模型，"
            "不发送原始数据行和真实取值（如姓名、客户名、地区名等敏感身份信息）。"
            "处理客户机密 / 个人信息时务必保持开启；若是公开练习数据，可关闭以获得更精准的解读。"
        ),
    )

    use_responses_api = False

    if provider == "zhipu":
        zhipu_models = ["glm-4-flash", "glm-4-flashx", "glm-4-air", "glm-4-airx", "glm-4-plus", "glm-4-long"]
        zhipu_labels = {
            "glm-4-flash": "glm-4-flash（免费，速度快，够日常用）",
            "glm-4-flashx": "glm-4-flashx（便宜，比 flash 强）",
            "glm-4-air": "glm-4-air（性价比）",
            "glm-4-airx": "glm-4-airx（更快的 air）",
            "glm-4-plus": "glm-4-plus（效果最好，按量收费）",
            "glm-4-long": "glm-4-long（超长文本）",
        }
        default_model = _get_config_value("ZHIPU_MODEL", "glm-4-flash")
        model_name = st.sidebar.selectbox(
            "模型名称",
            options=zhipu_models,
            index=zhipu_models.index(default_model) if default_model in zhipu_models else 0,
            format_func=lambda value: zhipu_labels.get(value, value),
            help="预算紧就用 glm-4-flash（免费）；想要更好的分析效果用 glm-4-plus。",
        )
        base_url = st.sidebar.text_input(
            "接口地址",
            value=_get_config_value("ZHIPU_BASE_URL", "https://open.bigmodel.cn/api/paas/v4"),
            help="智谱开放平台的官方地址，一般不用改。",
        )
    elif provider == "deepseek":
        deepseek_models = ["deepseek-chat", "deepseek-reasoner"]
        deepseek_labels = {
            "deepseek-chat": "deepseek-chat（V3，日常推荐，快又便宜）",
            "deepseek-reasoner": "deepseek-reasoner（R1，深度推理，更强但慢）",
        }
        default_model = _get_config_value("DEEPSEEK_MODEL", "deepseek-chat")
        model_name = st.sidebar.selectbox(
            "模型名称",
            options=deepseek_models,
            index=deepseek_models.index(default_model) if default_model in deepseek_models else 0,
            format_func=lambda value: deepseek_labels.get(value, value),
            help="日常用 deepseek-chat；要更强的推理分析用 deepseek-reasoner。",
        )
        base_url = st.sidebar.text_input(
            "接口地址",
            value=_get_config_value("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            help="DeepSeek 官方地址，一般不用改。",
        )
    elif provider == "dashscope":
        default_model = _get_config_value("QWEN_MODEL", "qwen-plus")
        model_name = st.sidebar.selectbox(
            "模型名称",
            options=["qwen-plus", "qwen-turbo", "qwen-max"],
            index=["qwen-plus", "qwen-turbo", "qwen-max"].index(default_model)
            if default_model in {"qwen-plus", "qwen-turbo", "qwen-max"}
            else 0,
        )
        base_url = st.sidebar.text_input(
            "接口地址",
            value=_get_config_value(
                "DASHSCOPE_BASE_URL",
                "https://dashscope.aliyuncs.com/compatible-mode/v1",
            ),
            help="默认使用 DashScope 的兼容接口地址。",
        )
    else:
        default_use_responses_api = _get_config_value("OPENAI_USE_RESPONSES_API", "false").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        model_name = st.sidebar.text_input(
            "模型名称",
            value=_get_config_value("OPENAI_MODEL", "gpt-4o-mini"),
            help="填写你的 OpenAI 兼容网关实际支持的模型名。",
        )
        base_url = st.sidebar.text_input(
            "接口地址",
            value=_get_config_value("OPENAI_BASE_URL", ""),
            help="例如 `https://ccg-in.nowcoder.com`。",
        )
        use_responses_api = st.sidebar.checkbox(
            "使用 Responses 接口",
            value=default_use_responses_api,
            help="如果你的网关配置写了 `wire_api = responses`，就勾选它。",
        )

    # 防污染：密钥内容若等于接口地址，说明是异常数据（曾出现过把地址误存成密钥的情况），
    # 不写盘，避免坏数据被反复回写形成"删不掉"的死循环。
    key_is_valid = bool(api_key.strip()) and api_key.strip() != base_url.strip()
    if remember_key and key_is_valid:
        try:
            _save_credentials(provider, api_key.strip(), model_name.strip(), base_url.strip())
            st.sidebar.caption("已保存到本机，下次自动填。")
        except Exception as exc:
            st.sidebar.caption("密钥保存失败：" + str(exc))
    elif not remember_key and _get_config_value("LLM_REMEMBER", "").strip():
        try:
            _forget_credentials(provider)
        except Exception:
            pass

    return LLMConfig(
        provider=provider,
        api_key=api_key,
        model_name=model_name,
        base_url=base_url,
        use_responses_api=use_responses_api,
    )


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

    signature = _build_file_signature(uploaded_file.name, file_bytes, sheet_name) + f":h{header_row}"
    if st.session_state.file_signature != signature:
        try:
            raw_df = load_dataframe(file_bytes, uploaded_file.name, sheet_name=sheet_name, header_row=header_row)
            st.session_state.file_signature = signature
            st.session_state.file_name = uploaded_file.name
            st.session_state.raw_df = raw_df
            st.session_state.cleaning_options = _default_cleaning_options()
            _reset_cleaning_to_raw_state()
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
    st.dataframe(_prepare_dataframe_for_display(raw_df.head(preview_limit)), width="stretch")


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

    _render_cleaned_data_export(cleaned_df)

    compare_limit = st.selectbox(
        "对比展示行数",
        options=[20, 50, 100, 200],
        index=1,
        key="cleaning_compare_limit",
    )
    _render_cleaning_comparison(raw_df, cleaned_df, cleaning_report, compare_limit)

    st.markdown("**具体改了哪里**")
    performance_mode = _get_cleaning_performance_mode(raw_df)
    if performance_mode != "full":
        st.info("当前数据量较大，页面已切换为轻量模式，只展示重点变化，避免长时间无响应。")

    change_summary = _build_change_summary(
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
            _prepare_dataframe_for_display(pd.DataFrame(change_summary["changed_cells"])),
            width="stretch",
        )
    else:
        st.info("这次没有发现单元格内容被改动。")

    if change_summary["removed_rows"]:
        with st.expander(f"被删除的重复行（{len(change_summary['removed_rows'])} 行）"):
            st.dataframe(
                _prepare_dataframe_for_display(pd.DataFrame(change_summary["removed_rows"]).head(50)),
                width="stretch",
            )

    if change_summary["flagged_rows"]:
        with st.expander(f"被标记为异常的行（{len(change_summary['flagged_rows'])} 行）"):
            st.dataframe(
                _prepare_dataframe_for_display(pd.DataFrame(change_summary["flagged_rows"]).head(50)),
                width="stretch",
            )

    st.markdown("**本次清洗做了什么**")
    for action_text in _build_cleaning_action_summary(cleaning_report):
        st.write(f"- {action_text}")

    # Field-level detail and samples are useful but secondary — keep them tucked away
    # so the page is not a wall of tables on first glance.
    with st.expander("字段处理清单 / 重复行样例 / 异常值样例"):
        diff_columns = st.columns(2)
        with diff_columns[0]:
            st.markdown("**字段处理清单**")
            column_summary = _build_cleaning_column_summary(cleaning_report)
            if not column_summary.empty:
                st.dataframe(_prepare_dataframe_for_display(column_summary), width="stretch")
            else:
                st.info("当前没有字段级处理明细。")

        with diff_columns[1]:
            st.markdown("**重复行样例**")
            duplicate_preview = _build_duplicate_preview(
                raw_df=raw_df,
                duplicate_row_indices=cleaning_report.get("duplicate_row_indices", []),
                limit=compare_limit,
            )
            if not duplicate_preview.empty:
                st.dataframe(_prepare_dataframe_for_display(duplicate_preview), width="stretch")
            else:
                st.success("这次没有发现重复行。")

        flagged_rows = cleaned_df[cleaned_df[OUTLIER_FLAG_COLUMN]].head(compare_limit)
        st.markdown("**异常值样例**")
        if not flagged_rows.empty:
            st.caption("“异常值字段”这一列会告诉你，每一行是被哪些字段判定为异常。")
            st.dataframe(_prepare_dataframe_for_display(flagged_rows), width="stretch")
        else:
            st.success("当前未检测到明显异常值。")

    with st.expander("查看完整清洗明细（原始 JSON）"):
        st.json(cleaning_report)


def render_qa_tab(llm_config: LLMConfig) -> None:
    """Renders natural language query execution."""

    if st.session_state.cleaned_df is None:
        st.info("📂 还没有数据。请先到「数据上传」上传文件（清洗可选），就能用这个功能。")
        return

    st.subheader("智能问答")
    st.write("示例：`按地区统计销售额总和，并按从高到低排序`")

    with st.form("qa_form", clear_on_submit=False):
        question = st.text_area(
            "请输入分析问题",
            placeholder="例如：筛选 2025 年订单，并按产品分组统计销售额、利润，按销售额降序排列。",
            height=120,
        )
        submitted = st.form_submit_button("生成并执行 pandas 代码")

    if submitted:
        if not question.strip():
            st.warning("请输入分析问题。")
        elif not llm_config.api_key.strip():
            st.warning("请先在左侧填写可用的接口密钥。")
        elif llm_config.provider == "openai_compatible" and not llm_config.base_url.strip():
            st.warning("OpenAI 兼容接口模式下请先填写接口地址。")
        else:
            try:
                with st.spinner("正在生成 pandas 代码并自动执行..."):
                    llm_service = _build_runtime_llm_service(llm_config)
                    agent = PandasQueryAgent(llm_service=llm_service, max_retries=2)
                    analysis_df = drop_helper_columns(st.session_state.cleaned_df)
                    desensitize = bool(st.session_state.get("desensitize", True))
                    profile = build_dataframe_profile(analysis_df, desensitize=desensitize)
                    result = agent.ask(
                        question=question.strip(),
                        df=analysis_df,
                        dataframe_profile=profile,
                        desensitize=desensitize,
                    )
                    st.session_state.query_result = result
            except Exception as exc:
                st.error(str(exc))

    query_result = st.session_state.query_result
    if query_result is None:
        st.info("执行完成后，这里会展示生成代码、结果表和 AI 解读。")
        return

    _render_query_result(query_result)


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
                _render_chart_download(payload["fig"], f"自动{title}", key=f"dl_auto_{key}")
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
    _render_chart_download(result["fig"], "自定义图表", key="dl_custom")
    with st.expander("查看这张图背后的数据"):
        st.dataframe(_prepare_dataframe_for_display(result["data"]), width="stretch")


def _render_chart_download(fig: Any, base_name: str, key: str) -> None:
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


def render_report_tab(llm_config: LLMConfig) -> None:
    """Renders the AI business analysis report."""

    if st.session_state.cleaned_df is None:
        st.info("📂 还没有数据。请先到「数据上传」上传文件（清洗可选），就能用这个功能。")
        return

    st.subheader("AI 分析报告")
    st.write("结合清洗结果、统计问答结果和图表摘要，输出业务分析、风险提示和优化建议。")

    if st.button("生成 AI 分析报告", type="primary"):
        if not llm_config.api_key.strip():
            st.warning("请先在左侧填写可用的接口密钥。")
        elif llm_config.provider == "openai_compatible" and not llm_config.base_url.strip():
            st.warning("OpenAI 兼容接口模式下请先填写接口地址。")
        else:
            try:
                with st.spinner("正在生成分析报告..."):
                    llm_service = _build_runtime_llm_service(llm_config)
                    analysis_df = drop_helper_columns(st.session_state.cleaned_df)
                    desensitize = bool(st.session_state.get("desensitize", True))
                    data_profile = build_dataframe_profile(analysis_df, desensitize=desensitize)
                    statistics = build_analysis_statistics(analysis_df, desensitize=desensitize)
                    question = (
                        st.session_state.query_result.question
                        if isinstance(st.session_state.query_result, QueryExecutionResult)
                        else ""
                    )
                    result_summary = _build_result_summary(st.session_state.query_result)
                    if not st.session_state.chart_bundle:
                        st.session_state.chart_bundle = build_chart_bundle(st.session_state.cleaned_df)
                    chart_summary = build_chart_summary(st.session_state.chart_bundle or {})

                    report = llm_service.generate_business_report(
                        data_profile=data_profile,
                        cleaning_report=st.session_state.cleaning_report,
                        question=question,
                        result_summary=result_summary,
                        chart_summary=chart_summary,
                        statistics=statistics,
                    )
                    st.session_state.analysis_report = report
            except Exception as exc:
                st.error(f"生成报告失败：{exc}")

    if st.session_state.analysis_report:
        st.markdown(st.session_state.analysis_report)
        _render_report_export(st.session_state.analysis_report)
    else:
        st.info("点击上方按钮后，这里会展示自动生成的 AI 分析报告。")


def _render_report_export(report_text: str) -> None:
    """Offers Word/Markdown download buttons for the generated AI report."""

    if not report_text or not report_text.strip():
        return

    base_name = "AI分析报告"
    file_label = st.session_state.get("file_name", "")
    if file_label:
        base_name = f"AI分析报告_{os.path.splitext(file_label)[0]}"

    st.markdown("**导出分析报告**")
    download_columns = st.columns(2)

    try:
        docx_bytes = markdown_to_docx_bytes(report_text, title="AI 分析报告")
        download_columns[0].download_button(
            "下载 Word（.docx）",
            data=docx_bytes,
            file_name=f"{base_name}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            width="stretch",
            key="dl_report_docx",
        )
    except Exception as exc:
        download_columns[0].warning(f"Word 导出失败：{exc}")

    download_columns[1].download_button(
        "下载 Markdown（.md）",
        data=report_text.encode("utf-8"),
        file_name=f"{base_name}.md",
        mime="text/markdown",
        width="stretch",
        key="dl_report_md",
    )


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
    raw_shown = _prepare_dataframe_for_display(raw_aligned)
    cleaned_shown = _prepare_dataframe_for_display(cleaned_aligned)
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

    display_df = _prepare_dataframe_for_display(view).reset_index(drop=True)
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


def _render_dataframe_export(df: pd.DataFrame, base_name: str, key_prefix: str, sheet_name: str = "数据") -> None:
    """Generic Excel/CSV download buttons for any dataframe (formatted like the screen view)."""

    if df is None or df.empty:
        st.info("当前没有可导出的数据。")
        return

    export_df = escape_spreadsheet_formulas(_prepare_dataframe_for_display(df))
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


def _render_cleaned_data_export(cleaned_df: pd.DataFrame) -> None:
    """Offers Excel/CSV download buttons for the cleaned data."""

    # Keep the outlier marker columns only when there are actual outliers; otherwise drop the noise.
    export_source = cleaned_df
    if OUTLIER_FLAG_COLUMN in cleaned_df.columns and not bool(cleaned_df[OUTLIER_FLAG_COLUMN].any()):
        export_source = drop_helper_columns(cleaned_df)

    base_name = "清洗后数据"
    file_label = st.session_state.get("file_name", "")
    if file_label:
        base_name = f"清洗后_{os.path.splitext(file_label)[0]}"

    st.markdown("**导出清洗后的数据**")
    _render_dataframe_export(export_source, base_name=base_name, key_prefix="dl_cleaned", sheet_name="清洗后数据")


def _render_cleaning_controls() -> None:
    """Renders configurable cleaning options and applies them on demand."""

    stored_options = st.session_state.cleaning_options or _default_cleaning_options()

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
        _apply_cleaning()
        st.success("新的清洗规则已应用。")

    action_columns = st.columns(2)
    with action_columns[0]:
        if st.button("恢复原始数据", width="stretch"):
            st.session_state.cleaning_options = _default_cleaning_options()
            st.session_state.cleaning_applied = False
            _reset_cleaning_to_raw_state()
            st.success("已经恢复为原始数据，当前没有做任何清洗。")
    with action_columns[1]:
        if st.button("按当前规则重新清洗", width="stretch"):
            _apply_cleaning()
            st.success("已按当前规则重新清洗。")


def _apply_cleaning() -> None:
    """Applies the currently selected cleaning options to the raw dataframe."""

    if st.session_state.raw_df is None:
        return

    option_payload = {
        key: value
        for key, value in (st.session_state.cleaning_options or _default_cleaning_options()).items()
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


def _reset_cleaning_to_raw_state() -> None:
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
        "option_summary": {**_default_cleaning_options()},
        "total_missing_filled": 0,
    }
    st.session_state.query_result = None
    st.session_state.analysis_report = ""
    st.session_state.chart_bundle = {}


def _default_cleaning_options() -> dict[str, Any]:
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


def _build_runtime_llm_service(llm_config: LLMConfig) -> LLMService:
    """Normalizes trimmed runtime values before building the model client."""

    return LLMService(
        LLMConfig(
            provider=llm_config.provider,
            api_key=llm_config.api_key.strip(),
            model_name=llm_config.model_name.strip(),
            base_url=llm_config.base_url.strip(),
            use_responses_api=llm_config.use_responses_api,
        )
    )


def _render_query_result(query_result: QueryExecutionResult) -> None:
    """Displays query code, result table, and repair details."""

    result_metrics = st.columns(3)
    result_metrics[0].metric("执行轮次", query_result.attempts)
    result_metrics[1].metric("结果行数", query_result.result_frame.shape[0])
    result_metrics[2].metric("结果列数", query_result.result_frame.shape[1])

    st.markdown("**查询结果**")
    st.dataframe(_prepare_dataframe_for_display(query_result.result_frame), width="stretch")

    st.markdown("**AI 结果解读**")
    st.markdown(query_result.explanation)

    st.markdown("**导出查询结果**")
    _render_dataframe_export(query_result.result_frame, base_name="问答结果", key_prefix="dl_qa", sheet_name="问答结果")

    # The generated code is kept available for the curious, but folded away so the
    # result and its plain-language reading come first.
    with st.expander("查看本次执行的 pandas 代码"):
        st.code(query_result.code, language="python")

    if query_result.errors:
        with st.expander("查看自动纠错日志"):
            for index, error_text in enumerate(query_result.errors, start=1):
                st.write(f"{index}. {error_text}")
            st.markdown("**历史代码尝试**")
            for index, code_text in enumerate(query_result.attempted_codes, start=1):
                st.code(f"# 第 {index} 次尝试\n{code_text}", language="python")


def _build_result_summary(query_result: QueryExecutionResult | None) -> str:
    """Builds a compact summary string for the AI report prompt."""

    if not isinstance(query_result, QueryExecutionResult):
        return "暂无自然语言问答结果。"

    preview = _format_dataframe_preview(query_result.result_frame.head(10))
    return (
        f"用户问题：{query_result.question}\n"
        f"执行轮次：{query_result.attempts}\n"
        f"结果预览：\n{preview}\n\n"
        f"AI 解读：\n{query_result.explanation}"
    )


def _build_cleaning_action_summary(cleaning_report: dict[str, Any]) -> list[str]:
    """Builds human-readable cleaning steps for non-technical users."""

    actions: list[str] = []
    option_summary = cleaning_report.get("option_summary", {})

    if not st.session_state.get("cleaning_applied", False):
        return ["当前还是原始数据，系统还没有对你的数据做任何清洗。"]

    if option_summary:
        enabled_actions = []
        if option_summary.get("strip_text"):
            enabled_actions.append("去除文本首尾空格")
        if option_summary.get("convert_datetime"):
            enabled_actions.append("识别日期")
        if option_summary.get("convert_numeric_text"):
            enabled_actions.append("识别数字文本")
        if option_summary.get("remove_duplicates"):
            enabled_actions.append("删除重复行")
        if option_summary.get("fill_missing"):
            enabled_actions.append("填充缺失值")
        if option_summary.get("mark_outliers"):
            enabled_actions.append("标记异常值")
        actions.append(f"这次启用了这些清洗动作：{'、'.join(enabled_actions) if enabled_actions else '未启用任何动作'}。")

    duplicate_count = int(cleaning_report.get("duplicate_rows_removed", 0))
    actions.append(f"删除重复行：{duplicate_count} 行。")

    datetime_columns = cleaning_report.get("converted_datetime_columns", [])
    if datetime_columns:
        actions.append(f"识别成日期的字段：{', '.join(datetime_columns)}。")

    numeric_columns = cleaning_report.get("converted_numeric_columns", [])
    if numeric_columns:
        actions.append(f"识别成数值的字段：{', '.join(numeric_columns)}。")

    total_missing_filled = int(cleaning_report.get("total_missing_filled", 0))
    actions.append(f"填充缺失值：{total_missing_filled} 个。")

    total_outlier_rows = int(cleaning_report.get("total_outlier_rows", 0))
    if option_summary.get("mark_outliers", True):
        actions.append(f"标记异常值：{total_outlier_rows} 行。")

    skipped_outlier_columns = cleaning_report.get("skipped_outlier_columns", [])
    if skipped_outlier_columns:
        actions.append(f"这些更像编号的字段没有参与异常值判断：{', '.join(skipped_outlier_columns)}。")

    return actions


def _build_cleaning_column_summary(cleaning_report: dict[str, Any]) -> pd.DataFrame:
    """Builds a field-level summary of what the cleaning step changed."""

    missing_values_filled = cleaning_report.get("missing_values_filled", {})
    missing_fill_strategies = cleaning_report.get("missing_fill_strategies", {})
    outlier_counts = cleaning_report.get("outlier_counts", {})
    datetime_columns = set(cleaning_report.get("converted_datetime_columns", []))
    numeric_columns = set(cleaning_report.get("converted_numeric_columns", []))

    all_columns = sorted(
        set(missing_values_filled)
        | set(missing_fill_strategies)
        | set(outlier_counts)
        | datetime_columns
        | numeric_columns
    )

    rows: list[dict[str, Any]] = []
    for column in all_columns:
        converted_labels: list[str] = []
        if column in datetime_columns:
            converted_labels.append("转成日期")
        if column in numeric_columns:
            converted_labels.append("转成数值")

        rows.append(
            {
                "字段": column,
                "字段转换": "、".join(converted_labels) if converted_labels else "未转换",
                "填充缺失值数量": int(missing_values_filled.get(column, 0)),
                "缺失值处理方式": missing_fill_strategies.get(column, "未处理"),
                "异常值命中数量": int(outlier_counts.get(column, 0)),
            }
        )

    return pd.DataFrame(rows)


def _build_duplicate_preview(raw_df: pd.DataFrame | None, duplicate_row_indices: list[int], limit: int = 20) -> pd.DataFrame:
    """Shows a small preview of rows removed as duplicates."""

    if raw_df is None or not duplicate_row_indices:
        return pd.DataFrame()

    preview = raw_df.iloc[duplicate_row_indices].copy().head(limit)
    preview.insert(0, "原始行号", duplicate_row_indices[: len(preview)])
    return preview


def _build_change_summary(
    raw_df: pd.DataFrame,
    cleaned_df: pd.DataFrame,
    cleaning_report: dict[str, Any],
    limit: int = 100,
    performance_mode: str = "full",
) -> dict[str, list[dict[str, Any]]]:
    """Builds a compact list of visible changes instead of showing two full tables only."""

    changed_cells: list[dict[str, Any]] = []
    removed_rows: list[dict[str, Any]] = []
    flagged_rows: list[dict[str, Any]] = []

    duplicate_row_indices = cleaning_report.get("duplicate_row_indices", [])
    if duplicate_row_indices:
        removed_preview = raw_df.iloc[duplicate_row_indices].copy()
        removed_preview.insert(0, "原始行号", duplicate_row_indices[: len(removed_preview)])
        removed_rows = removed_preview.head(limit).to_dict(orient="records")

    comparable_raw = raw_df.drop(index=duplicate_row_indices, errors="ignore").reset_index(drop=True)
    comparable_cleaned = cleaned_df.drop(columns=[OUTLIER_FLAG_COLUMN, OUTLIER_FIELDS_COLUMN], errors="ignore").reset_index(drop=True)

    shared_columns = [column for column in comparable_raw.columns if column in comparable_cleaned.columns]
    shared_row_count = min(len(comparable_raw), len(comparable_cleaned))
    if performance_mode == "light":
        shared_row_count = min(shared_row_count, 200)
    elif performance_mode == "medium":
        shared_row_count = min(shared_row_count, 1000)

    candidate_columns = _pick_change_candidate_columns(cleaning_report, shared_columns)

    for row_index in range(shared_row_count):
        for column in candidate_columns:
            before_value = comparable_raw.iloc[row_index][column]
            after_value = comparable_cleaned.iloc[row_index][column]
            if _values_equal(before_value, after_value):
                continue

            changed_cells.append(
                {
                    "行号": row_index,
                    "字段": column,
                    "清洗前": _display_value(before_value),
                    "清洗后": _display_value(after_value),
                }
            )

    if OUTLIER_FLAG_COLUMN in cleaned_df.columns:
        flagged_preview = cleaned_df[cleaned_df[OUTLIER_FLAG_COLUMN]].copy().head(limit)
        if not flagged_preview.empty:
            flagged_preview.insert(0, "清洗后行号", flagged_preview.index.tolist())
            flagged_rows = flagged_preview.to_dict(orient="records")

    return {
        "changed_cells": changed_cells[: max(limit * 20, 200)],
        "removed_rows": removed_rows,
        "flagged_rows": flagged_rows,
    }


def _build_changed_row_preview(
    raw_df: pd.DataFrame,
    cleaned_df: pd.DataFrame,
    cleaning_report: dict[str, Any],
    limit: int,
    performance_mode: str = "full",
) -> pd.DataFrame:
    """Builds a row-level preview focused only on rows that changed."""

    duplicate_row_indices = set(cleaning_report.get("duplicate_row_indices", []))
    comparable_raw = raw_df.drop(index=list(duplicate_row_indices), errors="ignore").reset_index(drop=True)
    comparable_cleaned = cleaned_df.drop(columns=[OUTLIER_FLAG_COLUMN, OUTLIER_FIELDS_COLUMN], errors="ignore").reset_index(drop=True)

    shared_columns = [column for column in comparable_raw.columns if column in comparable_cleaned.columns]
    candidate_columns = _pick_change_candidate_columns(cleaning_report, shared_columns)
    changed_rows: list[dict[str, Any]] = []

    row_count = min(len(comparable_raw), len(comparable_cleaned))
    if performance_mode == "light":
        row_count = min(row_count, 200)
    elif performance_mode == "medium":
        row_count = min(row_count, 1000)

    for row_index in range(row_count):
        row_changes: dict[str, Any] = {"行号": row_index}
        has_change = False
        for column in candidate_columns:
            before_value = comparable_raw.iloc[row_index][column]
            after_value = comparable_cleaned.iloc[row_index][column]
            if _values_equal(before_value, after_value):
                continue
            row_changes[f"{column}（前）"] = _display_value(before_value)
            row_changes[f"{column}（后）"] = _display_value(after_value)
            has_change = True

        if has_change:
            changed_rows.append(row_changes)

    return pd.DataFrame(changed_rows[:limit])


def _pick_change_candidate_columns(cleaning_report: dict[str, Any], shared_columns: list[str]) -> list[str]:
    """Limits expensive comparisons to columns that are likely to have changed."""

    preferred_columns = (
        list(cleaning_report.get("converted_datetime_columns", []))
        + list(cleaning_report.get("converted_numeric_columns", []))
        + [
            column
            for column, count in cleaning_report.get("missing_values_filled", {}).items()
            if int(count) > 0
        ]
    )
    filtered = [column for column in dict.fromkeys(preferred_columns) if column in shared_columns]
    return filtered or shared_columns[: min(10, len(shared_columns))]


def _get_cleaning_performance_mode(raw_df: pd.DataFrame) -> str:
    """Chooses a lighter comparison mode for large datasets."""

    cell_count = int(raw_df.shape[0] * raw_df.shape[1])
    if cell_count >= 200000:
        return "light"
    if cell_count >= 50000:
        return "medium"
    return "full"


def _values_equal(before_value: Any, after_value: Any) -> bool:
    """Compares values safely across strings, numbers, datetimes, and missing values."""

    if pd.isna(before_value) and pd.isna(after_value):
        return True
    return before_value == after_value


def _display_value(value: Any) -> Any:
    """Formats values for the visible change list."""

    if pd.isna(value):
        return "空值"
    return str(value)


def _build_file_signature(file_name: str, file_bytes: bytes, sheet_name: str | None) -> str:
    """Creates a stable signature so Streamlit only reloads changed files."""

    digest = hashlib.md5(file_bytes).hexdigest()
    return f"{file_name}:{sheet_name or ''}:{digest}"


def _format_dataframe_preview(df: pd.DataFrame) -> str:
    """Formats small result previews without requiring optional markdown deps."""

    try:
        return df.to_markdown(index=False)
    except Exception:
        return df.to_string(index=False)


def _prepare_dataframe_for_display(df: pd.DataFrame) -> pd.DataFrame:
    """Converts mixed object columns into Arrow-safe strings for Streamlit."""

    display_df = df.copy()
    display_df.columns = [str(column) for column in display_df.columns]

    for column in display_df.columns:
        series = display_df[column]

        # Dates without a real time-of-day shouldn't show a noisy "00:00:00".
        if pd.api.types.is_datetime64_any_dtype(series):
            non_null = series.dropna()
            if not non_null.empty and bool((non_null.dt.normalize() == non_null).all()):
                display_df[column] = series.dt.strftime("%Y-%m-%d")
            else:
                display_df[column] = series.dt.strftime("%Y-%m-%d %H:%M:%S")
            continue

        if not (pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series)):
            continue

        sample_types = {type(value) for value in series.dropna().head(50)}
        has_mixed_types = len(sample_types) > 1
        has_bytes = any(value_type in {bytes, bytearray} for value_type in sample_types)

        if has_mixed_types or has_bytes:
            display_df[column] = series.map(_stringify_display_value)

    return display_df


def _stringify_display_value(value: Any) -> Any:
    """Formats non-null values as strings so Streamlit can render them reliably."""

    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    if isinstance(value, (bytes, bytearray)):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return value.hex()
    return str(value)


def _init_session_state() -> None:
    """Initializes Streamlit session keys once."""

    defaults: dict[str, Any] = {
        "file_signature": "",
        "file_name": "",
        "raw_df": None,
        "cleaned_df": None,
        "cleaning_report": {},
        "cleaning_options": _default_cleaning_options(),
        "cleaning_applied": False,
        "query_result": None,
        "chart_bundle": {},
        "analysis_report": "",
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


if __name__ == "__main__":
    main()
