# InspectPilot

InspectPilot 是一个面向钢铁方坯表面视觉检测结果的工业视觉质检异常诊断 Agent。v0.3 在确定性统计工具和 LLM Tool Calling 工作流之上，加入 FAISS/BGE 向量 RAG；v0.4 开始从“查缺陷结果/知识问答”升级为“诊断异常原因”：LLM 只负责理解问题、选择受控 tools、基于工具结果和知识库证据生成中文结论，不直接查询数据库或生成 SQL。

## 项目定位

- 项目名称：InspectPilot - 工业视觉质检异常诊断 Agent
- 项目类型：工业视觉缺陷分析与异常诊断 Agent，不是普通聊天机器人
- 简历关键词：FastAPI、LangGraph、OpenAI Tool Calling、RAG、SQLite/MySQL、FAISS/BGE、工业视觉检测、异常诊断、质量追溯、相机健康分析、误检风险评估

## v0.3 能力

- LLM Tool Calling 工作流：`prepare -> plan_tool_calls -> execute_tools -> generate_answer`
- 受控工具调用：只允许调用 `backend/tools/defect_tools.py` 中封装好的确定性统计工具
- RAG 知识检索：`retrieve_defect_knowledge` 从 `backend/rag/knowledge_base.md` 检索缺陷类别、等级规则、判定标准、常见原因和报告模板
- Hybrid Retrieval：默认使用 FAISS/BGE 语义召回 + BM25 词面召回，并通过 RRF 融合候选；向量依赖缺失时自动降级到 BM25/关键词检索，保证本地演示不断流
- OpenAI 兼容接口：支持 OpenAI、通义千问、DeepSeek、本地兼容服务等
- 统一响应字段：`answer`、`tool_calls`、`evidence`、`kb_evidence`、`rag_trace`、`time_window`、`filters`、`warnings`
- 最小评测集：覆盖工具选择、关键统计结果、无数据不编造规则

## v0.3.1 RAG Eval + Debug Trace

- API 新增 `rag_trace`：记录每次知识检索的 `trace_id`、原始 query、retriever、embedding model、top_k、候选 doc_id、score、category、tags、source、answer_mode 和 warnings
- 前端新增 RAG Trace 展示区：演示时可以直接看到本次回答引用了哪些知识片段
- `eval_runner.py` 支持 RAG 专用检查：`expected_need_rag`、`must_not_tools`、`expected_top_doc_ids`、`expected_any_doc_ids`、`expected_relevant_doc_ids`
- eval 输出 RAG 指标：`recall@K`、`mrr`、`irrelevant_rate`，用于后续 query rewrite、hybrid retrieval、rerank 的量化对比

## v0.3.2 Knowledge Metadata + Business Rerank + Evidence Budget

- 知识库 chunk 增加业务元数据：`defect_types`、`risk_level`、`applicable_intents`、`evidence_type`、`related_doc_ids`、`status`、`version`、`updated_at`
- RAG 检索从“直接返回向量 TopK”升级为“两阶段排序”：先用 FAISS/BGE 扩大候选召回，再根据缺陷类型、问题意图和知识类别做业务重排
- `kb_evidence` 和 `rag_trace` 新增 `dense_score`、`metadata_score`、`rerank_score`、`rerank_reason`、`included_in_answer_context`、`evidence_budget`
- Evidence Budget 通过 `RAG_EVIDENCE_BUDGET_CHARS` 和 `RAG_EVIDENCE_BUDGET_MAX_ITEMS` 控制进入答案生成上下文的知识片段，前端仍展示完整 TopK 证据，避免 LLM 被弱相关证据淹没
- 前端参考知识区展示重排依据，便于演示“Agent 基于可追溯知识片段回答，而不是凭空解释”

## v0.3.3 Query Rewrite + Multi-Query + Evidence Judge

- RAG 从单次检索升级为轻量 Agentic RAG：`原问题 -> query rewrite -> 多子查询检索 -> 合并去重 -> business rerank -> evidence budget -> evidence judge -> 最多一轮补查`
- 规则型 Query Rewrite 支持口语别名和业务意图归一：例如“开裂”归一为“裂纹”，“危险”映射到 `severity/critical`，“看错”映射到 `false_positive`
- Multi-Query Retrieval 会围绕缺陷说明、等级规则、空间分布、原因排查、复核闭环和回答规范生成子查询，解决复杂问题只查到单类证据的问题
- Evidence Judge 基于 `evidence_type` 判断证据是否覆盖当前问题所需类型，输出 `required_evidence_types`、`covered_evidence_types`、`missing_aspects`、`coverage_rate`
- `rag_trace` 新增 `rewritten_query`、`sub_queries`、`retrieval_rounds`、`evidence_sufficient`、`second_round_queries` 等字段，便于演示规划、检索、观察和补查过程
- `eval_runner.py` 新增 Agentic RAG 指标：`rewrite_success_rate`、`coverage_rate`、`second_round_success_rate`

