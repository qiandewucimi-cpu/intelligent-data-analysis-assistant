# 智能数据分析助手 · 本地 LLM 代码执行沙箱引擎

**问题**：让 LLM 写 pandas 代码分析本地 Excel，有三个绕不开的约束——企业数据不能出域、
生成的代码不能在主应用里裸跑、输出质量不能靠"我试过几个都没问题"来担保。

**本项目**：一个零 UI 依赖的 Python 引擎（`analyzer/`），实现「自然语言 → 生成 pandas
代码 → AST 白名单校验 → 子进程沙箱执行（超时/内存上限）→ 失败自动纠错 → 结果归一化」
完整链路，配套 18 题六类评测集量化可靠性；Streamlit 网页与 CLI 是它的两个可替换入口。

```
analyzer/  引擎（核心资产）
  executor.py       AST 校验 + 子进程沙箱（超时 / 内存看门狗 / 输出只回传 JSON）
  sandbox_worker.py 沙箱子进程入口（纵深防御：父进程验过，子进程再验一遍）
  agent.py          生成 → 执行 → 报错自动重试 循环
  llm.py            四家 provider 统一 OpenAI 兼容端点（无 LangChain）
  profile.py        prompt 数据概况 / 全表真实统计（脱敏开关）
  evals/            18 题评测集 + 判分与指标产出
ui/        演示壳
  data_handler.py   文件加载 + 交互式清洗管线
  tabs/             上传 / 清洗 / 问答 / 图表 / AI 报告 五个页面
  exports.py        Excel/CSV 导出（含公式注入转义）
app.py      59 行薄入口
```

## 快速开始

```bash
# 网页入口
python -m streamlit run app.py

# CLI 入口（同一引擎，不开浏览器）
python -m analyzer sales.csv -q "按地区统计销售额总和，从高到低排序" --show-code

# 评测
python -m analyzer.evals.run_eval --dry-run        # CI 模式：校验题目与黄金答案，零 API 消耗
python -m analyzer.evals.run_eval                  # 真实评测，产出 results/eval_report.md
```

复制 `.env.example` 为 `.env` 填入模型密钥（支持智谱 GLM / DeepSeek / 通义千问 /
任意 OpenAI 兼容网关）。全新 Windows 机器首次使用时双击 `一键部署.bat` 安装环境；
环境就绪后日常使用双击 `启动应用.bat`，不会重复安装或更新依赖。

## 沙箱设计

生成代码视为不可信输入，两层防御：

- **静态**：AST 白名单——禁 import/while/def/class/try、禁 os/sys/socket 等标识符、
  禁 dunder 属性访问，pandas/NumPy 只开放白名单方法，所有文件读写接口不可达。
  父进程先验（快速失败），子进程再验（纵深防御）。
- **动态**：一次性子进程执行，硬超时（默认 20s）+ psutil 内存看门狗（默认 1024MB），
  按进程树监控与击杀（Windows 下 venv 的 python.exe 是启动器壳，真解释器是它的子进程——
  只盯直接子进程会漏掉失控的真进程）。

**数据过界不对称**：父→子 pickle（父产生的可信载荷）；子→父只回传 JSON——
执行过不可信代码的进程产物永远不被反序列化。

超时 / 内存上限可通过 `SANDBOX_TIMEOUT_SECONDS`、`SANDBOX_MEMORY_MB` 调整。
威胁模型的完整陈述与残余风险（如 format-string 属性遍历对 AST 的盲区）见
[docs/DESIGN_DECISIONS.md](docs/DESIGN_DECISIONS.md)——本项目不承诺抵御一切解释器逃逸，
隔离边界是"进程可杀 + 输出不反序列化"。

## 评测

数据：种子 42 确定性生成的 5,000 行合成销售明细（故意含 40 行完全重复、约 2% 缺失、
文本日期）。题目：18 题 × 6 类（单值聚合 / 分组聚合 / 筛选计算 / 时间趋势 /
**口径陷阱**（比率列 sum 陷阱）/ 数据质量），每题带运行时执行的黄金答案。
判分验数值正确性，不苛求列名与行序。

### 评测结果（zhipu / glm-4-flash，2026-09-13）

| 指标 | 数值 |
|---|---|
| 一轮成功率 | 15/18（83.3%） |
| 最终成功率（含自动纠错） | 15/18（83.3%） |
| 延迟 P50 / P95 | 16.4s / 27.1s |
| 超时 / 内存击杀 / 安全拦截 | 0 / 0 / 0 |

两个值得注意的发现：

- **口径陷阱 3/3 全过**——prompt 里"比率用 mean 不能 sum"的业务口径约束全部生效，
  这类错误是 BI 场景里最贵的一类。
- 三道未通过都是**理解问题而非执行失败**：两道复合双问句（"是哪个城市？销量是多少？"）
  模型只答了一半；一道"单日销售额最高"被算成了单笔口径。沙箱零超时、零拦截，
  说明执行层稳定；下一轮迭代该攻的是问句分解，不是代码执行。

## 数据安全

- **脱敏模式**（默认开启）：问答与报告只外发列名、类型和聚合数字，不发明细行与真实取值；
  全表统计中的分类取值替换为中性标签。
- **导出侧防公式注入**：导出 CSV/Excel 时对 `=`、`+`、`-`、`@`、Tab 开头的文本加转义前缀
  （OWASP CSV Injection），防止数据被打开时变成可执行公式。
- 密钥仅存本机 `.env`（已 gitignore），侧边栏"记住密钥"可随时撤销。

## 依赖取舍

13 个直接依赖（从 15 降下来）：移除 LangChain 全家桶与 dashscope SDK——它们只有一条
分支在用，而所有 provider 本就兼容 OpenAI 端点；保留 kaleido（PNG 导出唯一依赖）。
部署脚本的依赖哨兵记录 requirements.txt 哈希，清单变更自动重装。

## 测试

```bash
python -m unittest discover -s tests -v
```

覆盖：沙箱校验拒绝路径、子进程结果与直接 pandas 对拍、超时/内存击杀实测、
导出公式注入转义；CI 另跑评测集 dry-run（黄金答案自检）。
