from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from utils.llm_service import LLMService
from utils.sandbox import run_in_sandbox, validate_code_safety


@dataclass
class QueryExecutionResult:
    """Represents one natural language query execution round."""

    question: str
    code: str
    result_frame: pd.DataFrame
    explanation: str
    attempts: int
    attempted_codes: list[str]
    errors: list[str]


class PandasQueryAgent:
    """Generates pandas code, executes it in a sandbox, and retries on failure.

    Safety enforcement lives in :mod:`utils.sandbox`: the AST allowlist runs
    before spawning anything, and the code itself executes in a killable child
    process with a timeout and memory ceiling — never in this process.
    """

    def __init__(
        self,
        llm_service: LLMService,
        max_retries: int = 2,
        timeout_s: float | None = None,
        memory_mb: int | None = None,
    ) -> None:
        self.llm_service = llm_service
        self.max_retries = max_retries
        self.timeout_s = timeout_s
        self.memory_mb = memory_mb

    # Kept as a class-level alias because UI code and tests reference the
    # validator through the agent; the implementation lives in utils.sandbox.
    _validate_code_safety = staticmethod(validate_code_safety)

    def ask(
        self,
        question: str,
        df: pd.DataFrame,
        dataframe_profile: dict[str, Any],
        desensitize: bool = False,
    ) -> QueryExecutionResult:
        """Runs the generate-execute-repair loop for one question.

        When ``desensitize`` is True, the result preview sent to the model for
        its written explanation has text-column values masked, so real names
        in the answer table are not transmitted.
        """

        previous_code = ""
        previous_error = ""
        attempted_codes: list[str] = []
        errors: list[str] = []

        for attempt in range(1, self.max_retries + 2):
            generated_code = self.llm_service.generate_pandas_code(
                question=question,
                dataframe_profile=dataframe_profile,
                previous_code=previous_code,
                error_message=previous_error,
            )
            sanitized_code = self._strip_code_fences(generated_code)
            attempted_codes.append(sanitized_code)

            try:
                sandbox_result = run_in_sandbox(
                    sanitized_code, df, timeout_s=self.timeout_s, memory_mb=self.memory_mb
                )
                if not sandbox_result.ok:
                    raise RuntimeError(sandbox_result.error)

                result_frame = sandbox_result.result_frame
                explanation = self.llm_service.explain_query_result(
                    question=question,
                    result_preview=self._format_result_preview(result_frame.head(10), desensitize),
                    generated_code=sanitized_code,
                )

                return QueryExecutionResult(
                    question=question,
                    code=sanitized_code,
                    result_frame=result_frame,
                    explanation=explanation,
                    attempts=attempt,
                    attempted_codes=attempted_codes,
                    errors=errors,
                )
            except Exception as exc:
                previous_code = sanitized_code
                previous_error = str(exc)
                errors.append(f"第 {attempt} 次执行失败：{exc}")

        raise RuntimeError(
            "自动纠错后仍无法完成本次查询，请调整提问方式或检查字段名。\n"
            + "\n".join(errors)
        )

    @staticmethod
    def _strip_code_fences(code: str) -> str:
        """Removes a wrapping Markdown code fence if the model returns one.

        Handles ```python / ```py / bare ``` fences without touching the code
        body (the old version blindly deleted the first literal "python").
        """

        cleaned = code.strip()
        if not cleaned.startswith("```"):
            return cleaned

        lines = cleaned.splitlines()
        # Drop the opening fence line (``` optionally followed by a language tag).
        lines = lines[1:]
        # Drop the closing fence line if present.
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        return "\n".join(lines).strip()

    @staticmethod
    def _format_result_preview(result_frame: pd.DataFrame, desensitize: bool = False) -> str:
        """Formats compact previews without requiring optional markdown deps."""

        preview = result_frame
        if desensitize and not result_frame.empty:
            # 脱敏：文本类列的真实取值（可能是姓名/客户名/地区等）替换为占位符，
            # 数值列保留，AI 仍能解读数量级，但不外发具体身份信息。
            preview = result_frame.copy()
            text_columns = preview.select_dtypes(include=["object", "string", "category"]).columns
            for column in text_columns:
                preview[column] = "***"

        try:
            return preview.to_markdown(index=False)
        except Exception:
            return preview.to_string(index=False)
