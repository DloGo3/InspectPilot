from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str = Field(..., examples=["最近一小时检测出了哪些缺陷？"])


class ChatResponse(BaseModel):
    answer: str
    intent: str
    tool_results: Dict[str, Any]
    report_path: Optional[str] = None


class ReportRequest(BaseModel):
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    filters: Dict[str, Any] = Field(default_factory=dict)
    title: str = "方坯表面缺陷统计与空间分布分析报告"

