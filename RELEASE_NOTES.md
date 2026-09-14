# 智能数据分析助手 v1.0.0 - Release Notes

## 🎉 正式发布 - 本地 LLM 代码执行沙箱引擎

### 核心特性
- **真实沙箱隔离** - 子进程执行，AST代码校验 + 超时/内存双保护
- **科学计数法修复** - 大数值正确显示（78,117,574.89 而非 2.61431e+07）
- **多入口支持** - Streamlit界面 + 命令行CLI + Python包导入
- **统一LLM客户端** - 去LangChain，支持4家OpenAI兼容提供商
- **完整评测体系** - 18题六类评测，83.3%成功率（15/18）

### 技术架构
```
analyzer/          # 🚀 引擎核心（零UI依赖）
├── __init__.py     # 公共API：PandasQueryAgent, run_in_sandbox, LLMService
├── agent.py        # 生成→执行→自动纠错循环
├── executor.py     # 沙箱执行器（AST校验+超时内存保护）
├── llm.py          # 统一LLM客户端（4家provider）
├── __main__.py     # CLI入口
└── evals/          # 评测系统
    └── run_eval.py # 18题评测 + 指标报告

ui/                # 🎨 演示壳（Streamlit）
├── app.py          # 收缩至~100行入口
└── tabs/           # 功能页面：上传/清洗/问答/图表/报告
```

### 性能指标（真实评测）
- **一轮成功率**: 83.3% (15/18题)
- **重试收敛**: 15题1次通过，0题需要重试
- **延迟P50/P95**: 16.4s / 27.1s
- **安全拦截**: 0/0 (超时/内存/安全拦截)

### 按类别表现
| 类别 | 通过率 | 说明 |
|------|--------|------|
| 单值聚合 | 100% (3/3) | 基础统计计算 |
| 分组聚合 | 66.7% (2/3) | TopN稍有挑战 |
| 筛选计算 | 66.7% (2/3) | 复杂条件理解 |
| 时间趋势 | 66.7% (2/3) | 时间序列分析 |
| 口径陷阱 | 100% (3/3) | 业务逻辑理解 |
| 数据质量 | 100% (3/3) | 数据探查能力 |

### 快速开始

#### 1. CLI模式（推荐）
```bash
# 基础查询
python -m analyzer data.csv -q "总销售额是多少"

# 指定模型和超时
python -m analyzer data.csv -q "各地区Top5" --provider zhipu --timeout 15
```

#### 2. Streamlit界面
```bash
streamlit run app.py
```

#### 3. Python包导入
```python
from analyzer import PandasQueryAgent, run_in_sandbox
import pandas as pd

# 直接查询
agent = PandasQueryAgent(df)
result = agent.query("总销售额是多少")

# 沙箱执行
sandbox_result = run_in_sandbox(code, df, timeout_s=20, memory_mb=1024)
```

### 支持的LLM提供商
- **智谱AI** (zhipu/glm-4-flash) - 默认
- **DeepSeek** (deepseek-chat)
- **自定义OpenAI兼容端点**
- **阿里云dashscope** (通过OpenAI兼容接口)

### 安全特性
- **AST代码校验** - 阻止import/socket/文件IO等危险操作
- **子进程隔离** - 代码在独立进程中执行，崩溃不影响主程序
- **资源限制** - 超时控制(默认20s) + 内存看门狗(默认1024MB)
- **协议安全** - JSON+CSV通信，拒绝pickle注入

### 评测数据
- **合成销售数据** - 5000行，含缺失/重复/折扣率等真实业务场景
- **18题六类** - 覆盖常见分析需求
- **黄金答案** - 每题有标准答案用于自动判分

### 主要修复
- ✅ **科学计数法显示** - 大数值正确格式化显示
- ✅ **沙箱安全性** - 真正的子进程隔离，不是简单的exec限制
- ✅ **依赖瘦身** - 去除LangChain，依赖从15个减少到13个
- ✅ **模块化** - 引擎/UI完全分离，支持独立使用
- ✅ **错误处理** - 完善的超时/内存/安全错误分类

### 开发者友好
- **完整文档** - docs/DESIGN_DECISIONS.md 详细设计决策
- **单元测试** - 覆盖核心功能
- **类型注解** - 全程Python 3.8+类型提示
- **MIT协议** - 开源友好

### 未来路线图
- [ ] 更多数据源支持（Excel、数据库、API）
- [ ] 图表生成优化（更多可视化类型）
- [ ] 多语言提示词支持
- [ ] 企业级部署方案
- [ ] 更多LLM提供商集成

---

**升级说明**: 如果从旧版本升级，请重新安装依赖并重启Streamlit。新版本完全向后兼容。

**技术支持**: 请提交GitHub Issues或查看docs/DESIGN_DECISIONS.md