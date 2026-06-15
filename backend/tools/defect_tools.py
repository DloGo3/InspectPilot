import json
import sqlite3
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
DEFAULT_DB_PATH = BACKEND_DIR / "data" / "defects.db"
REPORT_DIR = PROJECT_ROOT / "docs" / "reports"

CAMERA_FACE_MAP = {
    "CAM01": "top",
    "CAM02": "right",
    "CAM03": "bottom",
    "CAM04": "left",
    "C1": "top",
    "C2": "right",
    "C3": "bottom",
    "C4": "left",
}

FACE_LABELS = {
    "top": "上表面",
    "bottom": "下表面",
    "left": "左表面",
    "right": "右表面",
}

LENGTH_REGION_LABELS = {
    "head": "头部",
    "middle": "中部",
    "tail": "尾部",
}

WIDTH_REGION_LABELS = {
    "edge": "边部",
    "center": "中心区域",
}


def get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path or DEFAULT_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def map_camera_to_face(camera_id: str, camera_face_map: Optional[Dict[str, str]] = None) -> str:
    mapping = camera_face_map or CAMERA_FACE_MAP
    return mapping.get(camera_id, "unknown")


def classify_length_region(length_pos: float) -> str:
    if length_pos < 0.2:
        return "head"
    if length_pos > 0.8:
        return "tail"
    return "middle"


def classify_width_region(width_pos: float, edge_ratio: float = 0.2) -> str:
    if width_pos <= edge_ratio or width_pos >= 1 - edge_ratio:
        return "edge"
    return "center"


def compute_length_pos(
    frame_no: int,
    fps: float,
    billet_speed_mps: float,
    billet_length_m: float,
    billet_start_frame: int = 0,
) -> float:
    if fps <= 0 or billet_speed_mps <= 0 or billet_length_m <= 0:
        return 0.0
    elapsed_frames = max(frame_no - billet_start_frame, 0)
    distance_m = elapsed_frames / fps * billet_speed_mps
    return round(max(0.0, min(distance_m / billet_length_m, 1.0)), 4)


def compute_width_pos_from_bbox(bbox: Dict[str, float], image_width: int) -> float:
    if image_width <= 0:
        return 0.0
    center_x = float(bbox.get("x", 0)) + float(bbox.get("w", 0)) / 2
    return round(max(0.0, min(center_x / image_width, 1.0)), 4)


def _parse_bbox(bbox: str) -> Dict[str, Any]:
    try:
        return json.loads(bbox)
    except json.JSONDecodeError:
        return {"raw": bbox}


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    data = dict(row)
    data["bbox"] = _parse_bbox(data.get("bbox", ""))
    data["face_label"] = FACE_LABELS.get(data.get("face_id"), data.get("face_id"))
    data["length_region_label"] = LENGTH_REGION_LABELS.get(data.get("length_region"), data.get("length_region"))
    data["width_region_label"] = WIDTH_REGION_LABELS.get(data.get("width_region"), data.get("width_region"))
    return data


def _build_where(
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    filters: Optional[Dict[str, Any]] = None,
    include_false_positive: bool = False,
) -> Tuple[str, List[Any]]:
    conditions: List[str] = []
    params: List[Any] = []
    filters = filters or {}

    if start_time:
        conditions.append("timestamp >= ?")
        params.append(start_time)
    if end_time:
        conditions.append("timestamp <= ?")
        params.append(end_time)

    for field in ["defect_type", "furnace_no", "plan_no", "billet_id", "face_id", "severity", "length_region", "width_region"]:
        value = filters.get(field)
        if value:
            conditions.append(f"{field} = ?")
            params.append(value)

    if not include_false_positive:
        conditions.append("review_status != ?")
        params.append("false_positive")

    if not conditions:
        return "", params
    return "WHERE " + " AND ".join(conditions), params


def _safe_pct(count: int, total: int) -> float:
    return round(count / total * 100, 2) if total else 0.0


