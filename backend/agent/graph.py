from typing import Any, Dict, List, Optional

from agent.intent import extract_filters, infer_intent, should_use_rag
from agent.llm_client import chat_completion, extract_json_object
from agent.prompts import ANSWER_SYSTEM_PROMPT, TOOL_PLANNER_SYSTEM_PROMPT
from agent.state import AgentState
from agent.tool_registry import (
    DIAGNOSTIC_TOOL_NAMES,
    TOOL_DEFINITIONS,
    compact_tool_results,
    execute_registered_tool,
    parse_tool_arguments,
    result_has_data,
    summarize_result,
)
from config import get_settings
from tools.defect_tools import get_latest_timestamp
from tools.diagnostic_tools import DEFAULT_ANALYSIS_START, DEFAULT_DEFECT_TYPE, DEFAULT_SCENARIO_ID, DEFAULT_TARGET_END

try:
    from langgraph.graph import END, StateGraph
except Exception:  # pragma: no cover - fallback keeps the MVP runnable without LangGraph installed.
    END = None
    StateGraph = None


GREETING_ANSWERS = {
    "晚上": "晚上好！我是 InspectPilot，可以帮你分析方坯表面缺陷检测结果。你可以问我：哪类缺陷最多、哪个表面缺陷最多、裂纹主要集中在哪里、哪个炉号/方坯 NG 率最高，或生成缺陷分析报告。",
    "早上": "早上好！我是 InspectPilot，可以帮你分析方坯表面缺陷检测结果。你可以问我：哪类缺陷最多、哪个表面缺陷最多、裂纹主要集中在哪里、哪个炉号/方坯 NG 率最高，或生成缺陷分析报告。",
    "default": "你好！我是 InspectPilot，可以帮你分析方坯表面缺陷检测结果。你可以问我：哪类缺陷最多、哪个表面缺陷最多、裂纹主要集中在哪里、哪个炉号/方坯 NG 率最高，或生成缺陷分析报告。",
}

HELP_ANSWER = "InspectPilot 支持方坯表面缺陷检测结果分析，包括缺陷类别统计、表面分布、头中尾/边部位置分析、炉号/计划号质量关注项、NG率排名、缺陷知识解释和报告生成。"

OUT_OF_SCOPE_ANSWER = "当前 InspectPilot 主要用于方坯表面缺陷检测结果分析，暂不支持该类问题。你可以询问缺陷类别、缺陷位置、炉号质量、方坯 NG 率或报告生成。"

DEFECT_ANALYSIS_KEYWORDS = [
    "缺陷",
    "裂纹",
    "开裂",
    "裂缝",
    "划伤",
    "结疤",
    "氧化皮",
    "凹坑",
    "夹渣",
    "麻点",
    "压痕",
    "表面",
    "方坯",
    "炉号",
    "计划号",
    "ng",
    "NG",
    "置信度",
    "bbox",
    "头部",
    "中部",
    "尾部",
    "边部",
    "中心",
    "报告",
    "统计",
    "质量",
    "危险",
    "误检",
    "看错",
    "人工确认",
    "工艺问题",
    "原因",
    "标准",
    "等级",
    "规则",
    "判定",
    "复核",
    "突然增多",
    "变多",
    "异常",
    "诊断",
    "检测系统",
    "相机",
    "camera",
    "CAM",
    "成像",
    "光照",
    "FPS",
    "fps",
    "判废",
    "停线",
    "复检",
]

HELP_KEYWORDS = ["你能做什么", "支持哪些问题", "怎么使用", "如何使用", "帮助", "help", "功能"]
GREETING_WORDS = ["你好", "您好", "晚上好", "早上好", "hello", "hi"]


