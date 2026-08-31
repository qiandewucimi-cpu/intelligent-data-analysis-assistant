# 智能数据分析助手

一个面向 Excel / CSV 数据的本地 Streamlit 应用，提供数据清洗、自然语言问答、智能图表和 AI 分析报告。

## 功能

- 上传 CSV、XLS 或 XLSX，支持工作表和表头选择
- 重复项、缺失值、类型转换和异常值检测
- 用自然语言生成受限的 pandas 分析
- 生成图表、Markdown 报告和 Word 报告
- 支持智谱 GLM、DeepSeek、通义千问以及 OpenAI 兼容接口
- 默认开启数据脱敏模式

## Windows 一键启动

双击 `一键部署.bat`。脚本会检测 Python、创建虚拟环境、安装依赖并打开本地页面。自动下载的 Python 安装包会先验证 Python Software Foundation 的数字签名。

## 手动运行

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

## API Key 安全

1. 复制 `.env.example` 为 `.env`，然后只填写自己使用的模型服务。
2. 真实 `.env`、Streamlit secrets、私钥和本地虚拟环境均已被 Git 忽略。
3. 公用电脑上不要勾选“记住密钥”。
4. 处理客户或个人数据时，保持“脱敏模式”开启。即使开启脱敏，列名和聚合统计仍会发送给所选模型服务。

应用将 AI 生成的 Python 代码视为不可信输入：禁止文件、网络、进程和动态执行类型的调用，并通过 pandas / NumPy 允许列表防止读取本地 `.env`。

## 测试

```powershell
python -m unittest discover -s tests -v
```

## 项目结构

```text
app.py                  Streamlit 主应用
utils/data_handler.py   数据读取、清洗与统计
utils/pandas_agent.py   受限的 AI pandas 执行器
utils/charting.py       图表生成
utils/llm_service.py    模型接口
utils/report_export.py  Word 报告导出
tests/                  安全回归测试
```
