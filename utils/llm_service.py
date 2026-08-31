from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from openai import OpenAI

try:
    from langchain_community.chat_models import ChatTongyi
except ImportError:  # pragma: no cover - optional compatibility path
    ChatTongyi = None


ProviderType = Literal["dashscope", "openai_compatible", "zhipu", "deepseek"]

# Providers that speak the OpenAI chat-completions wire format via the OpenAI SDK.
_OPENAI_SDK_PROVIDERS = {"openai_compatible", "zhipu", "deepseek"}


@dataclass(frozen=True)
class LLMConfig:
    """Normalizes model provider settings collected from UI or env vars."""

    provider: ProviderType
    api_key: str
    model_name: str
    base_url: str
    temperature: float = 0.1
    use_responses_api: bool = False


class LLMService:
    """Builds provider-specific text generation calls for analysis features."""

    def __init__(self, config: LLMConfig) -> None:
        self.config = config
        self.parser = StrOutputParser()
        self.langchain_llm = self._build_langchain_llm(config) if config.provider == "dashscope" else None
        self.openai_client = self._build_openai_client(config) if config.provider in _OPENAI_SDK_PROVIDERS else None

    def generate_pandas_code(
        self,
        question: str,
        dataframe_profile: dict,
        previous_code: str = "",
        error_message: str = "",
    ) -> str:
        """Generates executable pandas code for the current question."""

        system_prompt = (
            "你是一名资深 pandas 数据分析工程师。"
            "你只能基于变量 df 生成可执行 Python 代码。"
            "只允许使用 pandas 和 numpy，它们已经分别以 pd 和 np 提供。"
            "禁止 import、文件读写、网络请求、eval、exec、open、os、sys、subprocess。"
            "必须把最终结果赋值给 result 变量。"
            "严格使用“数据概况”里给出的真实列名（区分中英文与大小写），不要臆造列名；"
            "涉及筛选某个类别时，使用 column_value_hints 里列出的真实取值，不要凭空编造取值字符串。"
            "聚合要选对口径：金额、销量、数量、次数等可累加指标用求和（sum）；"
            "比率、占比、评分、单价、平均值类指标要用求平均（mean）而不是求和。"
            "如果返回表格，请保持列名清晰；分组统计时必须显式排序（通常按指标值降序）。"
            "不要使用名为“是否异常值”“异常值字段”的辅助列做业务统计。"
            "只返回代码本身，不要输出 Markdown 代码块，不要解释。"
        )
        user_prompt = (
            "数据概况如下：\n{dataframe_profile}\n\n"
            "用户问题：\n{question}\n\n"
            "上一次失败代码：\n{previous_code}\n\n"
            "执行报错：\n{error_message}\n\n"
            "请输出一段新的、可直接执行的修正版 pandas 代码。"
        ).format(
            dataframe_profile=json.dumps(dataframe_profile, ensure_ascii=False, default=str, indent=2),
            question=question,
            previous_code=previous_code or "无",
            error_message=error_message or "无",
        )

        return self._generate_text(system_prompt, user_prompt)

    def explain_query_result(self, question: str, result_preview: str, generated_code: str) -> str:
        """Explains the result table in business language."""

        system_prompt = (
            "你是一名业务数据分析顾问。"
            "请用中文解释数据结果，输出简洁专业的 Markdown。"
            "固定包含三部分：结果概览、业务含义、下一步建议。"
        )
        user_prompt = (
            "用户问题：\n{question}\n\n"
            "执行代码：\n{generated_code}\n\n"
            "结果预览：\n{result_preview}"
        ).format(
            question=question,
            generated_code=generated_code,
            result_preview=result_preview,
        )

        return self._generate_text(system_prompt, user_prompt)

    def generate_business_report(
        self,
        data_profile: dict,
        cleaning_report: dict,
        question: str,
        result_summary: str,
        chart_summary: str,
        statistics: dict | None = None,
    ) -> str:
        """Builds an AI analysis report grounded in real whole-table statistics."""

        system_prompt = (
            "你是一名资深 BI 分析师和业务顾问。"
            "请根据“全表统计”“数据摘要”“清洗报告”“图表摘要”和“问答结果”，"
            "输出面向业务负责人的中文分析报告。"
            "“全表统计”是基于全部数据算出的真实数字（各数值列的最大/最小/均值/中位数/总和、"
            "分类列的 Top 取值及占比、时间范围、强相关字段），这是你分析的主要依据。"
            "结论必须引用这些真实数字（写明具体数值/占比/字段名），不要泛泛而谈。"
            "使用 Markdown，固定包含以下章节：\n"
            "## 核心发现\n## 业务分析\n## 风险提示\n## 优化建议\n"
            "每个章节给出 2 到 4 条要点，每条尽量带上支撑它的具体数字。"
            "绝对不要编造统计里没有的数据；如果某方面信息不足，明确说“数据不足以判断”。"
        )
        user_prompt = (
            "全表统计（真实计算结果，请重点依据这里）：\n{statistics}\n\n"
            "数据摘要：\n{data_profile}\n\n"
            "数据清洗报告：\n{cleaning_report}\n\n"
            "用户关注问题：\n{question}\n\n"
            "问答结果摘要：\n{result_summary}\n\n"
            "图表摘要：\n{chart_summary}"
        ).format(
            statistics=json.dumps(statistics or {}, ensure_ascii=False, default=str, indent=2),
            data_profile=json.dumps(data_profile, ensure_ascii=False, default=str, indent=2),
            cleaning_report=json.dumps(cleaning_report, ensure_ascii=False, default=str, indent=2),
            question=question or "本次尚未输入具体问题，请基于整体数据进行分析。",
            result_summary=result_summary or "暂无问答结果。",
            chart_summary=chart_summary or "暂无图表摘要。",
        )

        return self._generate_text(system_prompt, user_prompt)

    def _generate_text(self, system_prompt: str, user_prompt: str) -> str:
        """Routes prompt execution through the selected provider implementation."""

        if self.config.provider == "dashscope":
            raw = self._generate_text_with_langchain(system_prompt, user_prompt)
        else:
            raw = self._generate_text_with_openai_sdk(system_prompt, user_prompt)
        return _strip_wrapping_code_fence(raw)

    def _generate_text_with_langchain(self, system_prompt: str, user_prompt: str) -> str:
        """Uses LangChain for the DashScope/Tongyi path."""

        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt),
                ("human", user_prompt),
            ]
        )
        chain = prompt | self.langchain_llm | self.parser
        return chain.invoke({}).strip()

    def _generate_text_with_openai_sdk(self, system_prompt: str, user_prompt: str) -> str:
        """Uses the official OpenAI SDK to avoid incompatible gateway wrappers."""

        if self.openai_client is None:
            raise RuntimeError("OpenAI-compatible client was not initialized.")

        if self.config.use_responses_api:
            response = self.openai_client.responses.create(
                model=self.config.model_name,
                instructions=system_prompt,
                input=user_prompt,
                temperature=self.config.temperature,
            )
            text = _extract_text_from_responses_api(response)
        else:
            response = self.openai_client.chat.completions.create(
                model=self.config.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=self.config.temperature,
            )
            text = _extract_text_from_chat_completions(response)

        cleaned = (text or "").strip()
        if not cleaned:
            raise RuntimeError("模型返回为空，无法生成结果。")
        return cleaned

    @staticmethod
    def _build_langchain_llm(config: LLMConfig) -> BaseChatModel:
        """Builds the DashScope/Tongyi model with a compatible fallback."""

        if ChatTongyi is not None:
            try:
                return ChatTongyi(
                    model=config.model_name,
                    dashscope_api_key=config.api_key,
                    temperature=config.temperature,
                )
            except TypeError:
                try:
                    return ChatTongyi(
                        model_name=config.model_name,
                        dashscope_api_key=config.api_key,
                        temperature=config.temperature,
                    )
                except Exception:
                    pass
            except Exception:
                pass

        kwargs = {
            "model": config.model_name,
            "api_key": config.api_key,
            "base_url": config.base_url,
            "temperature": config.temperature,
        }
        try:
            return ChatOpenAI(**kwargs)
        except TypeError:
            return ChatOpenAI(
                model_name=config.model_name,
                openai_api_key=config.api_key,
                openai_api_base=config.base_url,
                temperature=config.temperature,
            )

    @staticmethod
    def _build_openai_client(config: LLMConfig) -> OpenAI:
        """Builds a raw OpenAI SDK client for arbitrary compatible gateways."""

        return OpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
        )


