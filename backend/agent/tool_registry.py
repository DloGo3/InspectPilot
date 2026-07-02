import json
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

from tools.defect_tools import (
    generate_defect_report,
    get_defect_images,
    get_latest_timestamp,
    get_top_ng_billets,
    group_defects_by_face,
    group_defects_by_position,
    group_defects_by_type,
    query_defect_stats,
    query_defects_by_furnace,
)
from tools.diagnostic_tools import (
    DEFAULT_ANALYSIS_START,
    DEFAULT_DEFECT_TYPE,
    DEFAULT_SCENARIO_ID,
    DEFAULT_TARGET_END,
    analyze_camera_health,
    analyze_defect_camera_concentration,
    analyze_image_quality,
    detect_defect_spike,
    estimate_false_positive_risk,
)
from rag.retriever import retrieve_agentic_knowledge

ALLOWED_FILTERS = {
    "defect_type",
    "furnace_no",
    "plan_no",
    "billet_id",
    "face_id",
    "severity",
    "length_region",
    "width_region",
}
ALLOWED_FACES = {"top", "right", "bottom", "left"}
ALLOWED_LENGTH_REGIONS = {"head", "middle", "tail"}
ALLOWED_WIDTH_REGIONS = {"edge", "center"}
ALLOWED_SEVERITY = {"minor", "major", "critical"}
DIAGNOSTIC_TOOL_NAMES = {
    "detect_defect_spike",
    "analyze_defect_camera_concentration",
    "analyze_camera_health",
    "analyze_image_quality",
    "estimate_false_positive_risk",
}

def retrieve_defect_knowledge_tool(query: str, top_k: int = 3) -> Dict[str, Any]:
    return retrieve_agentic_knowledge(query=query, top_k=top_k)


TOOL_FUNCTIONS: Dict[str, Callable[..., Dict[str, Any]]] = {
    "query_defect_stats": query_defect_stats,
    "group_defects_by_type": group_defects_by_type,
    "group_defects_by_face": group_defects_by_face,
    "group_defects_by_position": group_defects_by_position,
    "query_defects_by_furnace": query_defects_by_furnace,
    "get_top_ng_billets": get_top_ng_billets,
    "get_defect_images": get_defect_images,
    "generate_defect_report": generate_defect_report,
    "retrieve_defect_knowledge": retrieve_defect_knowledge_tool,
    "detect_defect_spike": detect_defect_spike,
    "analyze_defect_camera_concentration": analyze_defect_camera_concentration,
    "analyze_camera_health": analyze_camera_health,
    "analyze_image_quality": analyze_image_quality,
    "estimate_false_positive_risk": estimate_false_positive_risk,
}

FILTER_SCHEMA = {
    "type": "object",
    "description": "Only structured filters are allowed. Do not pass SQL.",
    "additionalProperties": False,
    "properties": {
        "defect_type": {"type": "string", "description": "Chinese defect type, e.g. 裂纹, 划伤, 结疤, 氧化皮"},
        "furnace_no": {"type": "string", "description": "Furnace number, e.g. F25061403"},
        "plan_no": {"type": "string", "description": "Plan number, e.g. P-B40-006"},
        "billet_id": {"type": "string", "description": "Billet ID, e.g. B20260614007"},
        "face_id": {"type": "string", "enum": sorted(ALLOWED_FACES)},
        "severity": {"type": "string", "enum": sorted(ALLOWED_SEVERITY)},
        "length_region": {"type": "string", "enum": sorted(ALLOWED_LENGTH_REGIONS)},
        "width_region": {"type": "string", "enum": sorted(ALLOWED_WIDTH_REGIONS)},
    },
}

COMMON_PROPERTIES = {
    "time_window_preset": {
        "type": "string",
        "enum": ["all", "latest_1_hour", "latest_24_hours"],
        "description": "Use latest_1_hour for 最近一小时, latest_24_hours for 最近一天/今天, all when no time window is requested.",
    },
    "start_time": {"type": "string", "description": "Optional ISO timestamp lower bound."},
    "end_time": {"type": "string", "description": "Optional ISO timestamp upper bound."},
    "filters": FILTER_SCHEMA,
}


