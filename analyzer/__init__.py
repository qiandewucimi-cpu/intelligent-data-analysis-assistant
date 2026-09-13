"""analyzer — 本地 LLM 代码执行沙箱引擎（零 UI 依赖）。

分层边界：引擎回答"给定 DataFrame 和自然语言问题，安全地产出可信结果"；
文件加载、清洗、图表、报告导出等交互能力全部位于 ``ui/`` 演示壳。

刻意不在 ``__init__`` 里做任何导入：``sandbox_worker`` 会以
``python -m analyzer.sandbox_worker`` 方式启动，包级 __init__ 一旦引入
agent/llm 就会把 OpenAI SDK 拖进沙箱子进程。请直接从子模块导入。
"""