def classify_scope_and_answer(question: str) -> Dict[str, Optional[str]]:
    q = question.strip()
    q_lower = q.lower()
    compact = q_lower.replace(" ", "").replace("？", "").replace("?", "").replace("！", "").replace("!", "")

    if any(keyword in q for keyword in DEFECT_ANALYSIS_KEYWORDS) or "ng" in q_lower:
        return {"scope": "defect_analysis", "direct_answer": None}

    if any(keyword in q_lower for keyword in HELP_KEYWORDS) or any(keyword in q for keyword in HELP_KEYWORDS):
        return {"scope": "help", "direct_answer": HELP_ANSWER}

    if compact in GREETING_WORDS or any(compact == word.lower() for word in GREETING_WORDS):
        if "晚上" in q:
            answer = GREETING_ANSWERS["晚上"]
        elif "早上" in q:
            answer = GREETING_ANSWERS["早上"]
        else:
            answer = GREETING_ANSWERS["default"]
        return {"scope": "greeting", "direct_answer": answer}

    return {"scope": "out_of_scope", "direct_answer": OUT_OF_SCOPE_ANSWER}


def _time_window_preset(question: str) -> str:
    if "最近一小时" in question or "最近1小时" in question or "近一小时" in question:
        return "latest_1_hour"
    if "最近一天" in question or "最近1天" in question or "近一天" in question or "今天" in question:
        return "latest_24_hours"
    return "all"


def _diagnostic_scenario(question: str) -> str:
    q_lower = question.lower()
    if any(word in question for word in ["证据不足", "只有一条", "单条", "没有相机状态", "缺少相机状态"]):
        return "sparse_evidence"
    if any(word in question for word in ["多相机", "多个相机", "多台相机", "同步增加", "同步升高", "图像质量正常"]):
        return "multi_camera_quality_wave"
    if "quality_wave" in q_lower:
        return "multi_camera_quality_wave"
    if "sparse" in q_lower:
        return "sparse_evidence"
    return DEFAULT_SCENARIO_ID


def _diagnostic_camera(question: str, scenario_id: str) -> Optional[str]:
    if any(word in question for word in ["CAM02", "camera2", "Camera2", "2号相机", "二号相机", "camera 2"]):
        return "CAM02"
    if scenario_id == DEFAULT_SCENARIO_ID:
        return "CAM02"
    return None


def _rag_tool_call(question: str, min_top_k: Optional[int] = None) -> Dict[str, Any]:
    settings = get_settings()
    top_k = settings.rag_top_k
    if min_top_k is not None:
        top_k = max(top_k, min_top_k)
    return {
        "name": "retrieve_defect_knowledge",
        "arguments": {"query": question, "top_k": top_k},
        "source": "auto_rag",
    }


def _ensure_rag_tool_call(
    question: str,
    planned: List[Dict[str, Any]],
    min_top_k: Optional[int] = None,
) -> List[Dict[str, Any]]:
    settings = get_settings()
    desired_top_k = settings.rag_top_k
    if min_top_k is not None:
        desired_top_k = max(desired_top_k, min_top_k)
    for call in planned:
        if call.get("name") == "retrieve_defect_knowledge":
            arguments = call.setdefault("arguments", {})
            if not arguments.get("query"):
                arguments["query"] = question
            try:
                current_top_k = int(arguments.get("top_k") or 0)
            except (TypeError, ValueError):
                current_top_k = 0
            if current_top_k < desired_top_k:
                arguments["top_k"] = desired_top_k
            return planned
    return planned + [_rag_tool_call(question, min_top_k=min_top_k)]


def _diagnostic_tool_args(question: str, tool_name: str) -> Dict[str, Any]:
    filters = extract_filters(question)
    scenario_id = _diagnostic_scenario(question)
    camera_id = _diagnostic_camera(question, scenario_id)
    payload: Dict[str, Any] = {
        "scenario_id": scenario_id,
        "defect_type": filters.get("defect_type", DEFAULT_DEFECT_TYPE),
        "analysis_start": DEFAULT_ANALYSIS_START,
        "target_end": DEFAULT_TARGET_END,
    }
    if tool_name in {"analyze_camera_health", "analyze_image_quality", "estimate_false_positive_risk"}:
        payload["camera_id"] = camera_id
    return payload


def _diagnostic_tool_block(question: str) -> List[Dict[str, Any]]:
    return [
        {
            "name": name,
            "arguments": _diagnostic_tool_args(question, name),
            "source": "auto_diagnostic_guardrail",
        }
        for name in [
            "detect_defect_spike",
            "analyze_defect_camera_concentration",
            "analyze_camera_health",
            "analyze_image_quality",
            "estimate_false_positive_risk",
        ]
    ]