def _schema(description: str, extra: Optional[Dict[str, Any]] = None, include_common: bool = True) -> Dict[str, Any]:
    properties = dict(COMMON_PROPERTIES) if include_common else {}
    if extra:
        properties.update(extra)
    return {
        "type": "function",
        "function": {
            "name": "",
            "description": description,
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": properties,
            },
        },
    }


TOOL_DEFINITIONS: List[Dict[str, Any]] = []

_TOOL_DESCRIPTIONS = {
    "query_defect_stats": "Return headline defect statistics for a time window and filters.",
    "group_defects_by_type": "Group defects by defect type. Use for questions like 哪类缺陷最多.",
    "group_defects_by_face": "Group defects by billet face/surface. Use for 哪个表面缺陷最多.",
    "group_defects_by_position": "Group defects by length region and width region. Use for 头部/中部/尾部/边部/中心/集中在哪里.",
    "query_defects_by_furnace": "Group defects by furnace_no, plan_no, or billet_id for quality anomaly ranking.",
    "get_top_ng_billets": "Return top billets by NG rate. Use for NG率最高 or 方坯ID质量异常.",
    "get_defect_images": "Return image evidence paths for matching defect records.",
    "generate_defect_report": "Generate a Markdown defect statistics and spatial distribution report.",
    "retrieve_defect_knowledge": "Retrieve defect-domain knowledge from the hybrid FAISS/BGE + BM25 RAG knowledge base. Use for 原因、标准、等级、规则、判定、报告模板、复核建议 or defect explanations.",
    "detect_defect_spike": "Detect whether a defect type has spiked after a given time compared with a baseline window.",
    "analyze_defect_camera_concentration": "Analyze whether defect events are concentrated in one camera or distributed across cameras.",
    "analyze_camera_health": "Analyze target camera FPS, brightness, temperature, black frames, and empty frames.",
    "analyze_image_quality": "Analyze target camera image brightness, blur score, black ratio, and edge-box concentration.",
    "estimate_false_positive_risk": "Combine defect spike, camera concentration, camera health, and image quality to estimate false-positive risk vs true quality wave.",
}

for _name, _description in _TOOL_DESCRIPTIONS.items():
    extra_schema = None
    include_common = True
    if _name == "query_defects_by_furnace":
        extra_schema = {
            "group_level": {"type": "string", "enum": ["furnace_no", "plan_no", "billet_id"]},
        }
    elif _name in {"get_top_ng_billets", "get_defect_images"}:
        extra_schema = {
            "limit": {"type": "integer", "minimum": 1, "maximum": 100},
        }
    elif _name == "generate_defect_report":
        extra_schema = {
            "title": {"type": "string"},
        }
    elif _name == "retrieve_defect_knowledge":
        include_common = False
        extra_schema = {
            "query": {
                "type": "string",
                "description": "Original user question or concise retrieval query about defect knowledge.",
            },
            "top_k": {"type": "integer", "minimum": 1, "maximum": 10},
        }
    elif _name in DIAGNOSTIC_TOOL_NAMES:
        include_common = False
        extra_schema = {
            "scenario_id": {
                "type": "string",
                "description": "Diagnostic mock scenario id. Default camera2_imaging_abnormal.",
            },
            "defect_type": {"type": "string", "description": "Chinese defect type, default 裂纹."},
            "camera_id": {"type": "string", "description": "Optional target camera id, e.g. CAM02."},
            "analysis_start": {"type": "string", "description": "ISO timestamp when the anomaly starts."},
            "baseline_start": {"type": "string", "description": "Optional baseline window start."},
            "baseline_end": {"type": "string", "description": "Optional baseline window end."},
            "target_end": {"type": "string", "description": "Optional target window end."},
        }

    tool_schema = _schema(_description, extra_schema, include_common=include_common)
    tool_schema["function"]["name"] = _name
    TOOL_DEFINITIONS.append(tool_schema)


