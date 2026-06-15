from typing import Any, Dict, List, Optional, TypedDict


class AgentState(TypedDict, total=False):
    question: str
    intent: str
    start_time: Optional[str]
    end_time: Optional[str]
    filters: Dict[str, Any]
    tool_results: Dict[str, Any]
    need_rag: bool
    kb_evidence: List[Dict[str, str]]
    answer: str
    report_path: Optional[str]
    errors: List[str]