def _strip_wrapping_code_fence(text: str) -> str:
    """Removes a single ```lang ... ``` fence that wraps the whole response.

    Some models (e.g. GLM) wrap the entire Markdown answer in a ```markdown fence,
    which then renders as a literal code block instead of formatted text. We only
    strip when the whole content is one clean fenced block, so genuine inline code
    inside an answer is left untouched.
    """

    if not text:
        return text
    stripped = text.strip()
    if not stripped.startswith("```"):
        return text

    lines = stripped.splitlines()
    if len(lines) < 2 or lines[-1].strip() != "```":
        return text

    inner = "\n".join(lines[1:-1]).strip()
    return inner or text


def _extract_text_from_chat_completions(response: Any) -> str:
    """Extracts text from chat completions style responses."""

    try:
        message = response.choices[0].message
    except Exception as exc:  # pragma: no cover - defensive gateway handling
        raise RuntimeError(f"无法解析聊天补全返回结果：{exc}") from exc

    content = getattr(message, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text", "")))
            else:
                item_text = getattr(item, "text", None)
                if item_text:
                    parts.append(str(item_text))
        return "\n".join(part for part in parts if part)
    return str(content or "")


def _extract_text_from_responses_api(response: Any) -> str:
    """Extracts text from responses API outputs across compatible gateways."""

    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return output_text

    collected: list[str] = []

    for output in getattr(response, "output", []) or []:
        content_items = getattr(output, "content", None)
        if content_items is None and isinstance(output, dict):
            content_items = output.get("content", [])

        for item in content_items or []:
            item_type = getattr(item, "type", None)
            if item_type is None and isinstance(item, dict):
                item_type = item.get("type")

            if item_type in {"output_text", "text"}:
                text_value = getattr(item, "text", None)
                if text_value is None and isinstance(item, dict):
                    text_value = item.get("text")
                if text_value:
                    collected.append(str(text_value))

    if collected:
        return "\n".join(collected)

    try:
        return json.dumps(response.model_dump(), ensure_ascii=False)
    except Exception as exc:  # pragma: no cover - defensive gateway handling
        raise RuntimeError(f"无法解析 Responses API 返回结果：{exc}") from exc
