import re
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple

from tools.defect_tools import get_latest_timestamp

DEFECT_TYPES = ["裂纹", "划伤", "结疤", "氧化皮", "凹坑", "夹渣", "麻点", "压痕"]
DEFECT_TYPE_ALIASES = {
    "裂纹": ["裂纹", "开裂", "裂缝"],
    "划伤": ["划伤", "刮伤", "擦伤"],
    "结疤": ["结疤", "疤痕"],
    "氧化皮": ["氧化皮", "氧化", "氧化铁皮"],
    "凹坑": ["凹坑", "点坑"],
    "夹渣": ["夹渣", "夹杂"],
    "麻点": ["麻点", "麻面"],
    "压痕": ["压痕", "压印", "压伤"],
}
FACE_WORDS = {
    "上表面": "top",
    "上面": "top",
    "顶面": "top",
    "下表面": "bottom",
    "下面": "bottom",
    "底面": "bottom",
    "左表面": "left",
    "左面": "left",
    "右表面": "right",
    "右面": "right",
}


def infer_intent(question: str) -> str:
    q = question.strip()
    if "报告" in q or "生成" in q:
        return "report"
    if any(word in q for word in ["原因", "为什么", "标准", "等级", "规则", "模板", "说明", "解释", "怎么判定", "如何判定", "建议", "导致", "一定", "危险", "人工确认", "误检", "看错", "工艺问题"]):
        return "knowledge"
    if "图片" in q or "原图" in q or "图像" in q:
        return "images"
    if "哪类" in q or "类别" in q or "类型" in q:
        return "group_by_type"
    if "哪个表面" in q or "表面缺陷最多" in q or "上表面" in q or "下表面" in q:
        return "group_by_face"
    if "头部" in q or "中部" in q or "尾部" in q or "边部" in q or "中心" in q or "集中在哪里" in q:
        return "group_by_position"
    if "NG" in q.upper() or "方坯 ID" in q or "方坯ID" in q or "最高" in q:
        return "top_ng"
    if "炉号" in q:
        return "furnace_quality"
    if "计划号" in q:
        return "plan_quality"
    if "最近" in q or "检测出" in q or "有哪些" in q:
        return "recent_defects"
    return "general_stats"


def extract_filters(question: str) -> Dict[str, Any]:
    filters: Dict[str, Any] = {}
    for defect_type in DEFECT_TYPES:
        aliases = DEFECT_TYPE_ALIASES.get(defect_type, [defect_type])
        if any(alias in question for alias in aliases):
            filters["defect_type"] = defect_type
            break
    for word, face in FACE_WORDS.items():
        if word in question:
            filters["face_id"] = face
            break

    furnace_match = re.search(r"(F\d{6,}|炉号[:：]?\s*([A-Za-z0-9-]+))", question)
    if furnace_match:
        filters["furnace_no"] = furnace_match.group(1) if furnace_match.group(1).startswith("F") else furnace_match.group(2)

    plan_match = re.search(r"(P-[A-Za-z0-9-]+|计划号[:：]?\s*([A-Za-z0-9-]+))", question)
    if plan_match:
        filters["plan_no"] = plan_match.group(1) if plan_match.group(1).startswith("P-") else plan_match.group(2)

    billet_match = re.search(r"(B\d{8,})", question)
    if not billet_match:
        billet_match = re.search(r"方坯(?:\s*ID|ID|id| Id)?[:：]\s*([A-Za-z0-9-]+)", question)
    if billet_match:
        filters["billet_id"] = billet_match.group(1)

    if "头部" in question:
        filters["length_region"] = "head"
    elif "中部" in question:
        filters["length_region"] = "middle"
    elif "尾部" in question:
        filters["length_region"] = "tail"

    if "边部" in question:
        filters["width_region"] = "edge"
    elif "中心" in question:
        filters["width_region"] = "center"

    return filters


def parse_time_range(question: str, db_path: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
    latest = get_latest_timestamp(db_path)
    end_dt = datetime.fromisoformat(latest) if latest else datetime.now()
    q = question.strip()

    if "最近一小时" in q or "最近1小时" in q or "近一小时" in q:
        return (end_dt - timedelta(hours=1)).isoformat(timespec="seconds"), end_dt.isoformat(timespec="seconds")
    if "最近一天" in q or "最近1天" in q or "近一天" in q or "今天" in q:
        return (end_dt - timedelta(days=1)).isoformat(timespec="seconds"), end_dt.isoformat(timespec="seconds")
    if "最近" in q and "小时" in q:
        match = re.search(r"最近(\d+)小时", q)
        hours = int(match.group(1)) if match else 1
        return (end_dt - timedelta(hours=hours)).isoformat(timespec="seconds"), end_dt.isoformat(timespec="seconds")
    return None, None


def should_use_rag(question: str, intent: str) -> bool:
    return intent in {"knowledge", "report"} or any(
        word in question
        for word in ["原因", "标准", "等级", "规则", "模板", "为什么", "建议", "说明", "解释", "判定", "复核", "导致", "一定", "危险", "人工确认", "误检", "看错", "工艺问题"]
    )
