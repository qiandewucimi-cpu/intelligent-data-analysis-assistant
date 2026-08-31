from __future__ import annotations

import ast
import traceback
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from utils.llm_service import LLMService


# Generated code is model output and must be treated as untrusted input.  Keep
# access to the pandas/numpy module namespaces on an explicit allowlist so APIs
# such as ``pd.read_csv`` or ``np.load`` can never be used to read local secrets.
_SAFE_PANDAS_ATTRIBUTES = {
    "Categorical",
    "DataFrame",
    "Grouper",
    "NA",
    "NamedAgg",
    "NaT",
    "Series",
    "Timestamp",
    "api.types.is_bool_dtype",
    "api.types.is_datetime64_any_dtype",
    "api.types.is_numeric_dtype",
    "concat",
    "crosstab",
    "cut",
    "isna",
    "merge",
    "notna",
    "pivot_table",
    "qcut",
    "to_datetime",
    "to_numeric",
}

_SAFE_NUMPY_ATTRIBUTES = {
    "abs",
    "array",
    "average",
    "bool_",
    "ceil",
    "clip",
    "corrcoef",
    "datetime64",
    "exp",
    "float64",
    "floor",
    "inf",
    "int64",
    "isfinite",
    "isinf",
    "isnan",
    "log",
    "log10",
    "max",
    "mean",
    "median",
    "min",
    "nan",
    "number",
    "percentile",
    "quantile",
    "round",
    "sqrt",
    "std",
    "sum",
    "unique",
    "var",
    "where",
}


@dataclass
class QueryExecutionResult:
    """Represents one natural language query execution round."""

    question: str
    code: str
    result: Any
    result_frame: pd.DataFrame
    explanation: str
    attempts: int
    attempted_codes: list[str]
    errors: list[str]


