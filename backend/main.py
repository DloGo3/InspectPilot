from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from agent.graph import run_agent
from data.init_db import DEFAULT_DB_PATH, init_database
from rag.retriever import get_rag_status, retrieve_knowledge
from schemas import ChatRequest, ChatResponse, ReportRequest
from tools.defect_tools import (
    generate_defect_report,
    get_defect_images,
    group_defects_by_face,
    group_defects_by_position,
    group_defects_by_type,
    query_defect_stats,
)

app = FastAPI(
    title="InspectPilot API",
    description="Industrial vision defect analysis Agent for billet surface inspection results.",
    version="0.3.1",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    if not Path(DEFAULT_DB_PATH).exists():
        init_database(DEFAULT_DB_PATH, reset=True)


@app.get("/api/health")
def health():
    return {"status": "ok", "db_path": str(DEFAULT_DB_PATH)}


@app.post("/api/agent/chat", response_model=ChatResponse)
def agent_chat(payload: ChatRequest):
    state = run_agent(payload.question)
    return ChatResponse(
        answer=state.get("answer", ""),
        scope=state.get("scope", "defect_analysis"),
        direct_answer=state.get("direct_answer"),
        tool_calls=state.get("tool_calls", []),
        evidence=state.get("evidence", []),
        time_window=state.get("time_window", {}),
        filters=state.get("filters", {}),
        warnings=state.get("warnings", []),
        planner_mode=state.get("planner_mode", "fallback"),
        answer_mode=state.get("answer_mode", "fallback"),
        llm_used=state.get("llm_used", False),
        llm_error=state.get("llm_error"),
        intent=state.get("intent", "unknown"),
        need_rag=state.get("need_rag", False),
        kb_evidence=state.get("kb_evidence", []),
        rag_trace=state.get("rag_trace", []),
        tool_results=state.get("tool_results", {}),
        report_path=state.get("report_path"),
    )


@app.get("/api/rag/status")
def rag_status():
    return get_rag_status()


@app.get("/api/rag/search")
def rag_search(q: str = Query(..., min_length=1), top_k: int = Query(3, ge=1, le=10)):
    return {"query": q, "top_k": top_k, "items": retrieve_knowledge(q, top_k=top_k)}


@app.get("/api/defects/stats")
def defects_stats(
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    group_by: str = Query("summary", pattern="^(summary|type|face|position)$"),
    defect_type: Optional[str] = None,
    furnace_no: Optional[str] = None,
    plan_no: Optional[str] = None,
    billet_id: Optional[str] = None,
):
    filters = {
        k: v
        for k, v in {
            "defect_type": defect_type,
            "furnace_no": furnace_no,
            "plan_no": plan_no,
            "billet_id": billet_id,
        }.items()
        if v
    }
    if group_by == "type":
        return group_defects_by_type(start_time, end_time, filters)
    if group_by == "face":
        return group_defects_by_face(start_time, end_time, filters)
    if group_by == "position":
        return group_defects_by_position(start_time, end_time, filters)
    return query_defect_stats(start_time, end_time, filters)


@app.get("/api/defects/images")
def defects_images(
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    defect_type: Optional[str] = None,
    furnace_no: Optional[str] = None,
    plan_no: Optional[str] = None,
    billet_id: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
):
    filters = {
        k: v
        for k, v in {
            "defect_type": defect_type,
            "furnace_no": furnace_no,
            "plan_no": plan_no,
            "billet_id": billet_id,
        }.items()
        if v
    }
    return get_defect_images(start_time, end_time, filters, limit=limit)


@app.post("/api/reports/generate")
def reports_generate(payload: ReportRequest):
    return generate_defect_report(
        start_time=payload.start_time,
        end_time=payload.end_time,
        filters=payload.filters,
        title=payload.title,
    )
