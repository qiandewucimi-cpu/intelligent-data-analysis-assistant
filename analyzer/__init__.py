"""analyzer — 本地 LLM 代码执行沙箱引擎（零 UI 依赖）。

分层边界：引擎回答"给定 DataFrame 和自然语言问题，安全地产出可信结果"；
文件加载、清洗、图表、报告导出等交互能力全部位于 ``ui/`` 演示壳。

Public API - 支持直接导入使用：
    from analyzer import PandasQueryAgent, run_in_sandbox
    from analyzer import LLMService

注意：``sandbox_worker`` 会以 ``python -m analyzer.sandbox_worker`` 方式启动，
避免在子进程加载不必要的依赖。
"""

__version__ = "1.0.0"

# 导出核心API - 这些不会在沙箱子进程中使用
try:
    from .agent import PandasQueryAgent
    from .executor import run_in_sandbox
    from .llm import LLMService
    
    # 公开导出
    __all__ = ["PandasQueryAgent", "run_in_sandbox", "LLMService"]
except ImportError:
    # 如果导入失败（比如在沙箱子进程中），不导出任何内容
    __all__ = []