def parse_tool_arguments(raw_arguments: Any) -> Dict[str, Any]:
    if isinstance(raw_arguments, dict):
        return raw_arguments
    if not raw_arguments:
        return {}
    try:
        parsed = json.loads(raw_arguments)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def resolve_time_window(args: Dict[str, Any]) -> Tuple[Optional[str], Optional[str], Dict[str, Any]]:
    start_time = args.get("start_time")
    end_time = args.get("end_time")
    preset = args.get("time_window_preset") or "all"

    if start_time or end_time:
        return start_time, end_time, {"preset": "custom", "start_time": start_time, "end_time": end_time}

    latest = get_latest_timestamp()
    if not latest or preset == "all":
        return None, None, {"preset": "all", "start_time": None, "end_time": None}

    end_dt = datetime.fromisoformat(latest)
    if preset == "latest_1_hour":
        start_dt = end_dt - timedelta(hours=1)
    elif preset == "latest_24_hours":
        start_dt = end_dt - timedelta(days=1)
    else:
        return None, None, {"preset": "all", "start_time": None, "end_time": None}

    return (
        start_dt.isoformat(timespec="seconds"),
        end_dt.isoformat(timespec="seconds"),
        {
            "preset": preset,
            "start_time": start_dt.isoformat(timespec="seconds"),
            "end_time": end_dt.isoformat(timespec="seconds"),
        },
    )


def sanitize_filters(raw_filters: Any) -> Tuple[Dict[str, Any], List[str]]:
    warnings: List[str] = []
    if not isinstance(raw_filters, dict):
        return {}, warnings

    filters: Dict[str, Any] = {}
    for key, value in raw_filters.items():
        if key not in ALLOWED_FILTERS:
            warnings.append(f"ignored_unsupported_filter:{key}")
            continue
        if value in (None, ""):
            continue
        if key == "face_id" and value not in ALLOWED_FACES:
            warnings.append(f"ignored_invalid_face_id:{value}")
            continue
        if key == "length_region" and value not in ALLOWED_LENGTH_REGIONS:
            warnings.append(f"ignored_invalid_length_region:{value}")
            continue
        if key == "width_region" and value not in ALLOWED_WIDTH_REGIONS:
            warnings.append(f"ignored_invalid_width_region:{value}")
            continue
        if key == "severity" and value not in ALLOWED_SEVERITY:
            warnings.append(f"ignored_invalid_severity:{value}")
            continue
        filters[key] = value
    return filters, warnings


