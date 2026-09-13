"""Sandbox child process: validate -> exec -> normalize -> JSON result.

Runs as ``python -m analyzer.sandbox_worker``.  Reads one JSON request from
stdin::

    {"code": "...", "input_pkl": "<path>", "output_json": "<path>"}

and writes one JSON object to the output path::

    {"status": "ok", "result_split": {...}}          on success
    {"status": "error", "error": "..."}              on any failure

The pickle input was produced by the parent (trusted).  Nothing this process
emits is ever pickled — the parent deserializes only JSON, because this
process just ran untrusted code.
"""

from __future__ import annotations

import json
import sys
import traceback

import numpy as np
import pandas as pd

from analyzer.executor import SAFE_BUILTINS, validate_code_safety


def _index_is_meaningful(index: pd.Index) -> bool:
    """True when an index should be kept as a column on display."""

    if isinstance(index, pd.MultiIndex):
        return True
    if index.name is not None:
        return True
    # An unnamed default integer range is just row positions — drop it.
    return not isinstance(index, pd.RangeIndex)


def _normalize_result(result: Any) -> pd.DataFrame:
    """Normalizes different Python objects into a displayable DataFrame."""

    if isinstance(result, pd.DataFrame):
        # Only surface the index when it carries meaning (e.g. a groupby key).
        if _index_is_meaningful(result.index):
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


def _execute(code: str, df: pd.DataFrame) -> Any:
    """Executes validated code against a restricted namespace."""

    locals_dict = {"df": df.copy(), "pd": pd, "np": np, "result": None}
    exec(code, {"__builtins__": SAFE_BUILTINS}, locals_dict)  # noqa: S102 - sandboxed by design
    return locals_dict["result"]


def _write(path: str, payload: dict) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False)


def main() -> int:
    request = json.loads(sys.stdin.read())
    output_path = request["output_json"]

    try:
        df = pd.read_pickle(request["input_pkl"])
    except Exception as exc:
        _write(output_path, {"status": "error", "error": f"无法载入数据：{exc}"})
        return 0

    code = request["code"]
    try:
        # Defense in depth: the parent already validated, but this process
        # must never trust that it did.
        validate_code_safety(code)
        raw_result = _execute(code, df)
        frame = _normalize_result(raw_result)
        result_split = json.loads(
            frame.to_json(orient="split", date_format="iso", index=False, force_ascii=False)
        )
        _write(output_path, {"status": "ok", "result_split": result_split})
    except Exception as exc:
        detail = f"{type(exc).__name__}: {exc}"
        traceback.print_exc(file=sys.stderr)
        _write(output_path, {"status": "error", "error": detail})
    return 0


if __name__ == "__main__":
    sys.exit(main())
