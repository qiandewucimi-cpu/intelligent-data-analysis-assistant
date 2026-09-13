"""CLI 入口：不开浏览器，命令行直接问答。

    python -m analyzer sales.csv -q "各地区销售额Top5"

读取 .env 里的 provider 配置（与 Streamlit 壳共用同一套引擎），执行
「生成代码 -> 沙箱执行 -> 自动纠错 -> 业务解读」全链路后打印结果表。
"""

from __future__ import annotations

import argparse
import os
import sys

import pandas as pd
from dotenv import load_dotenv
from tabulate import tabulate

from analyzer.agent import PandasQueryAgent
from analyzer.columns import drop_helper_columns
from analyzer.llm import LLMConfig, LLMService, ProviderType
from analyzer.profile import build_dataframe_profile

# 与 Streamlit 侧边栏一致的默认模型与接口地址。
_PROVIDER_DEFAULTS: dict[str, dict[str, str]] = {
    "zhipu": {
        "key": "ZHIPU_API_KEY",
        "model": "glm-4-flash",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "model_env": "ZHIPU_MODEL",
        "base_env": "ZHIPU_BASE_URL",
    },
    "deepseek": {
        "key": "DEEPSEEK_API_KEY",
        "model": "deepseek-chat",
        "base_url": "https://api.deepseek.com",
        "model_env": "DEEPSEEK_MODEL",
        "base_env": "DEEPSEEK_BASE_URL",
    },
    "dashscope": {
        "key": "DASHSCOPE_API_KEY",
        "model": "qwen-plus",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model_env": "QWEN_MODEL",
        "base_env": "DASHSCOPE_BASE_URL",
    },
    "openai_compatible": {
        "key": "OPENAI_API_KEY",
        "model": "gpt-4o-mini",
        "base_url": "",
        "model_env": "OPENAI_MODEL",
        "base_env": "OPENAI_BASE_URL",
    },
}


def _load_config(args: argparse.Namespace) -> LLMConfig:
    """Resolves provider settings from .env / environment, mirroring the sidebar defaults."""

    spec = _PROVIDER_DEFAULTS[args.provider]
    api_key = os.getenv(spec["key"], "").strip()
    model_name = (os.getenv(spec["model_env"], "") or spec["model"]).strip()
    base_url = (os.getenv(spec["base_env"], "") or spec["base_url"]).strip()

    if not api_key:
        sys.exit(
            f"未找到 {spec['key']}。请在项目根目录 .env 里配置（参考 .env.example），"
            f"或改用 --provider 指定其他服务。"
        )

    return LLMConfig(
        provider=args.provider,
        api_key=api_key,
        model_name=model_name,
        base_url=base_url,
    )


def _read_input(path: str) -> pd.DataFrame:
    """Loads CSV/Excel via the same reader the UI shell uses."""

    from ui.data_handler import load_dataframe

    with open(path, "rb") as handle:
        return load_dataframe(handle.read(), os.path.basename(path))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m analyzer",
        description="智能数据分析引擎 CLI：对 CSV/Excel 用自然语言提问，沙箱执行生成的 pandas 代码。",
    )
    parser.add_argument("data", help="CSV / XLSX / XLS 数据文件路径")
    parser.add_argument("-q", "--question", required=True, help="自然语言分析问题")
    parser.add_argument(
        "--provider",
        default=os.getenv("LLM_PROVIDER", "zhipu").strip().lower(),
        choices=list(_PROVIDER_DEFAULTS),
        help="模型服务（默认取 .env 的 LLM_PROVIDER，否则 zhipu）",
    )
    parser.add_argument("--no-clean", action="store_true", help="跳过自动清洗，直接用原始数据提问")
    parser.add_argument("--show-code", action="store_true", help="打印生成的 pandas 代码")
    parser.add_argument("--timeout", type=float, default=None, help="沙箱超时秒数（默认 20）")
    args = parser.parse_args(argv)

    load_dotenv()
    config = _load_config(args)

    try:
        df = _read_input(args.data)
    except Exception as exc:
        sys.exit(f"读取数据失败：{exc}")

    if not args.no_clean:
        from ui.data_handler import CleaningOptions, clean_dataframe

        df, _ = clean_dataframe(df, options=CleaningOptions())

    df = drop_helper_columns(df)
    profile = build_dataframe_profile(df)
    print(f"数据：{df.shape[0]} 行 × {df.shape[1]} 列 | 模型：{config.provider}/{config.model_name}\n")

    agent = PandasQueryAgent(llm_service=LLMService(config), max_retries=2, timeout_s=args.timeout)
    try:
        result = agent.ask(question=args.question, df=df, dataframe_profile=profile)
    except Exception as exc:
        sys.exit(f"查询失败：{exc}")

    print(tabulate(result.result_frame.head(30), headers="keys", tablefmt="github", showindex=False))
    if len(result.result_frame) > 30:
        print(f"...（共 {len(result.result_frame)} 行，仅显示前 30 行）")

    print(f"\n—— AI 解读{'（第 ' + str(result.attempts) + ' 轮成功）' if result.attempts > 1 else ''} ——")
    print(result.explanation)

    if args.show_code:
        print("\n—— 生成的 pandas 代码 ——")
        print(result.code)

    return 0


if __name__ == "__main__":
    sys.exit(main())
