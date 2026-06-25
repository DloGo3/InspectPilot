# InspectPilot

InspectPilot 是一个面向钢铁方坯表面视觉检测结果的工业缺陷分析 Agent。v0.3 在确定性统计工具和 LLM Tool Calling 工作流之上，加入 FAISS/BGE 向量 RAG：LLM 只负责理解问题、选择受控 tools、基于工具结果和知识库证据生成中文结论，不直接查询数据库或生成 SQL。

## 项目定位

- 项目名称：InspectPilot - 方坯表面缺陷分析 Agent
- 项目类型：工业视觉缺陷分析 Agent，不是普通聊天机器人
- 简历关键词：FastAPI、LangGraph、OpenAI Tool Calling、RAG、SQLite/MySQL、FAISS/BGE、工业视觉检测、质量分析、缺陷空间分布

## v0.3 能力

- LLM Tool Calling 工作流：`prepare -> plan_tool_calls -> execute_tools -> generate_answer`
- 受控工具调用：只允许调用 `backend/tools/defect_tools.py` 中封装好的确定性统计工具
- RAG 知识检索：`retrieve_defect_knowledge` 从 `backend/rag/knowledge_base.md` 检索缺陷类别、等级规则、判定标准、常见原因和报告模板
- FAISS/BGE 优先：安装 `faiss-cpu`、`sentence-transformers` 后使用 `BAAI/bge-small-zh-v1.5` 建索引；依赖缺失时自动降级到关键词检索，保证本地演示不断流
- OpenAI 兼容接口：支持 OpenAI、通义千问、DeepSeek、本地兼容服务等
- 统一响应字段：`answer`、`tool_calls`、`evidence`、`kb_evidence`、`rag_trace`、`time_window`、`filters`、`warnings`
- 最小评测集：覆盖工具选择、关键统计结果、无数据不编造规则

## v0.3.1 RAG Eval + Debug Trace

- API 新增 `rag_trace`：记录每次知识检索的 `trace_id`、原始 query、retriever、embedding model、top_k、候选 doc_id、score、category、tags、source、answer_mode 和 warnings
- 前端新增 RAG Trace 展示区：演示时可以直接看到本次回答引用了哪些知识片段
- `eval_runner.py` 支持 RAG 专用检查：`expected_need_rag`、`must_not_tools`、`expected_top_doc_ids`、`expected_any_doc_ids`、`expected_relevant_doc_ids`
- eval 输出 RAG 指标：`recall@K`、`mrr`、`irrelevant_rate`，用于后续 query rewrite、hybrid retrieval、rerank 的量化对比

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
EMBEDDING_MODEL_NAME=BAAI/bge-small-zh-v1.5
RAG_TOP_K=3
```

如果暂时不配置 `.env`，后端会使用离线 fallback planner，并在 `warnings` 中说明，方便本地演示不断流。

访问：

- API 文档：http://127.0.0.1:8000/docs
- 健康检查：http://127.0.0.1:8000/api/health
- RAG 状态：http://127.0.0.1:8000/api/rag/status

## 构建 RAG 索引

首次安装向量依赖和 BGE 模型后，可手动构建 FAISS 索引：

```powershell
cd D:\求职\agent系统学习codex\InspectPilot\backend
python rag\build_index.py --force
```

如果本机暂未安装 `faiss-cpu`、`sentence-transformers` 或模型尚未下载，系统会在运行时使用关键词兜底检索，并在 `kb_evidence.retriever` 中标记为 `keyword_fallback`。

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
- 裂纹为什么需要重点关注？
- 缺陷等级规则是什么？
- 生成一份缺陷统计与空间分布分析报告。

## 启动前端

```powershell
cd D:\求职\agent系统学习codex\InspectPilot\frontend
npm install
npm run dev
```
