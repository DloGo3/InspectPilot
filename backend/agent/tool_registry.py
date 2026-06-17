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

TOOL_FUNCTIONS: Dict[str, Callable[..., Dict[str, Any]]] = {
    "query_defect_stats": query_defect_stats,
    "group_defects_by_type": group_defects_by_type,
    "group_defects_by_face": group_defects_by_face,
    "group_defects_by_position": group_defects_by_position,
    "query_defects_by_furnace": query_defects_by_furnace,
    "get_top_ng_billets": get_top_ng_billets,
    "get_defect_images": get_defect_images,
    "generate_defect_report": generate_defect_report,
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


def _schema(description: str, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    properties = dict(COMMON_PROPERTIES)
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
}

for _name, _description in _TOOL_DESCRIPTIONS.items():
    extra_schema = None
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

    tool_schema = _schema(_description, extra_schema)
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
    return "工具已返回结果。"


def compact_tool_results(tool_results: Dict[str, Any], max_chars: int = 12000) -> str:
    text = json.dumps(tool_results, ensure_ascii=False, indent=2)
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n...<truncated>"

