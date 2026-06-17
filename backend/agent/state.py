from typing import Any, Dict, List, Optional, TypedDict


class AgentState(TypedDict, total=False):
    question: str
    force_fallback: bool
    scope: str
    direct_answer: Optional[str]
    intent: str
    start_time: Optional[str]
    end_time: Optional[str]
    filters: Dict[str, Any]
    time_window: Dict[str, Any]
    planned_tool_calls: List[Dict[str, Any]]
    tool_calls: List[Dict[str, Any]]
    tool_results: Dict[str, Any]
    need_rag: bool
    kb_evidence: List[Dict[str, str]]
    evidence: List[Dict[str, Any]]
    answer: str
    report_path: Optional[str]
    warnings: List[str]
    errors: List[str]
    planner_mode: str
    answer_mode: str
    llm_used: bool
    llm_error: Optional[str]
