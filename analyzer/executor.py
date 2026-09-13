"""Sandbox for executing LLM-generated pandas code in a throwaway subprocess.

Trust model
-----------
Generated code is untrusted input.  Two layers back that claim:

1. Static: ``validate_code_safety`` runs an AST allowlist before any process
   is spawned (fast fail) and again inside the child (defense in depth).
2. Dynamic: the code never runs in the Streamlit process.  It runs in a child
   Python process with a restricted namespace, a hard timeout, and a memory
   watchdog; a runaway child is killed instead of hanging the app.

Data crosses the boundary asymmetrically:

* parent -> child: the DataFrame is pickled to a temp file.  That payload is
  produced by the parent (trusted), so deserializing it in the child is safe.
* child -> parent: the child executed untrusted code, so nothing it emits may
  be deserialized.  Results come back as JSON (``orient="split"``) only.

This module deliberately does not import anything from the app (llm_service,
streamlit, ...) so the worker stays lean and the import graph stays acyclic.
"""

from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from typing import Any

import pandas as pd

# Generated code may only touch a curated slice of the pandas/NumPy namespaces
# so APIs such as ``pd.read_csv`` or ``np.load`` can never reach local files.
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

BANNED_NODES = (
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

BANNED_NAMES = {
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

# Methods that write files / persist data.  Everyday pandas data ops such as
# ``replace``/``rename`` stay legal — the real filesystem functions are
# unreachable because os/pathlib/shutil are banned identifiers and every
# ``read_*`` loader is blocked above.
BANNED_ATTRIBUTE_NAMES = {
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

SAFE_BUILTINS = {
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

DEFAULT_TIMEOUT_SECONDS = 20.0
DEFAULT_MEMORY_MB = 1024
_POLL_INTERVAL_SECONDS = 0.2


@dataclass
class SandboxResult:
    """Outcome of one sandbox run; ``kind`` explains a failure."""

    ok: bool
    result_frame: pd.DataFrame | None = None
    error: str = ""
    kind: str = ""  # "", "rejected", "timeout", "memory", "error"


def sandbox_limits_from_env() -> tuple[float, int]:
    """Reads the configured timeout / memory ceiling (used when unset by callers)."""

    try:
        timeout_s = float(os.getenv("SANDBOX_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS))
    except ValueError:
        timeout_s = DEFAULT_TIMEOUT_SECONDS
    try:
        memory_mb = int(os.getenv("SANDBOX_MEMORY_MB", DEFAULT_MEMORY_MB))
    except ValueError:
        memory_mb = DEFAULT_MEMORY_MB
    return max(timeout_s, 1.0), max(memory_mb, 64)


def validate_code_safety(code: str) -> None:
    """Rejects unsafe Python before execution; raises ``ValueError``."""

    tree = ast.parse(code)
    parents = {
        child: parent
        for parent in ast.walk(tree)
        for child in ast.iter_child_nodes(parent)
    }
    # lambda / for / comprehensions are allowed — they are essential for
    # everyday pandas (apply(lambda...), assign(...=lambda d: ...)) and carry
    # no extra risk once imports/builtins/file-IO are locked down.  ``while``
    # is still blocked (can hang the app) alongside async/def/class/import/try.
    result_assigned = False

    for node in ast.walk(tree):
        if isinstance(node, BANNED_NODES):
            raise ValueError(f"检测到不允许的语法节点：{type(node).__name__}")

        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "result":
                    result_assigned = True

        if isinstance(node, ast.Name) and node.id in BANNED_NAMES:
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

        if isinstance(node, ast.Attribute) and node.attr in BANNED_ATTRIBUTE_NAMES:
            raise ValueError(f"检测到不允许的方法调用：{node.attr}")

        if isinstance(node, ast.Attribute):
            module_access = _module_attribute_path(node)
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


def run_in_sandbox(
    code: str,
    df: pd.DataFrame,
    timeout_s: float | None = None,
    memory_mb: int | None = None,
) -> SandboxResult:
    """Validates the code, then executes it in a killable child process.

    Defaults for ``timeout_s`` / ``memory_mb`` come from the
    ``SANDBOX_TIMEOUT_SECONDS`` / ``SANDBOX_MEMORY_MB`` environment variables.
    """

    env_timeout, env_memory = sandbox_limits_from_env()
    timeout_s = env_timeout if timeout_s is None else timeout_s
    memory_mb = env_memory if memory_mb is None else memory_mb

    try:
        validate_code_safety(code)
    except ValueError as exc:
        return SandboxResult(ok=False, error=str(exc), kind="rejected")

    workdir = tempfile.mkdtemp(prefix="sandbox_")
    input_path = os.path.join(workdir, "input.pkl")
    output_path = os.path.join(workdir, "output.json")
    try:
        # Parent -> child payload is parent-generated (trusted), so pickle is fine.
        pd.to_pickle(df, input_path)
        request = {"code": code, "input_pkl": input_path, "output_json": output_path}

        child_env = os.environ.copy()
        child_env["PYTHONIOENCODING"] = "utf-8"
        # Make ``-m analyzer.sandbox_worker`` resolvable regardless of the
        # caller's working directory (the CLI may run from anywhere).
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        child_env["PYTHONPATH"] = project_root + os.pathsep + child_env.get("PYTHONPATH", "")
        proc = subprocess.Popen(
            [sys.executable, "-m", "analyzer.sandbox_worker"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=child_env,
            text=True,
            encoding="utf-8",
        )
        # On Windows a venv's python.exe can be a launcher stub that spawns the
        # real interpreter as its child — memory and kill must target the whole
        # process tree, not just the direct child.
        try:
            import psutil

            tree_root = psutil.Process(proc.pid)
        except Exception:
            tree_root = None

        exceeded = _watchdog(proc, tree_root, timeout_s, memory_mb)
        exceeded["timeout_s"] = f"{timeout_s:g}"
        exceeded["memory_mb"] = str(memory_mb)
        try:
            _stdout, _stderr = proc.communicate(input=json.dumps(request), timeout=timeout_s)
        except subprocess.TimeoutExpired:
            exceeded["reason"] = exceeded.get("reason") or "timeout"
            _kill_tree(proc, tree_root)
            try:
                _stdout, _stderr = proc.communicate(timeout=5)
            except Exception:
                _stdout, _stderr = "", ""

        return _collect(proc, output_path, exceeded, _stderr or "")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _watchdog(
    proc: subprocess.Popen,
    tree_root: Any,
    timeout_s: float,
    memory_mb: int,
) -> dict[str, str]:
    """Starts a daemon thread that kills the process tree on timeout / OOM."""

    exceeded: dict[str, str] = {}
    deadline = time.monotonic() + timeout_s

    def watch() -> None:
        while proc.poll() is None:
            # Guard on the reason key, not dict truthiness: the parent adds
            # formatting keys (timeout_s / memory_mb) after this thread starts.
            if not exceeded.get("reason"):
                if time.monotonic() >= deadline:
                    exceeded["reason"] = "timeout"
                    _kill_tree(proc, tree_root)
                    return
                if tree_root is not None:
                    try:
                        rss_bytes = 0
                        for member in [tree_root, *tree_root.children(recursive=True)]:
                            try:
                                rss_bytes += member.memory_info().rss
                            except Exception:
                                pass  # member vanished between listing and query
                        rss_mb = rss_bytes / (1024 * 1024)
                        if rss_mb > memory_mb:
                            exceeded["reason"] = "memory"
                            exceeded["rss_mb"] = f"{rss_mb:.0f}"
                            _kill_tree(proc, tree_root)
                            return
                    except Exception:
                        pass
            time.sleep(_POLL_INTERVAL_SECONDS)

    thread = threading.Thread(target=watch, daemon=True)
    thread.start()
    return exceeded


def _kill_tree(proc: subprocess.Popen, tree_root: Any) -> None:
    """Kills descendants first, then the direct child, so nothing escapes."""

    if tree_root is not None:
        try:
            descendants = tree_root.children(recursive=True)
        except Exception:
            descendants = []
        for member in descendants:
            try:
                member.kill()
            except Exception:
                pass
        try:
            tree_root.kill()
        except Exception:
            pass
    try:
        proc.kill()
    except Exception:
        pass


def _collect(
    proc: subprocess.Popen,
    output_path: str,
    exceeded: dict[str, str],
    stderr_text: str,
) -> SandboxResult:
    """Turns the finished child's artifacts into a ``SandboxResult``."""

    reason = exceeded.get("reason", "")
    if reason == "timeout":
        return SandboxResult(
            ok=False,
            error=f"沙箱执行超时（超过 {exceeded.get('timeout_s', '')} 秒），已强制终止。",
            kind="timeout",
        )
    if reason == "memory":
        return SandboxResult(
            ok=False,
            error=(
                f"沙箱内存超限（{exceeded.get('rss_mb', '?')} MB，"
                f"上限 {exceeded.get('memory_mb', '')} MB），已强制终止。"
            ),
            kind="memory",
        )

    if proc.returncode != 0:
        return SandboxResult(
            ok=False,
            error=f"沙箱子进程异常退出（exit={proc.returncode}）：{stderr_text[-500:]}",
            kind="error",
        )

    try:
        with open(output_path, encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception as exc:
        return SandboxResult(ok=False, error=f"沙箱未返回结果：{exc}", kind="error")

    if payload.get("status") != "ok":
        return SandboxResult(
            ok=False, error=str(payload.get("error", "未知错误")), kind="error"
        )

    split = payload.get("result_split") or {}
    frame = pd.DataFrame(split.get("data", []), columns=split.get("columns", []))
    return SandboxResult(ok=True, result_frame=frame)
