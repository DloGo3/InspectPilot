# InspectPilot

InspectPilot 是一个面向钢铁方坯表面视觉检测结果的工业缺陷分析 Agent。v0.2 在第一阶段 MVP 的确定性统计工具之上，升级为 LLM Tool Calling 工作流：LLM 只负责理解问题、选择受控 tools、基于工具结果生成中文结论，不直接查询数据库或生成 SQL。

## 项目定位

- 项目名称：InspectPilot - 方坯表面缺陷分析 Agent
- 项目类型：工业视觉缺陷分析 Agent，不是普通聊天机器人
- 简历关键词：FastAPI、LangGraph、OpenAI Tool Calling、RAG、SQLite/MySQL、FAISS/Milvus、工业视觉检测、质量分析、缺陷空间分布

## v0.2 能力

- LLM Tool Calling 工作流：`prepare -> plan_tool_calls -> execute_tools -> generate_answer`
- 受控工具调用：只允许调用 `backend/tools/defect_tools.py` 中封装好的确定性统计工具
- OpenAI 兼容接口：支持 OpenAI、通义千问、DeepSeek、本地兼容服务等
- 统一响应字段：`answer`、`tool_calls`、`evidence`、`time_window`、`filters`、`warnings`
- 最小评测集：覆盖工具选择、关键统计结果、无数据不编造规则

## 启动后端

```powershell
cd D:\求职\agent系统学习codex\InspectPilot\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python data\init_db.py --reset
uvicorn main:app --reload
```

LLM 配置：

```powershell
cd D:\求职\agent系统学习codex\InspectPilot\backend
Copy-Item .env.example .env
```

编辑 `.env`：

```text
OPENAI_API_KEY=sk-your-key
OPENAI_BASE_URL=https://api.openai.com/v1
MODEL_NAME=gpt-4o-mini
```

如果暂时不配置 `.env`，后端会使用离线 fallback planner，并在 `warnings` 中说明，方便本地演示不断流。

访问：

- API 文档：http://127.0.0.1:8000/docs
- 健康检查：http://127.0.0.1:8000/api/health

## 运行评测

离线评测，不消耗 LLM API：

```powershell
cd D:\求职\agent系统学习codex\InspectPilot\backend
python evals\eval_runner.py --mode offline --reset-db
```

真实 LLM Tool Calling 评测：

```powershell
cd D:\求职\agent系统学习codex\InspectPilot\backend
python evals\eval_runner.py --mode llm --reset-db
```

`--mode llm` 默认要求本次评测真实使用过 LLM。如果 LLM 未配置、连接失败或工具规划/答案生成全部降级为 fallback，对应用例会失败。临时允许降级可加：

```powershell
python evals\eval_runner.py --mode llm --allow-fallback
```

评测输出会显示每个 case 的真实执行模式：

```text
[PASS] type_top_all planner=llm answer=llm tools=['group_defects_by_type']
```

## 测试问题

- 最近一小时检测出了哪些缺陷？
- 哪类缺陷最多？
- 哪个方坯表面缺陷最多？
- 方坯头部、中部、尾部哪个位置更容易出现缺陷？
- 哪个炉号、计划号、方坯 ID 的 NG 率最高？
- 裂纹主要集中在哪里？
- 生成一份缺陷统计与空间分布分析报告。

## 启动前端

```powershell
cd D:\求职\agent系统学习codex\InspectPilot\frontend
npm install
npm run dev
```