def sanitize_tool_arguments(tool_name: str, raw_args: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any], List[str]]:
    warnings: List[str] = []

    if tool_name == "retrieve_defect_knowledge":
        query = str(raw_args.get("query") or "").strip()
        if not query:
            warnings.append("missing_rag_query")
        top_k = raw_args.get("top_k", 3)
        try:
            top_k = int(top_k)
        except (TypeError, ValueError):
            top_k = 3
        return (
            {"query": query, "top_k": max(1, min(top_k, 10))},
            {"preset": "knowledge_base", "start_time": None, "end_time": None},
            warnings,
        )

    if tool_name in DIAGNOSTIC_TOOL_NAMES:
        scenario_id = str(raw_args.get("scenario_id") or DEFAULT_SCENARIO_ID).strip() or DEFAULT_SCENARIO_ID
        defect_type = str(raw_args.get("defect_type") or DEFAULT_DEFECT_TYPE).strip() or DEFAULT_DEFECT_TYPE
        analysis_start = str(raw_args.get("analysis_start") or DEFAULT_ANALYSIS_START).strip() or DEFAULT_ANALYSIS_START
        target_end = str(raw_args.get("target_end") or DEFAULT_TARGET_END).strip() or DEFAULT_TARGET_END
        baseline_start = raw_args.get("baseline_start")
        baseline_end = raw_args.get("baseline_end")
        camera_id = raw_args.get("camera_id")
        sanitized = {
            "scenario_id": scenario_id,
            "defect_type": defect_type,
            "analysis_start": analysis_start,
            "baseline_start": str(baseline_start).strip() if baseline_start else None,
            "baseline_end": str(baseline_end).strip() if baseline_end else None,
            "target_end": target_end,
        }
        if tool_name in {"analyze_camera_health", "analyze_image_quality", "estimate_false_positive_risk"}:
            sanitized["camera_id"] = str(camera_id).strip() if camera_id else None
        return (
            sanitized,
            {"preset": "diagnostic_window", "start_time": analysis_start, "end_time": target_end},
            warnings,
        )

    start_time, end_time, time_window = resolve_time_window(raw_args)
    filters, filter_warnings = sanitize_filters(raw_args.get("filters", {}))
    warnings.extend(filter_warnings)

    sanitized: Dict[str, Any] = {
        "start_time": start_time,
        "end_time": end_time,
        "filters": filters,
    }

    if tool_name == "query_defects_by_furnace":
        group_level = raw_args.get("group_level") or "furnace_no"
        if group_level not in {"furnace_no", "plan_no", "billet_id"}:
            warnings.append(f"invalid_group_level:{group_level};fallback:furnace_no")
            group_level = "furnace_no"
        sanitized["group_level"] = group_level
    elif tool_name in {"get_top_ng_billets", "get_defect_images"}:
        limit = raw_args.get("limit", 10 if tool_name == "get_top_ng_billets" else 20)
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = 10
        sanitized["limit"] = max(1, min(limit, 100))
    elif tool_name == "generate_defect_report":
        sanitized["title"] = raw_args.get("title") or "方坯表面缺陷统计与空间分布分析报告"

    return sanitized, time_window, warnings


def execute_registered_tool(tool_name: str, raw_args: Dict[str, Any]) -> Dict[str, Any]:
    if tool_name not in TOOL_FUNCTIONS:
        return {
            "ok": False,
            "tool": tool_name,
            "arguments": {},
            "result": {},
            "time_window": {"preset": "all", "start_time": None, "end_time": None},
            "filters": {},
            "warnings": [f"unsupported_tool:{tool_name}"],
        }

    sanitized, time_window, warnings = sanitize_tool_arguments(tool_name, raw_args)
    try:
        result = TOOL_FUNCTIONS[tool_name](**sanitized)
        return {
            "ok": True,
            "tool": tool_name,
            "arguments": sanitized,
            "result": result,
            "time_window": time_window,
            "filters": sanitized.get("filters", {}),
            "warnings": warnings,
        }
    except Exception as exc:
        return {
            "ok": False,
            "tool": tool_name,
            "arguments": sanitized,
            "result": {},
            "time_window": time_window,
            "filters": sanitized.get("filters", {}),
            "warnings": warnings + [f"tool_error:{tool_name}:{exc}"],
        }


def result_has_data(tool_name: str, result: Dict[str, Any]) -> bool:
    if not result:
        return False
    if tool_name in DIAGNOSTIC_TOOL_NAMES:
        return result.get("status") not in {None, "no_data"}
    if tool_name == "query_defect_stats":
        return result.get("total_defects", 0) > 0
    if tool_name in {"group_defects_by_type", "group_defects_by_face", "query_defects_by_furnace"}:
        return result.get("total", 0) > 0 and bool(result.get("items"))
    if tool_name == "group_defects_by_position":
        return result.get("total", 0) > 0 and bool(result.get("heatmap"))
    if tool_name in {"get_top_ng_billets", "get_defect_images"}:
        return bool(result.get("items"))
    if tool_name == "generate_defect_report":
        summary = result.get("summary", {})
        return any(summary.values())
    if tool_name == "retrieve_defect_knowledge":
        return bool(result.get("items"))
    return bool(result)


