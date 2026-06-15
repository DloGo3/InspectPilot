# InspectPilot 第一阶段 MVP 设计

## 一、项目名称和定位

项目名称：InspectPilot - 方坯表面缺陷分析 Agent

一句话定位：面向钢铁连铸方坯表面视觉检测结果的工业缺陷分析 Agent，自动完成缺陷统计、空间分布判断、炉号/计划号质量异常识别和报告生成。

它不是普通聊天机器人，而是带有数据工具、位置映射、质量分析口径和知识库证据的工业视觉缺陷分析系统。

## 二、第一阶段 MVP 功能

第一阶段只围绕“检测结果分析”闭环，不做模型训练、不接实时 PLC、不做复杂调度。

核心问题：

- 最近一小时/一天检测出了哪些缺陷
- 哪类缺陷最多
- 哪个方坯表面缺陷最多
- 方坯头部/中部/尾部哪个位置更容易出现缺陷
- 哪个炉号、计划号、方坯 ID 的 NG 率最高
- 某类缺陷主要集中在哪个表面、哪个长度区域、边部还是中心
- 自动生成缺陷统计与空间分布分析报告

第一阶段输出形式：

- API JSON 结果
- Agent 中文结论
- Markdown 分析报告
- 缺陷原图路径证据

## 三、数据结构

主表：`defect_records`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| defect_id | TEXT | 缺陷唯一 ID |
| timestamp | TEXT | 检测时间 |
| billet_id | TEXT | 方坯 ID |
| furnace_no | TEXT | 炉号 |
| plan_no | TEXT | 计划号 |
| camera_id | TEXT | 相机 ID |
| face_id | TEXT | 映射后的表面：top/right/bottom/left |
| defect_type | TEXT | 缺陷类别 |
| confidence | REAL | 算法置信度 |
| bbox | TEXT | JSON 字符串，包含 x/y/w/h |
| image_path | TEXT | 缺陷图片路径 |
| length_pos | REAL | 方坯长度归一化位置，0 为头部，1 为尾部 |
| width_pos | REAL | 当前表面宽度归一化位置 |
| severity | TEXT | minor/major/critical |
| review_status | TEXT | pending/confirmed/false_positive |
| frame_no | INTEGER | 图像序列帧号 |
| billet_speed_mps | REAL | 方坯速度 |
| image_width | INTEGER | 图像宽度 |
| image_height | INTEGER | 图像高度 |
| length_region | TEXT | head/middle/tail |
| width_region | TEXT | edge/center |

辅助表：`billet_quality`

用于 NG 率分母，包含 `inspected_frames` 和 `ng_frames`。如果只靠缺陷表，只能做缺陷数排名，不能严谨计算 NG 率。

## 四、位置映射方法

相机到表面映射：

```python
CAMERA_FACE_MAP = {
    "CAM01": "top",
    "CAM02": "right",
    "CAM03": "bottom",
    "CAM04": "left",
}
```

现场投产时，这个映射应来自相机标定配置表。四台相机在方坯对角线位置时，仍应以标定后的视场覆盖关系为准，而不是只凭安装方向硬编码。

长度方向 `length_pos`：

可选计算方法：

- 帧序号法：`length_pos = (frame_no - start_frame) / total_frames`
- 速度法：`length_pos = speed_mps * (timestamp - billet_start_time) / billet_length_m`
- 图像序列法：`length_pos = image_index / image_count`

区域划分：

- `0 <= length_pos < 0.2`：头部
- `0.2 <= length_pos <= 0.8`：中部
- `0.8 < length_pos <= 1`：尾部

宽度方向 `width_pos`：

先计算 bbox 中心点：

```python
center_x = bbox["x"] + bbox["w"] / 2
width_pos = center_x / image_width
```

区域划分：

- `width_pos <= 0.2` 或 `width_pos >= 0.8`：边部
- 其他：中心区域

## 五、Agent 工具层

第一阶段已实现工具：

