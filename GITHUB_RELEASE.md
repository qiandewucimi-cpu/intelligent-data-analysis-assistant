# 🚀 智能数据分析助手 v1.0.0

> 本地LLM代码执行沙箱引擎，智能数据分析助手

![Python](https://img.shields.io/badge/Python-3.9%2B-blue)
![License](https://img.shields.io/badge/License-MIT-green)
![Version](https://img.shields.io/badge/Version-1.0.0-red)

## 📋 简介

智能数据分析助手是一个本地运行的LLM代码执行沙箱引擎，提供数据分析、可视化报告生成等功能。采用真实的沙箱隔离机制，确保代码执行的安全性。

## ✨ 主要特性

### 🔒 安全沙箱
- **子进程执行**：代码在独立子进程中运行，与主进程完全隔离
- **AST校验**：执行前进行抽象语法树分析，阻止危险操作
- **超时保护**：20秒自动终止执行，防止单个查询耗时过长
- **内存限制**：1GB内存上限，防止内存耗尽攻击

### 🤖 多LLM支持
- **智谱AI**：glm-4-flash、glm-4v
- **DeepSeek**：deepseek-chat
- **阿里云**：dashscope通义千问
- **自定义**：OpenAI兼容端点

### 📊 数据分析能力
- **多格式支持**：CSV、XLSX、XLS
- **自动数据清洗**：缺失值处理、重复值检测
- **智能分析**：聚合、筛选、分组、趋势分析
- **可视化图表**：柱状图、折线图、饼图、散点图

### 💻 双入口模式
- **CLI模式**：命令行直接分析，适合自动化脚本
- **Web界面**：Streamlit交互式界面，适合探索性分析

## 📦 安装

### 从源码安装
```bash
pip install git+https://github.com/qiandewucimi-cpu/intelligent-data-analysis-assistant.git
```

### 本地安装
```bash
# 克隆仓库
git clone https://github.com/qiandewucimi-cpu/intelligent-data-analysis-assistant.git
cd intelligent-data-analysis-assistant

# 安装依赖
pip install -e .
```

## 🚀 快速开始

### CLI使用
```bash
# 基本分析
python -m analyzer data.csv -q "各地区销售额Top5"

# 指定模型
python -m analyzer data.csv -q "分析销售趋势" --provider zhipu

# 显示生成的代码
python -m analyzer data.csv -q "各产品销量对比" --show-code

# 跳过数据清洗
python -m analyzer data.csv -q "直接分析原始数据" --no-clean
```

### Web界面
```bash
# 启动Streamlit界面
python -m streamlit run app.py

# 或使用一键部署脚本
双击运行 一键部署.bat
```

访问 http://localhost:8501 开始使用。

## 📊 性能指标

- **成功率**：83.3% (15/18题)
- **响应速度**：P50延迟 16.4秒
- **安全性**：零安全事件记录
- **沙箱稳定性**：100%隔离成功率

## 🏗️ 架构设计

```
智能数据分析助手
├── analyzer/           # 核心引擎（无UI依赖）
│   ├── agent.py       # 智能分析代理
│   ├── executor.py    # 沙箱执行器
│   ├── llm.py         # LLM客户端
│   └── evals/         # 评测体系
├── ui/                # Streamlit界面
│   ├── app.py         # 主入口
│   └── tabs/          # 功能页面
└── examples/          # 示例数据
```

## 🔧 配置

创建 `.env` 文件配置API密钥：
```env
# LLM配置
LLM_PROVIDER=zhipu          # zhipu/deepseek/dashscope/openai_compatible
ZHIPU_API_KEY=your_zhipu_key
DEEPSEEK_API_KEY=your_deepseek_key
DASHSCOPE_API_KEY=your_dashscope_key
OPENAI_API_BASE=https://api.openai.com/v1
OPENAI_API_KEY=your_openai_key

# 沙箱配置
SANDBOX_TIMEOUT_SECONDS=20
SANDBOX_MEMORY_MB=1024
```

## 🧪 测试

### 运行评测
```bash
# 干跑测试（不调用API，仅验证逻辑）
python -m analyzer.evals.run_eval --dry-run

# 真实评测（需要配置API密钥）
python -m analyzer.evals.run_eval
```

### 功能测试
```bash
# CLI功能测试
python -m analyzer analyzer/evals/data/sales_sample.csv -q "各地区销售额Top5"

# Web界面测试
python -m streamlit run app.py --server.headless true
```

## 📋 评测集

包含18道测试题，覆盖6类分析场景：
1. **单值聚合**：总计、平均值、最大值等
2. **分组TopN**：各组内排序取前N
3. **筛选计算**：条件筛选后计算
4. **时间趋势**：时间序列分析
5. **口径陷阱**：易错的数据分析逻辑
6. **数据质量**：数据完整性分析

## 📚 文档

- [详细使用说明](README.md)
- [架构设计决策](docs/DESIGN_DECISIONS.md)
- [Release Notes](RELEASE_NOTES.md)
- [一键部署脚本](deploy.ps1)

## 🔒 安全说明

本工具采用多层次安全防护：
1. **AST校验**：阻止危险代码执行
2. **子进程隔离**：主进程与执行环境完全隔离
3. **资源限制**：CPU、内存、执行时间限制
4. **输出过滤**：执行结果经过严格验证

**注意**：虽然具备多层次防护，但仍不建议在处理敏感数据时使用。请在受控环境中使用本工具。

## 🤝 贡献

欢迎提交Issue和Pull Request！

1. Fork本仓库
2. 创建特性分支：`git checkout -b feature/new-feature`
3. 提交更改：`git commit -am 'Add new feature'`
4. 推送到分支：`git push origin feature/new-feature`
5. 提交Pull Request

## 📄 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情。

## 📞 支持

- 📧 Email：qiandewucimi@gmail.com
- 🐛 问题反馈：[GitHub Issues](https://github.com/qiandewucimi-cpu/intelligent-data-analysis-assistant/issues)
- 📖 文档：[GitHub Wiki](https://github.com/qiandewucimi-cpu/intelligent-data-analysis-assistant/wiki)

---

**Made with ❤️ by 陈源浩**