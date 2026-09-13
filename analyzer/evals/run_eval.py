"""评测运行器：对引擎跑 18 题评测集，产出成功率 / 收敛 / 延迟指标。

两种模式：
  --dry-run  不调用任何模型。校验题目 schema，并把每题的黄金答案
             （reference 代码）在评测数据上真实执行一遍，确认评测
             基准本身有效。CI 里跑的就是这个模式。
  默认       真实链路评测：每个问题走完整的「生成 -> 沙箱执行 ->
             自动纠错 -> 结果」，与黄金答案判分，输出
             analyzer/evals/results/eval_report.md 与 eval_results.json。

指标口径：
  一轮成功率   attempts == 1 且判分通过的比例（模型一次写对的能力）
  最终成功率   重试预算内判分通过的比例（产品实际交付的能力）
  收敛分布     按 attempts 统计的成功题数
  P50/P95 延迟 每题完整链路的墙钟时间（含全部重试）
"""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from analyzer.llm import PROVIDER_DEFAULTS

EVALS_DIR = Path(__file__).resolve().parent
QUESTIONS_PATH = EVALS_DIR / "questions.jsonl"
RESULTS_DIR = EVALS_DIR / "results"
CATEGORIES = ["单值聚合", "分组聚合", "筛选计算", "时间趋势", "口径陷阱", "数据质量"]
REQUIRED_KEYS = {"id", "category", "question", "reference", "check"}
CHECK_TYPES = {"value_close", "frame_equal"}


def load_questions() -> list[dict[str, Any]]:
    questions: list[dict[str, Any]] = []
    for line_no, line in enumerate(QUESTIONS_PATH.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        item = json.loads(line)
        missing = REQUIRED_KEYS - item.keys()
        if missing:
            raise ValueError(f"questions.jsonl 第 {line_no} 行缺少字段：{missing}")
        if item["category"] not in CATEGORIES:
            raise ValueError(f"{item['id']}：未知类别 {item['category']}")
        check = item["check"]
        if check.get("type") not in CHECK_TYPES:
            raise ValueError(f"{item['id']}：未知判分类型 {check.get('type')}")
        questions.append(item)
    return questions


def build_eval_frame() -> pd.DataFrame:
    """Loads the sample data and applies the product default cleaning."""

    from analyzer.evals.data.generate_sample import ensure_sample_csv
    from ui.data_handler import CleaningOptions, clean_dataframe, default_cleaning_options

    raw = pd.read_csv(ensure_sample_csv())
    cleaned, _ = clean_dataframe(raw, options=CleaningOptions(**default_cleaning_options()))
    # 与 UI 问答入口一致：分析前剥掉清洗辅助标记列。
    return cleaned.drop(columns=[c for c in ("是否异常值", "异常值字段") if c in cleaned.columns])


def _run_reference(code: str, df: pd.DataFrame) -> Any:
    """Executes one golden answer with real pandas (trusted code, not sandboxed)."""

    locals_dict: dict[str, Any] = {"df": df.copy(), "pd": pd, "np": np, "result": None}
    exec(code, {"__builtins__": __builtins__}, locals_dict)  # noqa: S102 - 本仓库自带黄金答案
    return locals_dict["result"]


def _cell_key(value: Any) -> Any:
    """Normalizes one cell for comparison (floats quantized, strings trimmed)."""

    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "<nan>"
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, float, np.integer, np.floating)):
        numeric = float(value)
        if math.isnan(numeric):
            return "<nan>"
        return round(numeric, 4)
    return str(value).strip()


def _frame_rows(frame: pd.DataFrame) -> Counter:
    return Counter(tuple(_cell_key(cell) for cell in row) for row in frame.itertuples(index=False, name=None))


def _first_numeric_column(frame: pd.DataFrame) -> pd.Series | None:
    for column in frame.columns:
        series = pd.to_numeric(frame[column], errors="coerce")
        if series.notna().mean() >= 0.5:
            return series
    return None


def _grade_value_close(
    result_frame: pd.DataFrame, expected: Any, rel_tol: float
) -> tuple[bool, str]:
    """Passes when any single cell of the answer matches the golden number."""

    if isinstance(expected, (int, float, np.integer, np.floating)) and not isinstance(expected, bool):
        expected_value = float(expected)
    else:
        return False, f"黄金答案不是数值（{type(expected).__name__}），无法按 value_close 判分"

    for row in result_frame.itertuples(index=False, name=None):
        for cell in row:
            key = _cell_key(cell)
            if isinstance(key, float):
                if math.isclose(key, expected_value, rel_tol=rel_tol, abs_tol=1e-9):
                    return True, ""
    return False, f"结果中未找到期望值 {expected_value:.4f}（允许相对误差 {rel_tol:.2%}）"


