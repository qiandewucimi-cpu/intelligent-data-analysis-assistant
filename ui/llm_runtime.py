"""Builds the runtime LLMService from the sidebar config (shared by QA & report tabs)."""

from __future__ import annotations

from analyzer.llm import LLMConfig, LLMService


def build_runtime_llm_service(llm_config: LLMConfig) -> LLMService:
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