## v0.3.4 Hybrid Retrieval

- RAG 召回层从“FAISS/BGE 优先，失败后关键词兜底”升级为默认 Hybrid Retrieval：FAISS/BGE 负责语义相似度，BM25 负责精确词面匹配和口语关键词兜底
- 新增轻量 BM25 实现，不引入额外依赖；中文场景通过领域词、英文/数字 token、中文 bi-gram/tri-gram 共同建模
- FAISS 与 BM25 候选通过 Reciprocal Rank Fusion 融合，输出 `dense_score`、`bm25_score`、`fusion_score`、`fusion_strategy` 和 `fusion_components`
- 现有 business rerank、Evidence Budget、Evidence Judge 保持在融合召回之后继续生效，避免单纯词面命中挤掉业务必需证据
- `RAG_RETRIEVER_MODE` 支持 `hybrid`、`faiss`、`bm25` 三种模式，便于对比召回策略和离线演示
- 前端参考知识和 RAG Trace 展示 BM25 / fusion 字段；`eval_runner.py` 输出 retriever 使用分布、BM25 使用率和 hybrid 使用率

## v0.4.0 Diagnostic Agent

- 项目定位从“缺陷统计 + RAG 知识问答”升级为“工业视觉质检异常诊断 Agent”
- 新增诊断 mock 数据表：`defect_events`、`camera_status`、`image_quality_metrics`
- 构造三类诊断场景：
  - `camera2_imaging_abnormal`：10:00 后裂纹突增，集中在 CAM02/right/head-edge，同时 FPS 下降、亮度下降、黑帧/空帧升高、低置信度框增多；期望诊断为相机成像异常/误检风险更高
  - `multi_camera_quality_wave`：10:00 后多相机、多位置、多方坯同步裂纹增多，图像质量和相机状态基本正常；期望诊断为真实质量波动风险更高
  - `sparse_evidence`：只有单条裂纹记录且缺少相机/图像质量证据；期望诊断为证据不足，不能硬判根因
- 新增确定性诊断工具：`detect_defect_spike`、`analyze_defect_camera_concentration`、`analyze_camera_health`、`analyze_image_quality`、`estimate_false_positive_risk`
- 诊断类问题自动输出固定结构：`【结论】`、`【关键证据】`、`【可能原因排序】`、`【建议动作】`、`【仍需补充的数据】`
- 诊断回答约束：不允许只根据缺陷数量、单条记录或空间集中直接判定质量事故/工艺事故；涉及判废、停线、复检必须建议人工确认
- `eval_runner.py` 新增诊断指标：`diagnosis_intent_accuracy`、`required_tool_coverage`、`root_cause_accuracy`、`evidence_keyword_coverage`、`unsafe_claim_rate`

## v0.4.1 Diagnostic Planner Guardrails

- 诊断类问题不再完全信任 LLM 自由选择工具；只要意图识别为 `diagnosis`，planner 输出会被规范为固定诊断工具链：`detect_defect_spike`、`analyze_defect_camera_concentration`、`analyze_camera_health`、`analyze_image_quality`、`estimate_false_positive_risk`
- 诊断工具参数会统一使用项目内置诊断窗口，避免 LLM 将 “10 点后” 错缩成 `10:00-10:02` 这类过窄窗口，导致样本数不足和误判
- 诊断类 RAG 检索至少拉取 5 条知识片段，确保回答能覆盖缺陷说明、复核闭环、表面判定标准和原因排查清单
- 诊断答案以 `estimate_false_positive_risk` 的结构化结果为准，LLM 不再覆盖工具给出的根因、风险等级和建议动作

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
RAG_RETRIEVER_MODE=hybrid
RAG_TOP_K=3
RAG_EVIDENCE_BUDGET_CHARS=1800
RAG_EVIDENCE_BUDGET_MAX_ITEMS=3
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

如果本机暂未安装 `faiss-cpu`、`sentence-transformers` 或模型尚未下载，系统会在运行时优先使用 BM25 兜底检索，并在 `kb_evidence.retriever` 中标记为 `bm25_fallback`；极端情况下再降级为 `keyword_fallback`。

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
- 今天 10 点后裂纹突然增多，请判断是真实质量异常，还是检测系统异常。
- 今天 10 点后多相机同步增加裂纹，图像质量正常，请判断是不是检测系统误检。
- 只有一条裂纹记录，而且没有相机状态，能判断根因吗？

## 启动前端

```powershell
cd D:\求职\agent系统学习codex\InspectPilot\frontend
npm install
npm run dev
```
