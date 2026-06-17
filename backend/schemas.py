from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str = Field(..., examples=["最近一小时检测出了哪些缺陷？"])


class ChatResponse(BaseModel):
    answer: str
    scope: str = "defect_analysis"
    direct_answer: Optional[str] = None
    tool_calls: List[Dict[str, Any]] = Field(default_factory=list)
    evidence: List[Dict[str, Any]] = Field(default_factory=list)
    time_window: Dict[str, Any] = Field(default_factory=dict)
    filters: Dict[str, Any] = Field(default_factory=dict)
    warnings: List[str] = Field(default_factory=list)
    planner_mode: str = "fallback"
    answer_mode: str = "fallback"
    llm_used: bool = False
    llm_error: Optional[str] = None
    intent: str = "unknown"
    tool_results: Dict[str, Any] = Field(default_factory=dict)
    report_path: Optional[str] = None


class ReportRequest(BaseModel):
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    filters: Dict[str, Any] = Field(default_factory=dict)
    title: str = "方坯表面缺陷统计与空间分布分析报告"