def _grade_frame_equal(
    result_frame: pd.DataFrame,
    reference_frame: pd.DataFrame,
    sorted_desc: bool,
) -> tuple[bool, str]:
    """Passes when the answer's row multiset equals the golden rows (order-insensitive)."""

    if result_frame.empty and reference_frame.empty:
        return True, ""
    if len(result_frame) != len(reference_frame) or result_frame.shape[1] != reference_frame.shape[1]:
        return False, (
            f"形状不一致：结果 {result_frame.shape} vs 黄金 {reference_frame.shape}"
        )

    if sorted_desc:
        series = _first_numeric_column(result_frame)
        if series is not None:
            values = series.dropna().tolist()
            if any(later > current + 1e-9 for current, later in zip(values, values[1:])):
                return False, "要求降序排列，但结果的第一数值列不是非递增的"

    if _frame_rows(result_frame) == _frame_rows(reference_frame):
        return True, ""
    return False, "结果行与黄金答案不一致（数值/取值有出入）"


def grade_question(item: dict[str, Any], result_frame: pd.DataFrame | None, df: pd.DataFrame) -> tuple[bool, str]:
    reference_result = _run_reference(item["reference"], df)
    check = item["check"]

    if check["type"] == "value_close":
        return _grade_value_close(result_frame, reference_result, float(check.get("rel_tol", 0.01)))

    reference_frame = _normalize_like_engine(reference_result)
    return _grade_frame_equal(result_frame, reference_frame, bool(check.get("sorted_desc", False)))


def _normalize_like_engine(raw_result: Any) -> pd.DataFrame:
    """Runs the engine's own result normalization on a golden answer."""

    from analyzer.sandbox_worker import _normalize_result

    return _normalize_result(raw_result)


def run_dry_run(questions: list[dict[str, Any]], df: pd.DataFrame) -> int:
    print(f"评测数据：{df.shape[0]} 行 × {df.shape[1]} 列（种子 42 确定性生成）")
    print(f"  完全重复行：{int(df.duplicated().sum())}")
    print(f"  数量缺失值：{int(df['数量'].isna().sum())}")

    failures = 0
    print(f"\n{'题目':<12}{'类别':<8}黄金答案执行")
    for item in questions:
        try:
            reference_result = _run_reference(item["reference"], df)
            if item["check"]["type"] == "frame_equal":
                normalized = _normalize_like_engine(reference_result)
                detail = f"OK ({normalized.shape[0]} 行 × {normalized.shape[1]} 列)"
            else:
                detail = f"OK (值={reference_result})"
        except Exception as exc:
            failures += 1
            detail = f"失败：{type(exc).__name__}: {exc}"
        print(f"{item['id']:<12}{item['category']:<8}{detail}")

    if failures:
        print(f"\n[FAIL] {failures} 道黄金答案自身执行失败，评测基准无效。")
        return 1
    print(f"\n[OK] {len(questions)} 道题目 schema 与黄金答案全部有效。")
    return 0


def _classify_error(error: str) -> str:
    if "超时" in error:
        return "timeout"
    if "内存超限" in error:
        return "memory"
    if "不允许" in error or "检测到" in error:
        return "sandbox_reject"
    return "error"


def _resolve_config(provider_arg: str | None):
    from analyzer.llm import LLMConfig

    provider = (provider_arg or os.getenv("LLM_PROVIDER", "zhipu")).strip().lower()
    spec = PROVIDER_DEFAULTS.get(provider) or PROVIDER_DEFAULTS["zhipu"]
    api_key = os.getenv(spec["key"], "").strip()
    if not api_key:
        sys.exit(f"未找到 {spec['key']}：真实评测需要模型服务。配置 .env 或使用 --provider。")
    return LLMConfig(
        provider=provider,
        api_key=api_key,
        model_name=(os.getenv(spec["model_env"], "") or spec["model"]).strip(),
        base_url=(os.getenv(spec["base_env"], "") or spec["base_url"]).strip(),
    )


def run_real(questions: list[dict[str, Any]], df: pd.DataFrame, provider_arg: str | None) -> int:
    from analyzer.agent import PandasQueryAgent
    from analyzer.llm import LLMService
    from analyzer.profile import build_dataframe_profile

    config = _resolve_config(provider_arg)
    profile = build_dataframe_profile(df, desensitize=False)
    agent = PandasQueryAgent(llm_service=LLMService(config), max_retries=2)

    records: list[dict[str, Any]] = []
    for index, item in enumerate(questions, start=1):
        print(f"[{index}/{len(questions)}] {item['id']} {item['question']}")
        started = time.perf_counter()
        error = ""
        result_frame: pd.DataFrame | None = None
        attempts = 0
        try:
            query_result = agent.ask(
                question=item["question"], df=df, dataframe_profile=profile, desensitize=False
            )
            result_frame = query_result.result_frame
            attempts = query_result.attempts
        except Exception as exc:
            error = str(exc).splitlines()[0][:200]

        latency = time.perf_counter() - started
        passed, reason = (False, error or "无结果") if result_frame is None else grade_question(item, result_frame, df)
        kind = "ok" if passed else (_classify_error(error) if error else "wrong_answer")

        status = "✓" if passed else "✗"
        print(f"    {status} attempts={attempts or '-'} {latency:.1f}s {reason or ''}")

        records.append(
            {
                "id": item["id"],
                "category": item["category"],
                "question": item["question"],
                "ok": passed,
                "attempts": attempts,
                "latency_s": round(latency, 2),
                "kind": kind,
                "error": error or reason,
            }
        )

    report = _summarize(records, config)
    _write_reports(report, records, config)
    return 0 if report["summary"]["final_ok"] == len(questions) else 1


