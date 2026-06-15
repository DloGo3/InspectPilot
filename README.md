# InspectPilot

InspectPilot 是一个面向钢铁方坯表面视觉检测结果的工业缺陷分析 Agent。第一阶段 MVP 聚焦检测结果统计、空间分布分析、炉号/计划号质量异常识别和自动报告生成。

## 项目定位

- 项目名称：InspectPilot - 方坯表面缺陷分析 Agent
- 项目类型：工业视觉缺陷分析 Agent，不是普通聊天机器人
- 简历关键词：FastAPI、LangGraph、RAG、SQLite/MySQL、FAISS/Milvus、工业视觉检测、质量分析、缺陷空间分布

## 启动后端

```powershell
cd D:\求职\agent系统学习codex\InspectPilot\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python data\init_db.py --reset
uvicorn main:app --reload
```

访问：

- API 文档：http://127.0.0.1:8000/docs
- 健康检查：http://127.0.0.1:8000/api/health

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

