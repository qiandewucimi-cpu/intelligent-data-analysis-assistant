"""Model/provider selection sidebar; returns the runtime LLMConfig."""

from __future__ import annotations

import streamlit as st

from analyzer.llm import LLMConfig, ProviderType
from ui.credentials import (
    forget_credentials,
    get_config_value,
    save_credentials,
)


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
    default_provider_value = get_config_value("LLM_PROVIDER", "zhipu").strip().lower()
    default_provider = default_provider_value if default_provider_value in provider_options else "zhipu"

    provider: ProviderType = st.sidebar.selectbox(
        "模型服务",
        options=provider_options,
        index=provider_options.index(default_provider),
        format_func=lambda value: provider_labels[value],
        help="只有智谱 key 就选「智谱 GLM」，地址已自动填好，贴上 key、选个模型即可。",
    )

    if provider == "zhipu":
        default_api_key = get_config_value("ZHIPU_API_KEY", "")
    elif provider == "deepseek":
        default_api_key = get_config_value("DEEPSEEK_API_KEY", "")
    elif provider == "dashscope":
        default_api_key = get_config_value("DASHSCOPE_API_KEY", "")
    else:
        default_api_key = get_config_value("OPENAI_API_KEY", "")

    api_key = st.sidebar.text_input(
        "接口密钥",
        value=default_api_key,
        type="password",
        help="未填写时仍可使用上传、清洗和图表能力，问答和 AI 报告不可用。",
    )
    remember_key = st.sidebar.checkbox(
        "记住密钥（保存到本机，下次自动填）",
        value=bool(get_config_value("LLM_REMEMBER", "").strip()),
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
        default_model = get_config_value("ZHIPU_MODEL", "glm-4-flash")
        model_name = st.sidebar.selectbox(
            "模型名称",
            options=zhipu_models,
            index=zhipu_models.index(default_model) if default_model in zhipu_models else 0,
            format_func=lambda value: zhipu_labels.get(value, value),
            help="预算紧就用 glm-4-flash（免费）；想要更好的分析效果用 glm-4-plus。",
        )
        base_url = st.sidebar.text_input(
            "接口地址",
            value=get_config_value("ZHIPU_BASE_URL", "https://open.bigmodel.cn/api/paas/v4"),
            help="智谱开放平台的官方地址，一般不用改。",
        )
    elif provider == "deepseek":
        deepseek_models = ["deepseek-chat", "deepseek-reasoner"]
        deepseek_labels = {
            "deepseek-chat": "deepseek-chat（V3，日常推荐，快又便宜）",
            "deepseek-reasoner": "deepseek-reasoner（R1，深度推理，更强但慢）",
        }
        default_model = get_config_value("DEEPSEEK_MODEL", "deepseek-chat")
        model_name = st.sidebar.selectbox(
            "模型名称",
            options=deepseek_models,
            index=deepseek_models.index(default_model) if default_model in deepseek_models else 0,
            format_func=lambda value: deepseek_labels.get(value, value),
            help="日常用 deepseek-chat；要更强的推理分析用 deepseek-reasoner。",
        )
        base_url = st.sidebar.text_input(
            "接口地址",
            value=get_config_value("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            help="DeepSeek 官方地址，一般不用改。",
        )
    elif provider == "dashscope":
        default_model = get_config_value("QWEN_MODEL", "qwen-plus")
        model_name = st.sidebar.selectbox(
            "模型名称",
            options=["qwen-plus", "qwen-turbo", "qwen-max"],
            index=["qwen-plus", "qwen-turbo", "qwen-max"].index(default_model)
            if default_model in {"qwen-plus", "qwen-turbo", "qwen-max"}
            else 0,
        )
        base_url = st.sidebar.text_input(
            "接口地址",
            value=get_config_value(
                "DASHSCOPE_BASE_URL",
                "https://dashscope.aliyuncs.com/compatible-mode/v1",
            ),
            help="默认使用 DashScope 的兼容接口地址。",
        )
    else:
        default_use_responses_api = get_config_value("OPENAI_USE_RESPONSES_API", "false").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        model_name = st.sidebar.text_input(
            "模型名称",
            value=get_config_value("OPENAI_MODEL", "gpt-4o-mini"),
            help="填写你的 OpenAI 兼容网关实际支持的模型名。",
        )
        base_url = st.sidebar.text_input(
            "接口地址",
            value=get_config_value("OPENAI_BASE_URL", ""),
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
            save_credentials(provider, api_key.strip(), model_name.strip(), base_url.strip())
            st.sidebar.caption("已保存到本机，下次自动填。")
        except Exception as exc:
            st.sidebar.caption("密钥保存失败：" + str(exc))
    elif not remember_key and get_config_value("LLM_REMEMBER", "").strip():
        try:
            forget_credentials(provider)
        except Exception:
            pass

    return LLMConfig(
        provider=provider,
        api_key=api_key,
        model_name=model_name,
        base_url=base_url,
        use_responses_api=use_responses_api,
    )