def _summarize(records: list[dict[str, Any]], config) -> dict[str, Any]:
    ok_records = [r for r in records if r["ok"]]
    latencies = sorted(r["latency_s"] for r in records)

    def _pct(data: list[float], q: float) -> float:
        if not data:
            return 0.0
        position = min(len(data) - 1, max(0, math.ceil(q * len(data)) - 1))
        return round(data[position], 2)

    by_category = {}
    for category in CATEGORIES:
        subset = [r for r in records if r["category"] == category]
        by_category[category] = {
            "total": len(subset),
            "passed": sum(1 for r in subset if r["ok"]),
        }

    convergence = Counter(str(r["attempts"]) for r in ok_records)
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "provider": config.provider,
        "model": config.model_name,
        "n_questions": len(records),
        "first_pass": sum(1 for r in ok_records if r["attempts"] == 1),
        "final_ok": len(ok_records),
        "latency_p50_s": _pct(latencies, 0.50),
        "latency_p95_s": _pct(latencies, 0.95),
        "latency_mean_s": round(statistics.fmean(latencies), 2) if latencies else 0.0,
        "timeouts": sum(1 for r in records if r["kind"] == "timeout"),
        "memory_kills": sum(1 for r in records if r["kind"] == "memory"),
        "sandbox_rejects": sum(1 for r in records if r["kind"] == "sandbox_reject"),
        "convergence": {attempt: convergence.get(attempt, 0) for attempt in ("1", "2", "3")},
        "by_category": by_category,
    }


def _write_reports(summary: dict[str, Any], records: list[dict[str, Any]], config) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    (RESULTS_DIR / "eval_results.json").write_text(
        json.dumps({"summary": summary, "questions": records}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    total = summary["n_questions"]
    lines = [
        "# 引擎评测报告",
        "",
        f"- 时间：{summary['generated_at']}",
        f"- 模型：{summary['provider']} / {summary['model']}",
        f"- 数据：合成销售明细 {total} 题六类（见 questions.jsonl）",
        "",
        "| 指标 | 数值 |",
        "|---|---|",
        f"| 一轮成功率 | {summary['first_pass']}/{total}（{summary['first_pass'] / total:.1%}） |",
        f"| 最终成功率（含重试） | {summary['final_ok']}/{total}（{summary['final_ok'] / total:.1%}） |",
        f"| 重试收敛 | {summary['convergence']} |",
        f"| 延迟 P50 / P95 / 均值 | {summary['latency_p50_s']}s / {summary['latency_p95_s']}s / {summary['latency_mean_s']}s |",
        f"| 超时 / 内存击杀 / 安全拦截 | {summary['timeouts']} / {summary['memory_kills']} / {summary['sandbox_rejects']} |",
        "",
        "## 按类别",
        "",
        "| 类别 | 通过 |",
        "|---|---|",
    ]
    for category, stat in summary["by_category"].items():
        lines.append(f"| {category} | {stat['passed']}/{stat['total']} |")

    lines += ["", "## 逐题明细", "", "| 题目 | 类别 | 结果 | 轮次 | 延迟 | 说明 |", "|---|---|---|---|---|---|"]
    for record in records:
        status = "✓" if record["ok"] else "✗"
        note = (record["error"] or "")[:60].replace("|", "\\|")
        lines.append(
            f"| {record['id']} | {record['category']} | {status} | {record['attempts'] or '-'} | "
            f"{record['latency_s']}s | {note} |"
        )

    (RESULTS_DIR / "eval_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n报告已写入 {RESULTS_DIR / 'eval_report.md'}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m analyzer.evals.run_eval",
        description="引擎评测：18 题六类，产出成功率/收敛/延迟指标。",
    )
    parser.add_argument("--dry-run", action="store_true", help="不调用模型：校验题目与黄金答案（CI 模式）")
    parser.add_argument("--provider", default=None, help="模型服务（默认取 .env 的 LLM_PROVIDER）")
    args = parser.parse_args(argv)

    questions = load_questions()
    df = build_eval_frame()

    if args.dry_run:
        return run_dry_run(questions, df)
    return run_real(questions, df, args.provider)


if __name__ == "__main__":
    sys.exit(main())