def summarize_result(tool_name: str, result: Dict[str, Any]) -> str:
    if tool_name == "query_defect_stats":
        return (
            f"有效缺陷 {result.get('total_defects', 0)} 条，涉及 "
            f"{result.get('affected_billets', 0)} 支方坯、"
            f"{result.get('affected_furnaces', 0)} 个炉号、"
            f"{result.get('affected_plans', 0)} 个计划号。"
        )
    if tool_name in {"group_defects_by_type", "group_defects_by_face", "query_defects_by_furnace"}:
        items = result.get("items", [])
        if not items:
            return "没有聚合结果。"
        top = items[0]
        label = top.get("label") or top.get("key")
        return f"Top 项为 {label}，数量 {top.get('defect_count')} 条，占比 {top.get('ratio_pct')}%。"
    if tool_name == "group_defects_by_position":
        heatmap = result.get("heatmap", [])
        if not heatmap:
            return "没有空间分布结果。"
        top = heatmap[0]
        return (
            f"最集中区域为 {top.get('length_label')} + {top.get('width_label')}，"
            f"{top.get('defect_count')} 条，占比 {top.get('ratio_pct')}%。"
        )
    if tool_name == "get_top_ng_billets":
        items = result.get("items", [])
        if not items:
            return "没有 NG 率排名结果。"
        top = items[0]
        return f"NG 率最高方坯为 {top.get('billet_id')}，NG 率 {top.get('ng_rate_pct')}%。"
    if tool_name == "get_defect_images":
        return f"返回 {len(result.get('items', []))} 条缺陷原图记录。"
    if tool_name == "generate_defect_report":
        return f"已生成报告：{result.get('report_path')}"
    if tool_name == "retrieve_defect_knowledge":
        items = result.get("items", [])
        if not items:
            return "未检索到相关知识片段。"
        top = items[0]
        return (
            f"检索到 {len(items)} 条知识片段，Top1={top.get('title')}，"
            f"检索器={top.get('retriever')}，rerank={top.get('rerank_score', top.get('score'))}，"
            f"证据充分={result.get('evidence_judge', {}).get('evidence_sufficient')}。"
        )
    if tool_name == "detect_defect_spike":
        metrics = result.get("key_metrics", {})
        return (
            f"缺陷突增状态={result.get('status')}，目标窗口 "
            f"{metrics.get('target_count', 0)} 条，基线 {metrics.get('baseline_count', 0)} 条。"
        )
    if tool_name == "analyze_defect_camera_concentration":
        metrics = result.get("key_metrics", {})
        return (
            f"相机集中度={result.get('status')}，Top 相机 {metrics.get('top_camera')}，"
            f"占比 {metrics.get('top_camera_ratio_pct')}%。"
        )
    if tool_name == "analyze_camera_health":
        metrics = result.get("key_metrics", {})
        return (
            f"相机健康={result.get('status')}，{metrics.get('camera_id')} "
            f"FPS下降 {metrics.get('fps_drop_pct')}%，亮度下降 {metrics.get('brightness_drop_pct')}%。"
        )
    if tool_name == "analyze_image_quality":
        metrics = result.get("key_metrics", {})
        return (
            f"图像质量={result.get('status')}，{metrics.get('camera_id')} "
            f"亮度 {metrics.get('avg_brightness')}，边缘框占比 {metrics.get('edge_box_ratio')}。"
        )
    if tool_name == "estimate_false_positive_risk":
        return (
            f"诊断结论：{result.get('summary')} "
            f"root_cause={result.get('root_cause')}，false_positive_risk={result.get('false_positive_risk')}。"
        )
    return "工具已返回结果。"


def compact_tool_results(tool_results: Dict[str, Any], max_chars: int = 12000) -> str:
    text = json.dumps(tool_results, ensure_ascii=False, indent=2)
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n...<truncated>"