- `query_defect_stats`：总体统计
- `group_defects_by_type`：按缺陷类别聚合
- `group_defects_by_face`：按方坯表面聚合
- `group_defects_by_position`：按头/中/尾、边部/中心聚合
- `query_defects_by_furnace`：按炉号/计划号/方坯聚合
- `get_top_ng_billets`：计算方坯 NG 率排名
- `get_defect_images`：返回缺陷原图证据
- `generate_defect_report`：生成 Markdown 报告

默认统计口径会排除 `review_status=false_positive` 的记录，避免已确认误检污染结论。

## 六、LangGraph 工作流

流程：

用户问题 -> 意图识别 -> 查询缺陷数据 -> 统计分析 -> 必要时检索知识库 -> 生成结论 -> 输出证据和报告

`AgentState` 字段：

- `question`：用户问题
- `intent`：识别出的意图
- `start_time` / `end_time`：时间范围
- `filters`：缺陷类型、炉号、计划号、方坯 ID、表面、位置过滤条件
- `tool_results`：工具返回结果
- `need_rag`：是否需要知识库
- `kb_evidence`：知识库证据
- `answer`：最终回答
- `report_path`：报告路径
- `errors`：工具错误

节点职责：

- `parse_intent`：关键词识别意图、抽取时间范围和过滤条件
- `query_data`：根据意图调用对应 tools
- `analyze`：检查工具结果是否为空或失败
- `retrieve_knowledge`：检索缺陷规则、原因、报告模板等知识
- `generate_answer`：基于工具结果和知识证据生成中文结论

条件路由：

- 如果问题涉及报告、原因、标准、等级、建议，进入 RAG
- 其他统计类问题直接生成答案

工具失败处理：

- 捕获异常写入 `errors`
- 回答中明确说明工具失败
- 只基于成功返回的数据输出结论

防胡编机制：

- 回答必须引用 `tool_results`
- 输出时间窗、过滤条件、统计口径
- 对异常判断给出数量、占比、NG 率或严重缺陷数
- 数据不足时明确说明不能判断

## 七、RAG 知识库

第一阶段知识库内容：

- 缺陷类别说明
- 方坯表面缺陷判定标准
- 缺陷等级规则
- 常见缺陷原因
- 现场质检经验
- 缺陷分析报告模板

文档切分：

- 按主题切分，每个 chunk 约 200-500 字
- 一个 chunk 只描述一个缺陷类别、规则或模板段落

metadata 设计：

- `doc_id`
- `title`
- `category`
- `defect_type`
- `severity`
- `process_stage`
- `tags`
- `source`
- `version`

FAISS / Milvus 选择：

- 第一阶段：FAISS 或轻量关键词检索，适合本地 Demo、简历项目、单机部署
- 生产阶段：Milvus，适合多文档、多用户、权限隔离和增量更新

回答引用方式：

- Agent 在回答尾部列出 `[doc_id] title`
- 统计结论引用数据库工具结果
- 原因、等级、建议引用知识库 chunk

## 八、后端接口

已实现 FastAPI 接口：

- `POST /api/agent/chat`
- `GET /api/defects/stats`
- `GET /api/defects/images`
- `POST /api/reports/generate`

建议后续增加：

- `POST /api/defects/import`
- `PATCH /api/defects/{defect_id}/review`
- `GET /api/reports/{report_id}`

## 九、项目目录结构

```text
InspectPilot/
  backend/
    main.py
    requirements.txt
    schemas.py
    agent/
      graph.py
      intent.py
      state.py
    tools/
      defect_tools.py
    rag/
      retriever.py
      knowledge_base.md
    data/
      schema.sql
      sample_defects.csv
      init_db.py
    prompts/
      agent_prompt.md
  frontend/
    index.html
    package.json
    src/
      App.vue
      main.js
  tests/
    test_tools.py
  docs/
    MVP_DESIGN.md
    reports/
```

第一阶段先写文件顺序：

1. `backend/data/schema.sql`
2. `backend/data/sample_defects.csv`
3. `backend/data/init_db.py`
4. `backend/tools/defect_tools.py`
5. `backend/agent/intent.py`
6. `backend/agent/graph.py`
7. `backend/main.py`
8. `backend/rag/knowledge_base.md`
9. `docs/MVP_DESIGN.md`

