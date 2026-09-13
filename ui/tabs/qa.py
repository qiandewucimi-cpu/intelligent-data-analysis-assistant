"""QA tab: natural-language question -> sandboxed pandas -> result + explanation."""

from __future__ import annotations

import streamlit as st

from analyzer.agent import PandasQueryAgent, QueryExecutionResult
from analyzer.columns import drop_helper_columns
from analyzer.llm import LLMConfig
from analyzer.profile import build_dataframe_profile
from ui.display import prepare_dataframe_for_display
from ui.exports import render_dataframe_export
from ui.llm_runtime import build_runtime_llm_service


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
                with st.spinner("正在生成 pandas 代码并在沙箱中执行..."):
                    llm_service = build_runtime_llm_service(llm_config)
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

    render_query_result(query_result)


def render_query_result(query_result: QueryExecutionResult) -> None:
    """Displays query code, result table, and repair details."""

    result_metrics = st.columns(3)
    result_metrics[0].metric("执行轮次", query_result.attempts)
    result_metrics[1].metric("结果行数", query_result.result_frame.shape[0])
    result_metrics[2].metric("结果列数", query_result.result_frame.shape[1])

    st.markdown("**查询结果**")
    st.dataframe(prepare_dataframe_for_display(query_result.result_frame), width="stretch")

    st.markdown("**AI 结果解读**")
    st.markdown(query_result.explanation)

    st.markdown("**导出查询结果**")
    render_dataframe_export(query_result.result_frame, base_name="问答结果", key_prefix="dl_qa", sheet_name="问答结果")

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