def _ensure_diagnostic_tool_calls(question: str, planned: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if infer_intent(question) != "diagnosis":
        return planned

    non_diagnostic = [call for call in planned if call.get("name") not in DIAGNOSTIC_TOOL_NAMES]
    return _diagnostic_tool_block(question) + non_diagnostic


def _fallback_tool_plan(question: str) -> List[Dict[str, Any]]:
    intent = infer_intent(question)
    filters = extract_filters(question)
    preset = _time_window_preset(question)

    def args(extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"time_window_preset": preset, "filters": filters}
        if extra:
            payload.update(extra)
        return payload

    def finalize(calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not should_use_rag(question, intent):
            return calls
        min_top_k = 5 if intent == "diagnosis" else None
        return _ensure_rag_tool_call(question, calls, min_top_k=min_top_k)

    if intent == "diagnosis":
        scenario_id = _diagnostic_scenario(question)
        camera_id = _diagnostic_camera(question, scenario_id)
        diagnostic_args: Dict[str, Any] = {
            "scenario_id": scenario_id,
            "defect_type": filters.get("defect_type", DEFAULT_DEFECT_TYPE),
            "analysis_start": DEFAULT_ANALYSIS_START,
            "target_end": DEFAULT_TARGET_END,
        }
        diagnostic_args_with_camera = dict(diagnostic_args)
        if camera_id:
            diagnostic_args_with_camera["camera_id"] = camera_id
        calls = [
            {"name": "detect_defect_spike", "arguments": diagnostic_args},
            {"name": "analyze_defect_camera_concentration", "arguments": diagnostic_args},
            {"name": "analyze_camera_health", "arguments": diagnostic_args_with_camera},
            {"name": "analyze_image_quality", "arguments": diagnostic_args_with_camera},
            {"name": "estimate_false_positive_risk", "arguments": diagnostic_args_with_camera},
        ]
        return finalize(calls)

    if intent in {"general_stats", "recent_defects"}:
        return finalize([
            {"name": "query_defect_stats", "arguments": args()},
            {"name": "group_defects_by_type", "arguments": args()},
            {"name": "get_defect_images", "arguments": args({"limit": 5})},
        ])
    if intent == "group_by_type":
        return finalize([{"name": "group_defects_by_type", "arguments": args()}])
    if intent == "group_by_face":
        return finalize([{"name": "group_defects_by_face", "arguments": args()}])
    if intent == "group_by_position":
        calls = [{"name": "group_defects_by_position", "arguments": args()}]
        if filters.get("defect_type"):
            calls.append({"name": "group_defects_by_face", "arguments": args()})
        return finalize(calls)
    if intent == "top_ng":
        return finalize([{"name": "get_top_ng_billets", "arguments": args({"limit": 10})}])
    if intent == "furnace_quality":
        return finalize([{"name": "query_defects_by_furnace", "arguments": args({"group_level": "furnace_no"})}])
    if intent == "plan_quality":
        return finalize([{"name": "query_defects_by_furnace", "arguments": args({"group_level": "plan_no"})}])
    if intent == "images":
        return finalize([{"name": "get_defect_images", "arguments": args({"limit": 20})}])
    if intent == "report":
        calls = [{"name": "generate_defect_report", "arguments": args()}]
        return finalize(calls)
    if intent == "knowledge":
        return [_rag_tool_call(question)]

    calls = [{"name": "query_defect_stats", "arguments": args()}]
    return finalize(calls)


def classify_user_scope_node(state: AgentState) -> AgentState:
    question = state["question"]
    classified = classify_scope_and_answer(question)
    state["scope"] = classified["scope"] or "out_of_scope"
    state["direct_answer"] = classified["direct_answer"]
    state["intent"] = infer_intent(question)
    state["need_rag"] = state["scope"] == "defect_analysis" and should_use_rag(question, state["intent"])
    state["tool_results"] = {}
    state["tool_calls"] = []
    state["planned_tool_calls"] = []
    state["kb_evidence"] = []
    state["rag_trace"] = []
    state["diagnosis"] = {}
    state["evidence"] = []
    state["warnings"] = []
    state["errors"] = []
    state["planner_mode"] = "none" if state["scope"] != "defect_analysis" else "fallback"
    state["answer_mode"] = "direct" if state["scope"] != "defect_analysis" else "fallback"
    state["llm_used"] = False
    state["llm_error"] = None
    state["time_window"] = {"preset": _time_window_preset(question), "start_time": None, "end_time": None}
    state["filters"] = extract_filters(question)
    return state


def prepare_node(state: AgentState) -> AgentState:
    return state


def route_after_scope(state: AgentState) -> str:
    return "prepare" if state.get("scope") == "defect_analysis" else "direct_answer"


def direct_answer_node(state: AgentState) -> AgentState:
    state["answer"] = state.get("direct_answer") or OUT_OF_SCOPE_ANSWER
    state["tool_calls"] = []
    state["planned_tool_calls"] = []
    state["tool_results"] = {}
    state["kb_evidence"] = []
    state["rag_trace"] = []
    state["diagnosis"] = {}
    state["evidence"] = []
    state["warnings"] = []
    state["planner_mode"] = "none"
    state["answer_mode"] = "direct"
    state["llm_used"] = False
    state["llm_error"] = None
    return state


def _record_llm_error(state: AgentState, message: str) -> None:
    existing = state.get("llm_error")
    state["llm_error"] = f"{existing}; {message}" if existing else message


def plan_tool_calls_node(state: AgentState) -> AgentState:
    question = state["question"]
    force_fallback = bool(state.get("force_fallback"))
    settings = get_settings()

    if force_fallback:
        state["planned_tool_calls"] = _fallback_tool_plan(question)
        state["planner_mode"] = "fallback"
        state.setdefault("warnings", []).append("llm_disabled_for_eval;used_fallback_tool_planner")
        return state

    if not settings.llm_configured:
        state["planned_tool_calls"] = _fallback_tool_plan(question)
        state["planner_mode"] = "fallback"
        _record_llm_error(state, "planner:llm_not_configured")
        state.setdefault("warnings", []).append("OPENAI_API_KEY/OPENAI_BASE_URL not configured;used_fallback_tool_planner")
        return state

    latest_timestamp = get_latest_timestamp()
    messages = [
        {"role": "system", "content": TOOL_PLANNER_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"用户问题：{question}\n"
                f"检测数据库最新 timestamp：{latest_timestamp or 'unknown'}\n"
                "请通过 tool_calls 选择需要调用的工具。"
            ),
        },
    ]

    try:
        response = chat_completion(
            settings=settings,
            messages=messages,
            tools=TOOL_DEFINITIONS,
            tool_choice="auto",
            temperature=0.0,
        )
        message = response.choices[0].message
        raw_tool_calls = getattr(message, "tool_calls", None) or []
        planned: List[Dict[str, Any]] = []
        for call in raw_tool_calls:
            function = call.function
            planned.append(
                {
                    "id": getattr(call, "id", None),
                    "name": function.name,
                    "arguments": parse_tool_arguments(function.arguments),
                    "source": "llm",
                }
            )
        if not planned:
            planned = _fallback_tool_plan(question)
            state["planner_mode"] = "fallback"
            _record_llm_error(state, "planner:llm_returned_no_tool_calls")
            state.setdefault("warnings", []).append("llm_returned_no_tool_calls;used_fallback_tool_planner")
        else:
            state["planner_mode"] = "llm"
            state["llm_used"] = True
        planned = _ensure_diagnostic_tool_calls(question, planned)
        if state.get("need_rag"):
            min_top_k = 5 if state.get("intent") == "diagnosis" else None
            planned = _ensure_rag_tool_call(question, planned, min_top_k=min_top_k)
        state["planned_tool_calls"] = planned
    except Exception as exc:
        state["planned_tool_calls"] = _fallback_tool_plan(question)
        state["planner_mode"] = "fallback"
        _record_llm_error(state, f"planner:{exc}")
        state.setdefault("warnings", []).append(f"llm_tool_planning_failed:{exc};used_fallback_tool_planner")

    return state


def _merge_filters(current: Dict[str, Any], new_filters: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(current or {})
    for key, value in (new_filters or {}).items():
        if value not in (None, ""):
            merged[key] = value
    return merged


def _choose_time_window(current: Dict[str, Any], candidate: Dict[str, Any]) -> Dict[str, Any]:
    if candidate and candidate.get("preset") == "knowledge_base":
        return current or candidate
    if current and current.get("preset") == "knowledge_base":
        return candidate or current
    if not current or current.get("preset") == "all":
        return candidate
    if candidate and candidate.get("preset") != "all":
        return candidate
    return current


def execute_tools_node(state: AgentState) -> AgentState:
    tool_results: Dict[str, Any] = {}
    tool_calls: List[Dict[str, Any]] = []
    evidence: List[Dict[str, Any]] = []
    kb_evidence: List[Dict[str, Any]] = []
    rag_trace: List[Dict[str, Any]] = []
    diagnosis: Dict[str, Any] = {}
    warnings = list(state.get("warnings", []))
    filters = dict(state.get("filters", {}))
    time_window = dict(state.get("time_window", {}))

    for index, planned in enumerate(state.get("planned_tool_calls", []), start=1):
        name = planned.get("name")
        raw_args = planned.get("arguments", {})
        execution = execute_registered_tool(name, raw_args)
        call_key = f"{name}#{index}"
        result = execution["result"]

        warnings.extend(execution.get("warnings", []))
        if name == "retrieve_defect_knowledge" and result.get("warnings"):
            warnings.extend([str(warning) for warning in result.get("warnings", [])])
        filters = _merge_filters(filters, execution.get("filters", {}))
        time_window = _choose_time_window(time_window, execution.get("time_window", {}))
        tool_results[call_key] = {
            "tool": name,
            "arguments": execution.get("arguments", {}),
            "ok": execution.get("ok", False),
            "result": result,
        }

        has_data = execution.get("ok", False) and result_has_data(name, result)
        summary = summarize_result(name, result) if execution.get("ok") else "工具调用失败。"
        if name == "retrieve_defect_knowledge" and result.get("items"):
            kb_evidence.extend(result.get("items", []))
        if name == "retrieve_defect_knowledge" and result.get("trace"):
            trace = dict(result.get("trace") or {})
            trace["need_rag"] = bool(state.get("need_rag", False))
            trace["tool_name"] = name
            trace_warnings = list(trace.get("warnings", []))
            for warning in execution.get("warnings", []):
                if warning not in trace_warnings:
                    trace_warnings.append(warning)
            trace["warnings"] = trace_warnings
            rag_trace.append(trace)
        if name == "estimate_false_positive_risk" and execution.get("ok", False):
            diagnosis = result
        tool_calls.append(
            {
                "name": name,
                "arguments": execution.get("arguments", {}),
                "ok": execution.get("ok", False),
                "has_data": has_data,
                "summary": summary,
            }
        )
        if has_data:
            evidence.append(
                {
                    "tool": name,
                    "summary": summary,
                    "data_source": (
                        "backend.rag.knowledge_base.md via hybrid FAISS/BGE + BM25 retrieval"
                        if name == "retrieve_defect_knowledge"
                        else "backend.tools.diagnostic_tools deterministic diagnostic result"
                        if name in DIAGNOSTIC_TOOL_NAMES
                        else "backend.tools.defect_tools deterministic result"
                    ),
                    "time_window": execution.get("time_window", {}),
                    "filters": execution.get("filters", {}),
                }
            )
        if name == "generate_defect_report" and result.get("report_path"):
            state["report_path"] = result["report_path"]

    state["tool_results"] = tool_results
    state["tool_calls"] = tool_calls
    state["kb_evidence"] = kb_evidence
    state["rag_trace"] = rag_trace
    state["diagnosis"] = diagnosis
    state["evidence"] = evidence
    state["warnings"] = warnings
    state["filters"] = filters
    state["time_window"] = time_window
    state["start_time"] = time_window.get("start_time")
    state["end_time"] = time_window.get("end_time")
    return state


def _format_diagnostic_answer(diagnosis: Dict[str, Any]) -> str:
    conclusion = diagnosis.get("conclusion") or diagnosis.get("summary") or "当前数据不足以判断"
    evidence = diagnosis.get("evidence") or []
    candidates = diagnosis.get("root_cause_candidates") or []
    actions = diagnosis.get("recommended_actions") or []
    missing_data = diagnosis.get("missing_data") or []
    metrics = diagnosis.get("key_metrics") or {}

    lines = [
        "【结论】",
        conclusion,
        "",
        "【关键证据】",
    ]
    if evidence:
        for index, item in enumerate(evidence[:6], start=1):
            lines.append(f"{index}. {item}")
    else:
        lines.append("1. 当前没有足够诊断证据。")

    if metrics:
        scenario_id = metrics.get("scenario_id")
        if scenario_id:
            lines.append(f"{len(evidence[:6]) + 1 if evidence else 2}. 诊断场景：{scenario_id}")

    lines.extend(["", "【可能原因排序】"])
    if candidates:
        for index, item in enumerate(candidates, start=1):
            item_evidence = "；".join(item.get("evidence", [])[:3])
            suffix = f"：{item_evidence}" if item_evidence else ""
            lines.append(f"{index}. {item.get('name')}，可能性 {item.get('likelihood')}{suffix}")
    else:
        lines.append("1. 当前证据不足，不能可靠排序。")

    lines.extend(["", "【建议动作】"])
    if actions:
        for index, item in enumerate(actions, start=1):
            lines.append(f"{index}. {item}")
    else:
        lines.append("1. 先补齐原图、相机状态、图像质量和人工复核记录。")

    lines.extend(["", "【仍需补充的数据】"])
    if missing_data:
        for index, item in enumerate(missing_data, start=1):
            lines.append(f"{index}. {item}")
    else:
        lines.append("1. 人工复核结论和现场工艺记录。")

    return "\n".join(lines)


def _deterministic_answer(state: AgentState) -> str:
    if not state.get("evidence"):
        return "当前数据不足以判断"

    if state.get("intent") == "diagnosis" and state.get("diagnosis"):
        return _format_diagnostic_answer(state["diagnosis"])

    stats_evidence = [item for item in state.get("evidence", []) if item.get("tool") != "retrieve_defect_knowledge"]
    kb_evidence = _answer_kb_evidence(state.get("kb_evidence", []))
    lines: List[str] = []

    if stats_evidence:
        lines.append(
            f"分析口径：时间窗 {state.get('time_window', {}).get('start_time') or '不限'} "
            f"至 {state.get('time_window', {}).get('end_time') or '不限'}；"
            f"过滤条件 {state.get('filters') or '无'}；默认排除已标记误检的记录。"
        )

    for item in stats_evidence:
        lines.append(f"- {item['summary']}")

    if kb_evidence:
        lines.append("知识库解释：")
        for item in kb_evidence[:3]:
            lines.append(f"- {item.get('title')}：{item.get('content')}")

    if stats_evidence:
        lines.append("证据来源：确定性 defect_tools 工具返回结果；质量闭环仍需结合人工复核和现场工艺记录。")
    if kb_evidence:
        lines.append("知识来源：backend/rag/knowledge_base.md；知识解释用于辅助复核，不直接等同于当前批次的确定原因。")
    return "\n".join(lines)


def _answer_kb_evidence(kb_evidence: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    budgeted = [item for item in kb_evidence if item.get("included_in_answer_context", True)]
    return budgeted or kb_evidence[:1]


def _answer_tool_results(tool_results: Dict[str, Any]) -> Dict[str, Any]:
    compacted: Dict[str, Any] = {}
    for key, value in (tool_results or {}).items():
        entry = dict(value or {})
        result = dict(entry.get("result") or {})
        if entry.get("tool") == "retrieve_defect_knowledge":
            items = result.get("items", [])
            context_items = result.get("context_items") or _answer_kb_evidence(items)
            result["items"] = context_items
            result["context_items"] = context_items
            result["omitted_doc_ids"] = [
                item.get("doc_id")
                for item in items
                if item.get("doc_id") and not item.get("included_in_answer_context", True)
            ]
        entry["result"] = result
        compacted[key] = entry
    return compacted


def generate_answer_node(state: AgentState) -> AgentState:
    if not state.get("evidence"):
        state["answer"] = "当前数据不足以判断"
        state["answer_mode"] = "fallback"
        warnings = list(state.get("warnings", []))
        warnings.append("no_tool_data;answer_guardrail_triggered")
        state["warnings"] = warnings
        return state

    if state.get("intent") == "diagnosis" and state.get("diagnosis"):
        state["answer"] = _format_diagnostic_answer(state["diagnosis"])
        state["answer_mode"] = "diagnostic_guardrail"
        return state

    settings = get_settings()
    force_fallback = bool(state.get("force_fallback"))
    if force_fallback or not settings.llm_configured:
        state["answer"] = _deterministic_answer(state)
        state["answer_mode"] = "fallback"
        if not force_fallback and not settings.llm_configured:
            _record_llm_error(state, "answer:llm_not_configured")
        return state

    messages = [
        {"role": "system", "content": ANSWER_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"用户问题：{state['question']}\n"
                f"time_window：{state.get('time_window')}\n"
                f"filters：{state.get('filters')}\n"
                f"evidence：{state.get('evidence')}\n"
                f"diagnosis：{state.get('diagnosis', {})}\n"
                f"kb_evidence：{_answer_kb_evidence(state.get('kb_evidence', []))}\n"
                f"tool_results：{compact_tool_results(_answer_tool_results(state.get('tool_results', {})))}\n"
                "请输出 JSON：{\"answer\":\"...\",\"warnings\":[\"...\"]}"
            ),
        },
    ]

    try:
        response = chat_completion(settings=settings, messages=messages, temperature=0.1)
        content = response.choices[0].message.content or ""
        parsed = extract_json_object(content)
        answer = parsed.get("answer")
        if not answer:
            raise ValueError("llm_answer_json_missing_answer")
        state["answer"] = answer
        state["answer_mode"] = "llm"
        state["llm_used"] = True
        extra_warnings = parsed.get("warnings", [])
        if isinstance(extra_warnings, list):
            state["warnings"] = list(state.get("warnings", [])) + [str(item) for item in extra_warnings]
    except Exception as exc:
        state["answer"] = _deterministic_answer(state)
        state["answer_mode"] = "fallback"
        _record_llm_error(state, f"answer:{exc}")
        state["warnings"] = list(state.get("warnings", [])) + [f"llm_answer_generation_failed:{exc};used_deterministic_answer"]

    return state


def _finalize_rag_trace(state: AgentState) -> AgentState:
    traces: List[Dict[str, Any]] = []
    for trace in state.get("rag_trace", []):
        updated = dict(trace)
        updated["need_rag"] = bool(state.get("need_rag", False))
        updated["answer_mode"] = state.get("answer_mode", "fallback")
        traces.append(updated)
    state["rag_trace"] = traces
    return state


def build_graph():
    if StateGraph is None:
        return None

    graph = StateGraph(AgentState)
    graph.add_node("classify_user_scope", classify_user_scope_node)
    graph.add_node("prepare", prepare_node)
    graph.add_node("direct_answer", direct_answer_node)
    graph.add_node("plan_tool_calls", plan_tool_calls_node)
    graph.add_node("execute_tools", execute_tools_node)
    graph.add_node("generate_answer", generate_answer_node)

    graph.set_entry_point("classify_user_scope")
    graph.add_conditional_edges(
        "classify_user_scope",
        route_after_scope,
        {"prepare": "prepare", "direct_answer": "direct_answer"},
    )
    graph.add_edge("prepare", "plan_tool_calls")
    graph.add_edge("plan_tool_calls", "execute_tools")
    graph.add_edge("execute_tools", "generate_answer")
    graph.add_edge("direct_answer", END)
    graph.add_edge("generate_answer", END)
    return graph.compile()


COMPILED_GRAPH = build_graph()


def _run_without_langgraph(initial_state: AgentState) -> AgentState:
    state = classify_user_scope_node(initial_state)
    if route_after_scope(state) == "direct_answer":
        return direct_answer_node(state)
    state = prepare_node(state)
    state = plan_tool_calls_node(state)
    state = execute_tools_node(state)
    state = generate_answer_node(state)
    return state


def run_agent(question: str, force_fallback: bool = False) -> AgentState:
    initial_state: AgentState = {"question": question, "force_fallback": force_fallback}
    if COMPILED_GRAPH is not None:
        return _finalize_rag_trace(COMPILED_GRAPH.invoke(initial_state))
    return _finalize_rag_trace(_run_without_langgraph(initial_state))