def _group_by(
    column: str,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    filters: Optional[Dict[str, Any]] = None,
    include_false_positive: bool = False,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    where, params = _build_where(start_time, end_time, filters, include_false_positive)
    sql = f"""
        SELECT {column} AS key, COUNT(*) AS defect_count, AVG(confidence) AS avg_confidence
        FROM defect_records
        {where}
        GROUP BY {column}
        ORDER BY defect_count DESC, avg_confidence DESC
    """
    with get_connection(db_path) as conn:
        rows = conn.execute(sql, params).fetchall()
        total = conn.execute(f"SELECT COUNT(*) FROM defect_records {where}", params).fetchone()[0]

    items = [
        {
            "key": row["key"],
            "label": _label_for_column(column, row["key"]),
            "defect_count": row["defect_count"],
            "ratio_pct": _safe_pct(row["defect_count"], total),
            "avg_confidence": round(row["avg_confidence"] or 0, 4),
        }
        for row in rows
    ]
    return {"total": total, "group_by": column, "items": items}


def _label_for_column(column: str, value: str) -> str:
    if column == "face_id":
        return FACE_LABELS.get(value, value)
    if column == "length_region":
        return LENGTH_REGION_LABELS.get(value, value)
    if column == "width_region":
        return WIDTH_REGION_LABELS.get(value, value)
    return value


def get_latest_timestamp(db_path: Optional[str] = None) -> Optional[str]:
    with get_connection(db_path) as conn:
        row = conn.execute("SELECT MAX(timestamp) AS latest_ts FROM defect_records").fetchone()
    return row["latest_ts"] if row and row["latest_ts"] else None


def query_defect_stats(
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    filters: Optional[Dict[str, Any]] = None,
    include_false_positive: bool = False,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Return headline defect statistics for a time window."""
    where, params = _build_where(start_time, end_time, filters, include_false_positive)
    with get_connection(db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT
                COUNT(*) AS total_defects,
                COUNT(DISTINCT billet_id) AS affected_billets,
                COUNT(DISTINCT furnace_no) AS affected_furnaces,
                COUNT(DISTINCT plan_no) AS affected_plans,
                AVG(confidence) AS avg_confidence,
                MIN(timestamp) AS first_seen,
                MAX(timestamp) AS last_seen
            FROM defect_records
            {where}
            """,
            params,
        ).fetchone()

        severity_rows = conn.execute(
            f"SELECT severity, COUNT(*) AS count FROM defect_records {where} GROUP BY severity ORDER BY count DESC",
            params,
        ).fetchall()
        review_rows = conn.execute(
            f"SELECT review_status, COUNT(*) AS count FROM defect_records {where} GROUP BY review_status ORDER BY count DESC",
            params,
        ).fetchall()

    total = rows["total_defects"] or 0
    return {
        "time_window": {"start_time": start_time, "end_time": end_time},
        "filters": filters or {},
        "total_defects": total,
        "affected_billets": rows["affected_billets"] or 0,
        "affected_furnaces": rows["affected_furnaces"] or 0,
        "affected_plans": rows["affected_plans"] or 0,
        "avg_confidence": round(rows["avg_confidence"] or 0, 4),
        "first_seen": rows["first_seen"],
        "last_seen": rows["last_seen"],
        "severity_distribution": {r["severity"]: r["count"] for r in severity_rows},
        "review_status_distribution": {r["review_status"]: r["count"] for r in review_rows},
        "evidence": "defect_records table, excluding review_status=false_positive by default",
    }


def group_defects_by_type(
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    filters: Optional[Dict[str, Any]] = None,
    include_false_positive: bool = False,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    return _group_by("defect_type", start_time, end_time, filters, include_false_positive, db_path)


def group_defects_by_face(
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    filters: Optional[Dict[str, Any]] = None,
    include_false_positive: bool = False,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    return _group_by("face_id", start_time, end_time, filters, include_false_positive, db_path)


def group_defects_by_position(
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    filters: Optional[Dict[str, Any]] = None,
    include_false_positive: bool = False,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    where, params = _build_where(start_time, end_time, filters, include_false_positive)
    with get_connection(db_path) as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM defect_records {where}", params).fetchone()[0]
        length_rows = conn.execute(
            f"""
            SELECT length_region AS key, COUNT(*) AS defect_count, AVG(confidence) AS avg_confidence
            FROM defect_records {where}
            GROUP BY length_region
            ORDER BY defect_count DESC
            """,
            params,
        ).fetchall()
        width_rows = conn.execute(
            f"""
            SELECT width_region AS key, COUNT(*) AS defect_count, AVG(confidence) AS avg_confidence
            FROM defect_records {where}
            GROUP BY width_region
            ORDER BY defect_count DESC
            """,
            params,
        ).fetchall()
        heatmap_rows = conn.execute(
            f"""
            SELECT length_region, width_region, COUNT(*) AS defect_count
            FROM defect_records {where}
            GROUP BY length_region, width_region
            ORDER BY defect_count DESC
            """,
            params,
        ).fetchall()

    return {
        "total": total,
        "by_length_region": [
            {
                "key": r["key"],
                "label": LENGTH_REGION_LABELS.get(r["key"], r["key"]),
                "defect_count": r["defect_count"],
                "ratio_pct": _safe_pct(r["defect_count"], total),
                "avg_confidence": round(r["avg_confidence"] or 0, 4),
            }
            for r in length_rows
        ],
        "by_width_region": [
            {
                "key": r["key"],
                "label": WIDTH_REGION_LABELS.get(r["key"], r["key"]),
                "defect_count": r["defect_count"],
                "ratio_pct": _safe_pct(r["defect_count"], total),
                "avg_confidence": round(r["avg_confidence"] or 0, 4),
            }
            for r in width_rows
        ],
        "heatmap": [
            {
                "length_region": r["length_region"],
                "length_label": LENGTH_REGION_LABELS.get(r["length_region"], r["length_region"]),
                "width_region": r["width_region"],
                "width_label": WIDTH_REGION_LABELS.get(r["width_region"], r["width_region"]),
                "defect_count": r["defect_count"],
                "ratio_pct": _safe_pct(r["defect_count"], total),
            }
            for r in heatmap_rows
        ],
    }


def query_defects_by_furnace(
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    filters: Optional[Dict[str, Any]] = None,
    group_level: str = "furnace_no",
    include_false_positive: bool = False,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    if group_level not in {"furnace_no", "plan_no", "billet_id"}:
        group_level = "furnace_no"
    where, params = _build_where(start_time, end_time, filters, include_false_positive)
    with get_connection(db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT
                {group_level} AS key,
                COUNT(*) AS defect_count,
                COUNT(DISTINCT billet_id) AS affected_billets,
                SUM(CASE WHEN severity = 'critical' THEN 1 ELSE 0 END) AS critical_count,
                AVG(confidence) AS avg_confidence
            FROM defect_records
            {where}
            GROUP BY {group_level}
            ORDER BY critical_count DESC, defect_count DESC
            """,
            params,
        ).fetchall()
        total = conn.execute(f"SELECT COUNT(*) FROM defect_records {where}", params).fetchone()[0]

    return {
        "group_level": group_level,
        "total": total,
        "items": [
            {
                "key": r["key"],
                "defect_count": r["defect_count"],
                "ratio_pct": _safe_pct(r["defect_count"], total),
                "affected_billets": r["affected_billets"],
                "critical_count": r["critical_count"],
                "avg_confidence": round(r["avg_confidence"] or 0, 4),
            }
            for r in rows
        ],
    }


def get_top_ng_billets(
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    filters: Optional[Dict[str, Any]] = None,
    limit: int = 10,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    filters = filters or {}
    conditions = []
    params: List[Any] = []

    if start_time:
        conditions.append("q.end_time >= ?")
        params.append(start_time)
    if end_time:
        conditions.append("q.start_time <= ?")
        params.append(end_time)
    for field in ["furnace_no", "plan_no", "billet_id"]:
        if filters.get(field):
            conditions.append(f"q.{field} = ?")
            params.append(filters[field])

    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    params.append(limit)

    with get_connection(db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT
                q.billet_id,
                q.furnace_no,
                q.plan_no,
                q.inspected_frames,
                q.ng_frames,
                ROUND(q.ng_frames * 100.0 / NULLIF(q.inspected_frames, 0), 2) AS ng_rate_pct,
                q.start_time,
                q.end_time,
                q.remark,
                COUNT(d.defect_id) AS defect_count,
                SUM(CASE WHEN d.severity = 'critical' AND d.review_status != 'false_positive' THEN 1 ELSE 0 END) AS critical_count
            FROM billet_quality q
            LEFT JOIN defect_records d ON q.billet_id = d.billet_id
            {where}
            GROUP BY q.billet_id
            ORDER BY ng_rate_pct DESC, critical_count DESC, defect_count DESC
            LIMIT ?
            """,
            params,
        ).fetchall()

    return {"items": [dict(r) for r in rows], "metric": "ng_frames / inspected_frames"}


def get_defect_images(
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    filters: Optional[Dict[str, Any]] = None,
    limit: int = 20,
    include_false_positive: bool = False,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    where, params = _build_where(start_time, end_time, filters, include_false_positive)
    params.append(limit)
    with get_connection(db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT defect_id, timestamp, billet_id, furnace_no, plan_no, camera_id, face_id,
                   defect_type, confidence, bbox, image_path, length_region, width_region, severity, review_status
            FROM defect_records
            {where}
            ORDER BY timestamp DESC, confidence DESC
            LIMIT ?
            """,
            params,
        ).fetchall()

    return {"items": [_row_to_dict(r) for r in rows], "limit": limit}


def _top_item(items: Iterable[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    items = list(items)
    return items[0] if items else None


def generate_defect_report(
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    filters: Optional[Dict[str, Any]] = None,
    title: str = "方坯表面缺陷统计与空间分布分析报告",
    db_path: Optional[str] = None,
    output_dir: Optional[str] = None,
) -> Dict[str, Any]:
    stats = query_defect_stats(start_time, end_time, filters, db_path=db_path)
    by_type = group_defects_by_type(start_time, end_time, filters, db_path=db_path)
    by_face = group_defects_by_face(start_time, end_time, filters, db_path=db_path)
    by_position = group_defects_by_position(start_time, end_time, filters, db_path=db_path)
    by_furnace = query_defects_by_furnace(start_time, end_time, filters, "furnace_no", db_path=db_path)
    by_plan = query_defects_by_furnace(start_time, end_time, filters, "plan_no", db_path=db_path)
    top_ng = get_top_ng_billets(start_time, end_time, filters, limit=5, db_path=db_path)

    top_type = _top_item(by_type["items"])
    top_face = _top_item(by_face["items"])
    top_length = _top_item(by_position["by_length_region"])
    top_width = _top_item(by_position["by_width_region"])
    top_furnace = _top_item(by_furnace["items"])
    top_plan = _top_item(by_plan["items"])
    top_billet = _top_item(top_ng["items"])

    report_lines = [
        f"# {title}",
        "",
        f"- 分析时间窗: {start_time or '不限'} 至 {end_time or '不限'}",
        f"- 样本范围: {stats['total_defects']} 条有效缺陷记录，涉及 {stats['affected_billets']} 支方坯、{stats['affected_furnaces']} 个炉号、{stats['affected_plans']} 个计划号",
        f"- 数据口径: 默认排除 review_status=false_positive 的记录",
        "",
        "## 1. 核心结论",
    ]

    if stats["total_defects"] == 0:
        report_lines.append("- 当前时间窗未检索到有效缺陷记录。")
    else:
        if top_type:
            report_lines.append(f"- 缺陷数量最多的类别是 **{top_type['label']}**，共 {top_type['defect_count']} 条，占比 {top_type['ratio_pct']}%。")
        if top_face:
            report_lines.append(f"- 缺陷最多的表面是 **{top_face['label']}**，共 {top_face['defect_count']} 条，占比 {top_face['ratio_pct']}%。")
        if top_length and top_width:
            report_lines.append(f"- 长度方向主要集中在 **{top_length['label']}**，宽度方向主要集中在 **{top_width['label']}**。")
        if top_furnace:
            report_lines.append(f"- 炉号维度需关注 **{top_furnace['key']}**，有效缺陷 {top_furnace['defect_count']} 条，其中严重缺陷 {top_furnace['critical_count']} 条。")
        if top_plan:
            report_lines.append(f"- 计划号维度需关注 **{top_plan['key']}**，有效缺陷 {top_plan['defect_count']} 条。")
        if top_billet:
            report_lines.append(f"- NG 率最高方坯为 **{top_billet['billet_id']}**，NG 率 {top_billet['ng_rate_pct']}%，缺陷记录 {top_billet['defect_count']} 条。")

    report_lines.extend([
        "",
        "## 2. 缺陷类别分布",
        "| 缺陷类别 | 数量 | 占比 | 平均置信度 |",
        "| --- | ---: | ---: | ---: |",
    ])
    for item in by_type["items"]:
        report_lines.append(f"| {item['label']} | {item['defect_count']} | {item['ratio_pct']}% | {item['avg_confidence']} |")

    report_lines.extend([
        "",
        "## 3. 表面分布",
        "| 表面 | 数量 | 占比 | 平均置信度 |",
        "| --- | ---: | ---: | ---: |",
    ])
    for item in by_face["items"]:
        report_lines.append(f"| {item['label']} | {item['defect_count']} | {item['ratio_pct']}% | {item['avg_confidence']} |")

    report_lines.extend([
        "",
        "## 4. 空间位置分布",
        "| 长度位置 | 宽度位置 | 数量 | 占比 |",
        "| --- | --- | ---: | ---: |",
    ])
    for item in by_position["heatmap"]:
        report_lines.append(f"| {item['length_label']} | {item['width_label']} | {item['defect_count']} | {item['ratio_pct']}% |")

    report_lines.extend([
        "",
        "## 5. 炉号/计划号/方坯质量关注项",
        "| 维度 | 编号 | 缺陷数量 | 严重缺陷 | 说明 |",
        "| --- | --- | ---: | ---: | --- |",
    ])
    for item in by_furnace["items"][:5]:
        report_lines.append(f"| 炉号 | {item['key']} | {item['defect_count']} | {item['critical_count']} | affected_billets={item['affected_billets']} |")
    for item in by_plan["items"][:5]:
        report_lines.append(f"| 计划号 | {item['key']} | {item['defect_count']} | {item['critical_count']} | affected_billets={item['affected_billets']} |")
    for item in top_ng["items"][:5]:
        report_lines.append(f"| 方坯 | {item['billet_id']} | {item['defect_count']} | {item['critical_count']} | NG率={item['ng_rate_pct']}%，{item['remark']} |")

    report_lines.extend([
        "",
        "## 6. 建议",
        "- 对严重缺陷占比高的炉号/计划号进行批次复核，优先回看缺陷原图与质检复判结果。",
        "- 若裂纹在头部和边部连续集中，应联动检查切头、拉速波动、冷却均匀性和导卫/辊道接触状态。",
        "- 对 review_status=pending 的高置信度缺陷建立人工复核闭环，避免误检直接进入质量异常结论。",
    ])

    markdown = "\n".join(report_lines) + "\n"
    output_root = Path(output_dir) if output_dir else REPORT_DIR
    output_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = output_root / f"defect_report_{stamp}.md"
    report_path.write_text(markdown, encoding="utf-8")

    return {
        "report_path": str(report_path),
        "markdown": markdown,
        "summary": {
            "top_type": top_type,
            "top_face": top_face,
            "top_length_region": top_length,
            "top_width_region": top_width,
            "top_furnace": top_furnace,
            "top_plan": top_plan,
            "top_ng_billet": top_billet,
        },
    }

