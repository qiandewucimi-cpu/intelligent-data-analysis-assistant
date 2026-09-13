"""Report tab: grounded AI business report with Word/Markdown export."""

from __future__ import annotations

import os

import streamlit as st

from analyzer.agent import QueryExecutionResult
from analyzer.columns import drop_helper_columns
from analyzer.llm import LLMConfig
from analyzer.profile import build_analysis_statistics, build_dataframe_profile
from ui.charts import build_chart_bundle, build_chart_summary
from ui.display import format_dataframe_preview
from ui.llm_runtime import build_runtime_llm_service
from ui.report_export import markdown_to_docx_bytes


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
                    llm_service = build_runtime_llm_service(llm_config)
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


def _build_result_summary(query_result: QueryExecutionResult | None) -> str:
    """Builds a compact summary string for the AI report prompt."""

    if not isinstance(query_result, QueryExecutionResult):
        return "暂无自然语言问答结果。"

    preview = format_dataframe_preview(query_result.result_frame.head(10))
    return (
        f"用户问题：{query_result.question}\n"
        f"执行轮次：{query_result.attempts}\n"
        f"结果预览：\n{preview}\n\n"
        f"AI 解读：\n{query_result.explanation}"
    )


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