class PandasQueryAgent:
    """Generates pandas code, executes it safely, and retries on failure."""

    def __init__(self, llm_service: LLMService, max_retries: int = 2) -> None:
        self.llm_service = llm_service
        self.max_retries = max_retries

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
                self._validate_code_safety(sanitized_code)
                raw_result = self._execute_code(sanitized_code, df)
                result_frame = self._normalize_result(raw_result)
                explanation = self.llm_service.explain_query_result(
                    question=question,
                    result_preview=self._format_result_preview(result_frame.head(10), desensitize),
                    generated_code=sanitized_code,
                )

                return QueryExecutionResult(
                    question=question,
                    code=sanitized_code,
                    result=raw_result,
                    result_frame=result_frame,
                    explanation=explanation,
                    attempts=attempt,
                    attempted_codes=attempted_codes,
                    errors=errors,
                )
            except Exception as exc:
                previous_code = sanitized_code
                previous_error = f"{exc}\n{traceback.format_exc(limit=1)}"
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
    def _validate_code_safety(code: str) -> None:
        """Rejects unsafe Python before execution."""

        tree = ast.parse(code)
        parents = {
            child: parent
            for parent in ast.walk(tree)
            for child in ast.iter_child_nodes(parent)
        }
        # Note: lambda / for / comprehensions are allowed — they are essential for
        # everyday pandas (apply(lambda...), assign(...=lambda d: ...)) and carry no
        # extra risk once imports/builtins/file-IO are locked down below. We still
        # block `while` (can hang the app) and async/def/class/import/try constructs.
        banned_nodes = (
            ast.Import,
            ast.ImportFrom,
            ast.With,
            ast.AsyncWith,
            ast.Try,
            ast.Raise,
            ast.Delete,
            ast.FunctionDef,
            ast.AsyncFunctionDef,
            ast.ClassDef,
            ast.AsyncFor,
            ast.While,
        )
        banned_names = {
            "eval",
            "exec",
            "open",
            "__import__",
            "input",
            "compile",
            "globals",
            "locals",
            "vars",
            "getattr",
            "setattr",
            "delattr",
            "os",
            "sys",
            "subprocess",
            "pathlib",
            "shutil",
            "socket",
            "requests",
        }
        # Block methods that write files / persist data. We intentionally do NOT
        # ban pandas data ops like `replace`/`rename`/`remove` here — those are
        # everyday analysis methods, and the real file-system functions (os.remove,
        # Path.unlink, ...) are already unreachable because os/pathlib/shutil are
        # banned identifiers and file reads (read_*) need a path the sandbox can't build.
        banned_attribute_names = {
            "eval",
            "load",
            "loads",
            "loadtxt",
            "memmap",
            "open_memmap",
            "pipe",
            "query",
            "read_clipboard",
            "read_csv",
            "read_excel",
            "read_feather",
            "read_fwf",
            "read_hdf",
            "read_html",
            "read_json",
            "read_orc",
            "read_parquet",
            "read_pickle",
            "read_sas",
            "read_spss",
            "read_sql",
            "read_sql_query",
            "read_sql_table",
            "read_stata",
            "read_table",
            "read_xml",
            "savez",
            "savez_compressed",
            "to_csv",
            "to_excel",
            "to_json",
            "to_pickle",
            "to_parquet",
            "to_sql",
            "to_clipboard",
            "save",
            "dump",
            "dumps",
            "write",
            "writelines",
        }

        result_assigned = False

        for node in ast.walk(tree):
            if isinstance(node, banned_nodes):
                raise ValueError(f"检测到不允许的语法节点：{type(node).__name__}")

            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "result":
                        result_assigned = True

            if isinstance(node, ast.Name) and node.id in banned_names:
                raise ValueError(f"检测到不允许的标识符：{node.id}")

            # Do not allow the module objects themselves to be copied into an
            # alias/container.  Otherwise ``module = pd`` could bypass the
            # direct-module allowlist below and reach ``module.io``.
            if isinstance(node, ast.Name) and node.id in {"pd", "np"}:
                parent = parents.get(node)
                if not (isinstance(parent, ast.Attribute) and parent.value is node):
                    raise ValueError(f"不允许直接引用模块对象：{node.id}")

            if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
                raise ValueError("检测到不允许的双下划线属性访问。")

            if isinstance(node, ast.Attribute) and node.attr in banned_attribute_names:
                raise ValueError(f"检测到不允许的方法调用：{node.attr}")

            if isinstance(node, ast.Attribute):
                module_access = PandasQueryAgent._module_attribute_path(node)
                if module_access is not None:
                    module_name, attribute_path = module_access
                    allowed = (
                        _SAFE_PANDAS_ATTRIBUTES
                        if module_name == "pd"
                        else _SAFE_NUMPY_ATTRIBUTES
                    )
                    if attribute_path not in allowed and not any(
                        permitted.startswith(attribute_path + ".") for permitted in allowed
                    ):
                        raise ValueError(
                            f"检测到不允许的 {module_name} 模块访问：{attribute_path}"
                        )

        if not result_assigned:
            raise ValueError("生成代码未把最终结果赋值给 result。")

    @staticmethod
    def _module_attribute_path(node: ast.Attribute) -> tuple[str, str] | None:
        """Returns ``(pd|np, dotted_path)`` for direct module attribute access."""

        parts = [node.attr]
        value = node.value
        while isinstance(value, ast.Attribute):
            parts.append(value.attr)
            value = value.value
        if isinstance(value, ast.Name) and value.id in {"pd", "np"}:
            return value.id, ".".join(reversed(parts))
        return None

    @staticmethod
    def _execute_code(code: str, df: pd.DataFrame) -> Any:
        """Executes the generated code in a restricted namespace."""

        safe_builtins = {
            "abs": abs,
            "all": all,
            "any": any,
            "bool": bool,
            "dict": dict,
            "enumerate": enumerate,
            "float": float,
            "int": int,
            "len": len,
            "list": list,
            "max": max,
            "min": min,
            "range": range,
            "round": round,
            "set": set,
            "sorted": sorted,
            "str": str,
            "sum": sum,
            "tuple": tuple,
            "zip": zip,
        }
        globals_dict = {"__builtins__": safe_builtins}
        locals_dict = {"df": df.copy(), "pd": pd, "np": np, "result": None}

        exec(code, globals_dict, locals_dict)

        if "result" not in locals_dict:
            raise ValueError("执行完成但未得到 result 变量。")
        return locals_dict["result"]

    @staticmethod
    def _index_is_meaningful(index: pd.Index) -> bool:
        """Returns True when an index should be kept as a column on display."""

        if isinstance(index, pd.MultiIndex):
            return True
        if index.name is not None:
            return True
        # An unnamed default integer range is just row positions — drop it.
        return not isinstance(index, pd.RangeIndex)

    @staticmethod
    def _normalize_result(result: Any) -> pd.DataFrame:
        """Normalizes different Python objects into a displayable DataFrame."""

        if isinstance(result, pd.DataFrame):
            # Only surface the index when it carries meaning (e.g. a groupby key).
            # A plain auto-number index would just add a noisy "index" column.
            if PandasQueryAgent._index_is_meaningful(result.index):
                return result.reset_index(drop=False)
            return result.reset_index(drop=True)

        if isinstance(result, pd.Series):
            frame = result.reset_index()
            if frame.shape[1] == 2:
                first_name = frame.columns[0]
                if first_name in (0, "index", None):
                    first_name = "分组"
                frame.columns = [str(first_name), result.name or "结果"]
            return frame

        if isinstance(result, pd.Index):
            return pd.DataFrame({"结果": result.tolist()})

        if isinstance(result, dict):
            return pd.DataFrame(
                {"字段": list(result.keys()), "结果": list(result.values())}
            )

        if isinstance(result, (list, tuple, set)):
            if not result:
                return pd.DataFrame({"结果": []})
            first_item = next(iter(result))
            if isinstance(first_item, dict):
                return pd.DataFrame(list(result))
            return pd.DataFrame({"结果": list(result)})

        return pd.DataFrame({"结果": [result]})

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
